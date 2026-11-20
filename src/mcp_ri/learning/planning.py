"""Provider-independent, evidence-aware learning-plan construction.

All matching is based on words present in the authored curriculum. Sequence
order follows validated curriculum prerequisites when present, then preserves
catalog order for unrelated topics. No prerequisite edge is inferred here.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Mapping

from .providers import ProviderAvailability, UnavailableStructuredLearningProvider


_STOP_WORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "by", "create", "for",
    "from", "help", "i", "in", "is", "it", "learn", "learning", "lesson", "me",
    "my", "of", "on", "or", "please", "plan", "student", "study", "the", "this",
    "to", "understand", "want", "with",
}


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return {word for word in re.findall(r"[a-z0-9]+", normalized) if word not in _STOP_WORDS}


def _flatten_curriculum(curriculum: Mapping[str, Any]) -> list[dict[str, Any]]:
    lessons_by_topic = {lesson["topic_id"]: lesson for lesson in curriculum.get("lessons", [])}
    questions_by_lesson: dict[str, list[dict[str, Any]]] = {}
    for question in curriculum.get("questions", []):
        questions_by_lesson.setdefault(question["lesson_id"], []).append(question)

    flattened: list[dict[str, Any]] = []
    for subject_index, subject in enumerate(curriculum.get("subjects", [])):
        for course_index, course in enumerate(subject.get("courses", [])):
            for unit_index, unit in enumerate(course.get("units", [])):
                for topic_index, topic in enumerate(unit.get("topics", [])):
                    lesson = lessons_by_topic.get(topic["topic_id"])
                    flattened.append({
                        "subject": subject,
                        "course": course,
                        "unit": unit,
                        "topic": topic,
                        "lesson": lesson,
                        "questions": questions_by_lesson.get(lesson["lesson_id"], []) if lesson else [],
                        "catalog_index": (subject_index, course_index, unit_index, topic_index),
                    })
    return flattened


def _topic_search_fields(entry: Mapping[str, Any]) -> dict[str, set[str]]:
    topic = entry["topic"]
    objectives = " ".join(item["text"] for item in topic.get("learning_objectives", []))
    return {
        "title": _tokens(topic.get("title", "")),
        "objective": _tokens(objectives),
        "description": _tokens(topic.get("description", "")),
        "course": _tokens(entry["course"].get("title", "") + " " + entry["course"].get("description", "")),
        "subject": _tokens(entry["subject"].get("title", "") + " " + entry["subject"].get("description", "")),
        "unit": _tokens(entry["unit"].get("title", "") + " " + entry["unit"].get("description", "")),
    }


def _map_goal(goal: str, curriculum: Mapping[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    goal_terms = _tokens(goal)
    searchable = [(entry, _topic_search_fields(entry)) for entry in entries]
    all_catalog_terms = set().union(*(set().union(*fields.values()) for _, fields in searchable)) if searchable else set()
    matched_terms = sorted(goal_terms & all_catalog_terms)
    unmatched_terms = sorted(goal_terms - all_catalog_terms)

    direct_matches: list[dict[str, Any]] = []
    if goal_terms:
        for entry, fields in searchable:
            topic_terms = fields["title"] | fields["objective"] | fields["description"] | fields["unit"]
            organizational_terms = fields["course"] | fields["subject"]
            direct_terms = goal_terms & topic_terms
            course_terms = goal_terms & organizational_terms
            if direct_terms or course_terms:
                entry["inclusion_reason"] = "goal_match"
                entry["matched_terms"] = sorted(direct_terms | course_terms)
                direct_matches.append(entry)

    catalog_gaps: list[str] = []
    for subject in curriculum.get("subjects", []):
        if _tokens(subject.get("title", "")) & goal_terms and not subject.get("courses"):
            catalog_gaps.append(
                f"Subject '{subject['title']}' is listed in the catalog but has no curated courses or lessons."
            )

    if not goal_terms:
        reason = "The goal contains no topic terms that can be mapped against the current curriculum."
    elif not direct_matches:
        reason = "No existing course, topic, objective, or lesson metadata matched the goal terms."
    elif unmatched_terms:
        reason = "Some goal terms match existing curriculum metadata; unmatched terms remain unsupported."
    else:
        reason = "Goal terms matched existing curriculum metadata."

    return {
        "goal_terms": sorted(goal_terms),
        "matched_terms": matched_terms,
        "unmatched_terms": unmatched_terms,
        "direct_matches": direct_matches,
        "catalog_gaps": catalog_gaps,
        "reason": reason,
    }


def _expand_validated_prerequisites(
    direct_matches: list[dict[str, Any]], entries: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]], list[str]]:
    by_id = {entry["topic"]["topic_id"]: entry for entry in entries}
    included = {entry["topic"]["topic_id"]: entry for entry in direct_matches}
    relationships: list[dict[str, str]] = []
    missing: list[str] = []
    pending = list(included)
    seen_edges: set[tuple[str, str]] = set()

    while pending:
        topic_id = pending.pop()
        topic = included[topic_id]["topic"]
        if topic.get("prerequisites_status") != "validated":
            continue
        for prerequisite_id in topic.get("prerequisite_topic_ids", []):
            edge = (prerequisite_id, topic_id)
            if edge in seen_edges:
                continue
            prerequisite = by_id.get(prerequisite_id)
            if prerequisite is None or prerequisite.get("lesson") is None:
                missing.append(
                    f"Curriculum prerequisite '{prerequisite_id}' referenced by '{topic_id}' has no available lesson."
                )
                continue
            seen_edges.add(edge)
            relationships.append({
                "prerequisite_topic_id": prerequisite_id,
                "topic_id": topic_id,
                "source": "curriculum",
                "verification_status": "validated",
            })
            if prerequisite_id not in included:
                prerequisite["inclusion_reason"] = "validated_prerequisite"
                prerequisite["matched_terms"] = []
                included[prerequisite_id] = prerequisite
                pending.append(prerequisite_id)

    return included, relationships, missing


def _ordered_topic_ids(
    included: Mapping[str, dict[str, Any]], relationships: list[dict[str, str]],
) -> tuple[list[str], bool]:
    indices = {topic_id: entry["catalog_index"] for topic_id, entry in included.items()}
    dependencies: dict[str, set[str]] = {topic_id: set() for topic_id in included}
    for relation in relationships:
        prerequisite_id = relation["prerequisite_topic_id"]
        topic_id = relation["topic_id"]
        if prerequisite_id in dependencies and topic_id in dependencies:
            dependencies[topic_id].add(prerequisite_id)

    ordered: list[str] = []
    remaining = set(included)
    while remaining:
        ready = sorted(
            (topic_id for topic_id in remaining if dependencies[topic_id].issubset(ordered)),
            key=indices.__getitem__,
        )
        if not ready:
            return sorted(included, key=indices.__getitem__), True
        selected = ready[0]
        ordered.append(selected)
        remaining.remove(selected)
    return ordered, False


def _knowledge_summary(
    topic_id: str, raw: Mapping[str, Any], state_version: int,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "topic_id": topic_id,
        "attempts": int(raw.get("attempts", 0)),
        "correct": int(raw.get("correct", 0)),
        "incorrect": int(raw.get("incorrect", 0)),
        "historical_accuracy": raw.get("historical_accuracy"),
        "recent_accuracy": raw.get("recent_accuracy"),
        "evidence_sufficiency": raw.get("evidence_sufficiency", "none"),
        "performance_trend": raw.get("performance_trend", "insufficient_evidence"),
        "state_version": state_version,
        "supporting_evidence_ids": sorted(set(evidence_ids)),
        "interpretation": "descriptive_response_history_only",
    }


def build_rule_based_learning_plan(
    *,
    learning_goal: str,
    curriculum: Mapping[str, Any],
    state_version: int | None = None,
    topic_state: Mapping[str, Mapping[str, Any]] | None = None,
    topic_evidence_ids: Mapping[str, list[str]] | None = None,
    provider_availability: ProviderAvailability | None = None,
) -> dict[str, Any]:
    """Map a learner goal only to supported catalog content and relationships."""
    entries = _flatten_curriculum(curriculum)
    mapping = _map_goal(learning_goal, curriculum, entries)
    direct_matches = mapping["direct_matches"]
    included, relationships, prerequisite_missing = _expand_validated_prerequisites(direct_matches, entries)
    ordered_ids, dependency_cycle = _ordered_topic_ids(included, relationships)
    topic_state = topic_state or {}
    topic_evidence_ids = topic_evidence_ids or {}
    state_by_topic = {
        topic_id: _knowledge_summary(topic_id, value, state_version or 1, topic_evidence_ids.get(topic_id, []))
        for topic_id, value in topic_state.items()
        if topic_id in included and state_version is not None
    }

    questions_by_topic = {
        topic_id: entry["questions"] for topic_id, entry in included.items()
    }
    steps: list[dict[str, Any]] = []
    total_minutes = 0
    for sequence, topic_id in enumerate(ordered_ids, start=1):
        entry = included[topic_id]
        topic = entry["topic"]
        lesson = entry["lesson"]
        questions = questions_by_topic[topic_id]
        valid_prereqs = sorted(
            relation["prerequisite_topic_id"]
            for relation in relationships if relation["topic_id"] == topic_id
        )
        question_types = sorted({item["question_type"] for item in questions})
        assessment_available = bool(questions)
        minutes = int(topic.get("estimated_minutes", lesson.get("estimated_minutes", 0)))
        total_minutes += minutes
        steps.append({
            "sequence": sequence,
            "topic_id": topic_id,
            "topic_title": topic["title"],
            "subject_id": entry["subject"]["subject_id"],
            "subject_title": entry["subject"]["title"],
            "course_id": entry["course"]["course_id"],
            "course_title": entry["course"]["title"],
            "unit_id": entry["unit"]["unit_id"],
            "unit_title": entry["unit"]["title"],
            "lesson_id": lesson["lesson_id"],
            "learning_objectives": topic.get("learning_objectives", []),
            "estimated_minutes": minutes,
            "inclusion_reason": entry.get("inclusion_reason", "goal_match"),
            "prerequisite_topic_ids": valid_prereqs,
            "prerequisites_status": topic.get("prerequisites_status", "not_established"),
            "assessment": {
                "source": "curated_questions" if assessment_available else "unavailable",
                "question_ids": [item["question_id"] for item in questions],
                "question_types": question_types,
                "evaluation_mode": "backend_scored_choice_or_numeric" if assessment_available else "not_available",
            },
            "prior_response_summary": state_by_topic.get(topic_id),
        })

    module_order: list[str] = []
    module_courses: dict[str, dict[str, Any]] = {}
    module_topic_ids: dict[str, list[str]] = {}
    for topic_id in ordered_ids:
        entry = included[topic_id]
        course_id = entry["course"]["course_id"]
        if course_id not in module_courses:
            module_order.append(course_id)
            module_courses[course_id] = entry["course"]
            module_topic_ids[course_id] = []
        module_topic_ids[course_id].append(topic_id)
    modules = [{
        "module_id": course_id,
        "title": module_courses[course_id]["title"],
        "description": module_courses[course_id]["description"],
        "course_id": course_id,
        "ordered_topic_ids": module_topic_ids[course_id],
    } for course_id in module_order]

    knowledge_summaries = [state_by_topic[topic_id] for topic_id in ordered_ids if topic_id in state_by_topic]
    if knowledge_summaries:
        knowledge = {
            "status": "available",
            "source": "student_studio_phase9_behavioral_summary",
            "state_version": state_version,
            "topic_summaries": knowledge_summaries,
            "reason": "Matched topics include saved Student Studio response summaries; these describe responses, not knowledge mastery.",
        }
    else:
        knowledge = {
            "status": "not_available",
            "source": None,
            "state_version": state_version,
            "topic_summaries": [],
            "reason": "No saved response summary is available for the mapped topics; no knowledge assessment was performed.",
        }

    missing_information = list(mapping["catalog_gaps"]) + prerequisite_missing
    without_prerequisites = sorted(
        topic_id for topic_id in included
        if not any(relation["topic_id"] == topic_id for relation in relationships)
    )
    if without_prerequisites:
        missing_information.append(
            "Prerequisites are not established for some mapped topics; their catalog order is not a prerequisite claim."
        )
    if any(not step["assessment"]["question_ids"] for step in steps):
        missing_information.append("One or more mapped lessons have no linked curated assessment questions.")
    if mapping["unmatched_terms"] and direct_matches:
        missing_information.append("Some learning-goal terms are not represented in the matched curriculum.")
    if dependency_cycle:
        missing_information.append("Validated prerequisite relationships contain a cycle; catalog order was used for sequencing.")
    if direct_matches and not mapping["unmatched_terms"]:
        status = "mapped"
    elif direct_matches:
        status = "partially_mapped"
    else:
        status = "unsupported"

    availability = provider_availability or UnavailableStructuredLearningProvider().availability("learning_plan")
    provider = {
        "capability": "learning_plan",
        "status": "available" if availability.available else "unavailable",
        "provider_id": availability.provider_id,
        "reason": availability.reason,
        "invoked": False,
    }
    identity = json.dumps({
        "goal": " ".join(learning_goal.split()).casefold(),
        "curriculum_version": curriculum.get("curriculum_version"),
        "state_version": state_version,
        "ordered_topic_ids": ordered_ids,
    }, sort_keys=True, separators=(",", ":"))
    plan_id = "plan-" + hashlib.sha256(identity.encode()).hexdigest()[:32]
    if not steps:
        missing_information.append("The current curated catalog does not provide a lesson sequence for this goal.")
    return {
        "plan_id": plan_id,
        "status": status,
        "generation_mode": "rule_based",
        "persisted": False,
        "learner_profile_id": "studio-local-demo",
        "learning_goal": learning_goal,
        "curriculum_version": curriculum.get("curriculum_version", "unknown"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "mapping": {
            "status": status,
            "method": "catalog_keyword_match",
            "matched_goal_terms": mapping["matched_terms"],
            "unmatched_goal_terms": mapping["unmatched_terms"],
            "catalog_gaps": mapping["catalog_gaps"],
            "reason": mapping["reason"],
        },
        "knowledge_assessment": knowledge,
        "prerequisites": {
            "status": "identified" if relationships else "not_established",
            "relationships": relationships,
            "topics_without_validated_prerequisites": without_prerequisites,
            "reason": (
                "Only prerequisite relationships explicitly marked validated in the curriculum are included."
                if relationships else "No validated prerequisite relationships are present in the current curriculum."
            ),
        },
        "modules": modules,
        "ordered_topic_ids": ordered_ids,
        "learning_sequence": steps,
        "estimated_minutes": total_minutes,
        "missing_information": list(dict.fromkeys(missing_information)),
        "limitations": [
            "Goal mapping uses literal keyword overlap with authored catalog text; it is not semantic goal understanding.",
            "The sequence is rule-based and uses only validated curriculum prerequisites, then catalog order.",
            "Behavioral summaries are observed response history and are not validated knowledge or mastery estimates.",
            "This preview is not persisted and cannot be resumed or edited as a saved plan.",
            "No AI provider was invoked; lesson generation and tutoring remain separate existing capabilities.",
        ],
    }
