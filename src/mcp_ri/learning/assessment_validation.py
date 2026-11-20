"""Offline descriptive audits for Student Studio assessment inputs.

The functions in this module report structure and observed response history.
They do not calculate psychometric reliability, predictive validity, or mastery.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


VALID_DIFFICULTIES = {"introductory", "intermediate", "advanced"}
VALID_QUESTION_TYPES = {"single_choice", "multiple_choice", "numeric"}
COGNITIVE_DEMAND_CATEGORIES = (
    "recall", "conceptual_understanding", "application", "analysis", "problem_solving",
)
QUESTION_REVIEW_STATUSES = (
    "pending_review", "approved", "approved_with_revision", "requires_revision", "rejected",
)


def audit_question_quality(curriculum: Mapping[str, Any]) -> dict[str, Any]:
    """Audit catalog structure and flag content questions for human review."""
    topics: dict[str, dict[str, Any]] = {}
    lessons = {item.get("lesson_id"): item for item in curriculum.get("lessons", [])}
    for subject in curriculum.get("subjects", []):
        for course in subject.get("courses", []):
            for unit in course.get("units", []):
                for topic in unit.get("topics", []):
                    topics[topic.get("topic_id")] = {
                        "topic_id": topic.get("topic_id"),
                        "topic_title": topic.get("title", ""),
                        "course_id": course.get("course_id"),
                        "lesson_id": topic.get("lesson_id"),
                        "objective_ids": {item.get("objective_id") for item in topic.get("learning_objectives", [])},
                        "question_ids": [],
                        "question_objective_ids": [],
                    }

    question_ids = [item.get("question_id") for item in curriculum.get("questions", [])]
    duplicate_ids = sorted(item for item, count in Counter(question_ids).items() if item and count > 1)
    duplicate_id_set = set(duplicate_ids)
    question_reports: list[dict[str, Any]] = []
    structurally_usable: set[str] = set()
    for question in curriculum.get("questions", []):
        question_id = question.get("question_id")
        topic_id = question.get("topic_id")
        lesson_id = question.get("lesson_id")
        findings: list[str] = []
        for field in ("question_id", "topic_id", "lesson_id", "objective_id", "prompt", "expected_answer", "explanation", "question_type", "grading"):
            if not question.get(field):
                findings.append(f"missing_{field}")
        if not question.get("difficulty"):
            findings.append("missing_difficulty_metadata")
        elif question.get("difficulty") not in VALID_DIFFICULTIES:
            findings.append("unknown_difficulty_metadata")
        if question.get("question_type") not in VALID_QUESTION_TYPES:
            findings.append("unknown_question_type")
        if question_id in duplicate_id_set:
            findings.append("duplicate_question_id")

        topic = topics.get(topic_id)
        lesson = lessons.get(lesson_id)
        if topic is None:
            findings.append("unknown_topic_association")
        if lesson is None:
            findings.append("unknown_lesson_association")
        elif lesson.get("topic_id") != topic_id:
            findings.append("lesson_topic_mismatch")
        if topic is not None and lesson is not None and lesson.get("course_id") != topic["course_id"]:
            findings.append("lesson_course_mismatch")
        if topic is not None and question.get("objective_id") not in topic["objective_ids"]:
            findings.append("unknown_objective_association")

        options = question.get("options", [])
        option_ids = [item.get("option_id") for item in options]
        if any(not item.get("option_id") or not item.get("text") for item in options):
            findings.append("option_missing_identifier_or_text")
        grading = question.get("grading") or {}
        if grading.get("kind") == "choice":
            correct_ids = grading.get("correct_option_ids", [])
            if len(option_ids) != len(set(option_ids)):
                findings.append("duplicate_option_id")
            if not options:
                findings.append("choice_question_has_no_options")
            if not correct_ids or not set(correct_ids) <= set(option_ids):
                findings.append("invalid_correct_option_mapping")
            if question.get("question_type") == "single_choice" and len(correct_ids) != 1:
                findings.append("single_choice_answer_count_mismatch")
            if question.get("question_type") == "multiple_choice" and len(correct_ids) < 2:
                findings.append("multiple_choice_has_fewer_than_two_correct_options")
            if question.get("question_type") == "numeric":
                findings.append("question_type_grading_mismatch")
        elif grading.get("kind") == "numeric":
            if question.get("question_type") != "numeric":
                findings.append("question_type_grading_mismatch")
            if options:
                findings.append("numeric_question_has_choice_options")
            try:
                float(grading["expected_value"])
                float(grading.get("absolute_tolerance", 0))
                float(grading.get("relative_tolerance", 0))
            except (KeyError, TypeError, ValueError):
                findings.append("invalid_numeric_grading_metadata")
        else:
            findings.append("unknown_grading_definition")

        if topic is not None and question_id:
            topic["question_ids"].append(question_id)
            topic["question_objective_ids"].append(question.get("objective_id"))
        if not findings and question_id:
            structurally_usable.add(question_id)
        question_reports.append({
            "question_id": question_id,
            "topic_id": topic_id,
            "objective_id": question.get("objective_id"),
            "question_type": question.get("question_type"),
            "difficulty": question.get("difficulty"),
            "structural_status": "complete" if not findings else "manual_review_required",
            "findings": sorted(set(findings)),
            "cognitive_demand": "not_encoded_in_catalog",
            "ambiguity_status": "requires_human_content_review",
            "assessment_suitability": "pending_human_review",
        })

    topic_reports = []
    for topic_id, topic in topics.items():
        counts = Counter(topic["question_objective_ids"])
        question_count = len(topic["question_ids"])
        unique_objectives = len({value for value in topic["question_objective_ids"] if value})
        if question_count == 0:
            coverage = "no_linked_questions"
        elif question_count == 1:
            coverage = "single_item_only"
        elif unique_objectives < question_count:
            coverage = "repeated_objective_coverage"
        else:
            coverage = "multiple_objective_ids_content_diversity_unverified"
        topic_reports.append({
            "topic_id": topic_id,
            "topic_title": topic["topic_title"],
            "course_id": topic["course_id"],
            "lesson_id": topic["lesson_id"],
            "question_count": question_count,
            "distinct_question_count": len(set(topic["question_ids"])),
            "distinct_objective_count": unique_objectives,
            "objectives_with_multiple_questions": sorted(key for key, count in counts.items() if key and count > 1),
            "structurally_usable_question_ids": [
                item["question_id"] for item in question_reports
                if item["topic_id"] == topic_id and not item["findings"]
            ],
            "coverage_status": coverage,
            "assessment_suitability": "pending_human_review",
        })

    return {
        "report_version": "question-quality-audit-1.0",
        "source": "authored_student_studio_curriculum",
        "question_count": len(question_reports),
        "topic_count": len(topic_reports),
        "duplicate_question_ids": duplicate_ids,
        "structurally_complete_question_count": len(structurally_usable),
        "questions_requiring_manual_review": [item["question_id"] for item in question_reports],
        "questions_with_structural_issues": [item["question_id"] for item in question_reports if item["findings"]],
        "questions_with_missing_metadata": [
            item["question_id"] for item in question_reports
            if any(finding.startswith("missing_") or finding.startswith("unknown_") for finding in item["findings"])
        ],
        "questions_with_unencoded_cognitive_demand": [item["question_id"] for item in question_reports if item["cognitive_demand"] == "not_encoded_in_catalog"],
        "question_type_distribution": dict(sorted(Counter(str(item["question_type"]) for item in question_reports).items())),
        "difficulty_distribution": dict(sorted(Counter(str(item["difficulty"]) for item in question_reports).items())),
        "questions": question_reports,
        "topics": topic_reports,
        "limitations": [
            "Structural completeness does not establish wording clarity, correctness, conceptual validity, or pedagogical suitability.",
            "Cognitive demand and ambiguity are not encoded in the catalog and require human review.",
            "Distinct objective identifiers are catalog coverage metadata, not proof of distinct latent concepts.",
        ],
    }


def build_question_blueprint(curriculum: Mapping[str, Any]) -> dict[str, Any]:
    """Create a catalog-grounded draft blueprint with reviewer judgments unknown."""
    audit = audit_question_quality(curriculum)
    topic_context: dict[str, dict[str, Any]] = {}
    for subject in curriculum.get("subjects", []):
        for course in subject.get("courses", []):
            for unit in course.get("units", []):
                for topic in unit.get("topics", []):
                    topic_context[topic["topic_id"]] = {
                        "topic_title": topic["title"],
                        "subject_id": subject["subject_id"],
                        "course_id": course["course_id"],
                        "unit_id": unit["unit_id"],
                        "lesson_id": topic.get("lesson_id"),
                        "objectives": {item["objective_id"]: item["text"] for item in topic.get("learning_objectives", [])},
                        "question_ids": [],
                    }
    for question in curriculum.get("questions", []):
        context = topic_context.get(question.get("topic_id"))
        if context is not None:
            context["question_ids"].append(question.get("question_id"))
    audit_by_id = {item["question_id"]: item for item in audit["questions"]}

    blueprint_questions = []
    for question in curriculum.get("questions", []):
        topic_id = question.get("topic_id")
        context = topic_context.get(topic_id, {})
        objective_id = question.get("objective_id")
        question_id = question.get("question_id")
        other_same_objective = [
            other.get("question_id") for other in curriculum.get("questions", [])
            if other.get("question_id") != question_id
            and other.get("topic_id") == topic_id
            and other.get("objective_id") == objective_id
        ]
        other_same_topic = [
            other_id for other_id in context.get("question_ids", [])
            if other_id and other_id != question_id and other_id not in other_same_objective
        ]
        grading = question.get("grading", {})
        answer_definition = {
            "grading": grading,
            "expected_answer": question.get("expected_answer"),
        }
        blueprint_questions.append({
            "question_id": question_id,
            "topic_id": topic_id,
            "topic_title": context.get("topic_title"),
            "subject_id": context.get("subject_id"),
            "course_id": context.get("course_id"),
            "unit_id": context.get("unit_id"),
            "lesson_id": question.get("lesson_id"),
            "learning_objective_id": objective_id,
            "catalog_objective_text": context.get("objectives", {}).get(objective_id),
            "question_format": question.get("question_type", "unknown"),
            "wording": question.get("prompt"),
            "answer_options": question.get("options", []),
            "correct_answer_definition": answer_definition,
            "intended_cognitive_demand": {
                "value": "unknown",
                "reviewer_options": list(COGNITIVE_DEMAND_CATEGORIES),
                "status": "pending_expert_review",
            },
            "intended_knowledge_or_skill": {
                "value": context.get("objectives", {}).get(objective_id),
                "source": "authored_catalog_learning_objective" if objective_id in context.get("objectives", {}) else "unknown",
                "status": "provisional_alignment_pending_expert_review",
            },
            "assessment_purpose": {
                "current_use": "student_studio_practice",
                "diagnostic_suitability": "unknown_pending_expert_review",
            },
            "difficulty": {
                "catalog_label": question.get("difficulty") or "unknown",
                "calibration_status": "unvalidated_catalog_label" if question.get("difficulty") else "unknown",
            },
            "explanation": {
                "available": bool(question.get("explanation")),
                "text": question.get("explanation"),
            },
            "potential_ambiguity": "unknown_pending_expert_review",
            "conceptual_overlap": {
                "same_objective_question_ids": other_same_objective,
                "other_same_topic_question_ids": other_same_topic,
                "review_status": "pending_expert_review",
            },
            "human_review": {
                "status": "pending_review",
                "reviewer_comments": [],
                "reviewer_id": None,
                "reviewed_at": None,
            },
            "metadata_completeness": {
                "structurally_complete": audit_by_id.get(question_id, {}).get("structural_status") == "complete",
                "structural_findings": audit_by_id.get(question_id, {}).get("findings", []),
                "unknown_or_unreviewed_fields": [
                    "intended_cognitive_demand", "difficulty_calibration", "ambiguity_review",
                    "conceptual_validity", "diagnostic_suitability", "psychometric_quality",
                ],
            },
        })
    blueprint = {
        "blueprint_version": "question-blueprint-1.0",
        "curriculum_version": curriculum.get("curriculum_version", "unknown"),
        "source": "authored_student_studio_curriculum",
        "review_status_values": list(QUESTION_REVIEW_STATUSES),
        "cognitive_demand_values": list(COGNITIVE_DEMAND_CATEGORIES),
        "questions": blueprint_questions,
        "limitations": [
            "This draft copies catalog facts and marks expert judgments unknown or pending; it records no completed review.",
            "Catalog objective alignment is provisional and requires expert confirmation.",
            "Difficulty labels are authored metadata, not calibrated item difficulty.",
        ],
    }
    validate_question_blueprint(blueprint, curriculum)
    return blueprint


def validate_question_blueprint(blueprint: Mapping[str, Any], curriculum: Mapping[str, Any]) -> None:
    """Reject duplicate, missing, or unsupported question-review blueprint data."""
    questions = blueprint.get("questions", [])
    expected_ids = [item.get("question_id") for item in curriculum.get("questions", [])]
    actual_ids = [item.get("question_id") for item in questions]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("question blueprint contains duplicate question IDs")
    if actual_ids != expected_ids:
        raise ValueError("question blueprint inventory/order does not match the authored catalog")
    topic_objectives = {
        topic["topic_id"]: {objective["objective_id"] for objective in topic.get("learning_objectives", [])}
        for subject in curriculum.get("subjects", [])
        for course in subject.get("courses", [])
        for unit in course.get("units", [])
        for topic in unit.get("topics", [])
    }
    for question in questions:
        topic_id = question.get("topic_id")
        objective_id = question.get("learning_objective_id")
        if topic_id not in topic_objectives or objective_id not in topic_objectives[topic_id]:
            raise ValueError(f"question blueprint has an invalid topic/objective reference for {question.get('question_id')}")
        if question.get("human_review", {}).get("status") not in QUESTION_REVIEW_STATUSES:
            raise ValueError(f"question blueprint has an unsupported review status for {question.get('question_id')}")
        demand = question.get("intended_cognitive_demand", {}).get("value")
        if demand != "unknown" and demand not in COGNITIVE_DEMAND_CATEGORIES:
            raise ValueError(f"question blueprint has an unsupported cognitive-demand value for {question.get('question_id')}")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def analyze_student_studio_attempts(
    *,
    question_quality: Mapping[str, Any],
    attempts: Iterable[Mapping[str, Any]],
    thresholds: Sequence[int] = (1, 2, 3, 5),
) -> dict[str, Any]:
    """Produce deterministic aggregate diagnostics without learner-level output."""
    if any(value < 1 for value in thresholds):
        raise ValueError("distinct-question thresholds must be positive integers")
    topic_ids = [item["topic_id"] for item in question_quality["topics"]]
    question_to_topic = {
        item["question_id"]: item["topic_id"]
        for item in question_quality["questions"] if item.get("question_id")
    }
    usable_question_to_topic = {
        question_id: item["topic_id"]
        for item in question_quality["topics"]
        for question_id in item.get("structurally_usable_question_ids", [])
    }
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    question_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    excluded_unmapped = 0
    excluded_non_studio = 0
    excluded_question_quality = 0
    excluded_invalid_provenance = 0
    attempt_count = 0
    correct_count = 0
    profile_ids: set[str] = set()
    evidence_status_counts: Counter[str] = Counter()
    for raw in attempts:
        attempt_count += 1
        if raw.get("source_dataset") != "mcp-ri-student-studio":
            excluded_non_studio += 1
            continue
        profile_id = str(raw.get("profile_id", ""))
        topic_id = str(raw.get("topic_id", ""))
        question_id = str(raw.get("question_id", ""))
        if profile_id:
            profile_ids.add(profile_id)
        evidence_status = str(raw.get("evidence_status", "missing"))
        evidence_status_counts[evidence_status] += 1
        if evidence_status == "invalid":
            excluded_invalid_provenance += 1
            continue
        if question_to_topic.get(question_id) == topic_id and usable_question_to_topic.get(question_id) != topic_id:
            excluded_question_quality += 1
            continue
        if not profile_id or usable_question_to_topic.get(question_id) != topic_id:
            excluded_unmapped += 1
            continue
        record = {
            "question_id": question_id,
            "is_correct": bool(raw.get("is_correct")),
            "event_timestamp": raw.get("event_timestamp"),
        }
        grouped[(profile_id, topic_id)].append(record)
        question_groups[(profile_id, topic_id, question_id)].append(record)
        correct_count += int(record["is_correct"])

    per_topic = []
    topic_profile_groups = {topic_id: [] for topic_id in topic_ids}
    for topic_id in topic_ids:
        questions = [item for item in question_quality["questions"] if item["topic_id"] == topic_id]
        q_stats = []
        for question in questions:
            grouped_rows = [
                (profile, values) for (profile, topic, qid), values in question_groups.items()
                if topic == topic_id and qid == question["question_id"]
            ]
            rows = [item for _, values in grouped_rows for item in values]
            q_stats.append({
                "question_id": question["question_id"],
                "attempt_count": len(rows),
                "correct_count": sum(item["is_correct"] for item in rows),
                "incorrect_count": sum(not item["is_correct"] for item in rows),
                "distinct_profile_count": len({profile for (profile, topic, qid) in question_groups if topic == topic_id and qid == question["question_id"]}),
                "repeat_attempt_count": sum(max(0, len(values) - 1) for _, values in grouped_rows),
            })
        observed_groups = [(key[0], values) for key, values in grouped.items() if key[1] == topic_id]
        topic_profile_groups[topic_id] = observed_groups
        topic_times = [parsed for _, values in observed_groups for item in values if (parsed := _parse_time(item["event_timestamp"]))]
        time_span_seconds = (
            max(topic_times).timestamp() - min(topic_times).timestamp()
            if len(topic_times) > 1 else 0.0 if topic_times else None
        )
        per_topic.append({
            "topic_id": topic_id,
            "catalog_question_count": len(questions),
            "question_statistics": q_stats,
            "attempt_count": sum(len(values) for _, values in observed_groups),
            "distinct_profile_count": len({profile for profile, _ in observed_groups}),
            "distinct_question_count": len({item["question_id"] for _, values in observed_groups for item in values}),
            "repeat_attempt_count": sum(max(0, len(values) - len({item["question_id"] for item in values})) for _, values in observed_groups),
            "event_time_range": (
                {"earliest": min(topic_times).isoformat(), "latest": max(topic_times).isoformat()}
                if topic_times else None
            ),
            "missing_timestamp_count": sum(
                not item["event_timestamp"] for _, values in observed_groups for item in values
            ),
            "questions_with_outcome_changes": sum(
                len({item["is_correct"] for item in values}) > 1
                for (profile, observed_topic, question_id), values in question_groups.items()
                if observed_topic == topic_id
            ),
            "unobserved": not observed_groups,
            "event_time_span_seconds": time_span_seconds,
            "recency_policy": "timestamps_descriptive_only_no_expiration_or_weighting",
        })

    threshold_reports = []
    confidence_counts: Counter[str] = Counter()
    for threshold in sorted(set(thresholds)):
        classifications: Counter[str] = Counter()
        eligible_units = len(profile_ids) * len(topic_ids)
        for topic_id, profile_groups in topic_profile_groups.items():
            rows_by_profile = dict(profile_groups)
            for profile_id in profile_ids:
                rows = rows_by_profile.get(profile_id, [])
                question_count = len({item["question_id"] for item in rows})
                outcomes = {item["is_correct"] for item in rows}
                per_question = defaultdict(set)
                for item in rows:
                    per_question[item["question_id"]].add(item["is_correct"])
                if len(outcomes) > 1 or any(len(values) > 1 for values in per_question.values()):
                    label = "conflicting_evidence"
                elif not rows:
                    label = "insufficient_evidence"
                elif question_count < threshold:
                    label = "insufficient_evidence"
                elif outcomes == {True}:
                    label = "supported_response_pattern"
                elif outcomes == {False}:
                    label = "developing_response_pattern"
                else:
                    label = "insufficient_evidence"
                classifications[label] += 1
                if threshold == 2:
                    confidence_counts["low"] += int(label != "insufficient_evidence")
                    confidence_counts["insufficient"] += int(label == "insufficient_evidence")
        threshold_reports.append({
            "minimum_distinct_questions": threshold,
            "observed_profile_topic_units": eligible_units,
            "classification_counts": dict(sorted(classifications.items())),
            "interpretation": "descriptive_sensitivity_only_not_threshold_validation",
        })

    return {
        "report_version": "student-studio-evidence-validation-1.0",
        "data_source": "student_studio_tables_only",
        "status": "descriptive_only" if attempt_count else "no_observations",
        "population": {
            "unique_profile_count": len(profile_ids),
            "attempt_rows_read": attempt_count,
            "catalog_mapped_attempt_count": attempt_count - excluded_unmapped - excluded_non_studio - excluded_question_quality - excluded_invalid_provenance,
            "excluded_unmapped_attempt_count": excluded_unmapped,
            "excluded_non_student_studio_count": excluded_non_studio,
            "excluded_question_quality_count": excluded_question_quality,
            "excluded_invalid_provenance_count": excluded_invalid_provenance,
            "correct_response_count": correct_count,
            "incorrect_response_count": attempt_count - excluded_unmapped - excluded_non_studio - excluded_question_quality - excluded_invalid_provenance - correct_count,
        },
        "evidence_provenance": {
            "canonical_evidence_valid_count": evidence_status_counts["valid"],
            "canonical_evidence_missing_count": evidence_status_counts["missing"],
            "canonical_evidence_invalid_count": evidence_status_counts["invalid"],
            "interpretation": "A canonical link is valid only when source dataset, source event, topic, and question match the Student Studio attempt.",
        },
        "topic_statistics": per_topic,
        "threshold_sensitivity": threshold_reports,
        "confidence_category_distribution_at_threshold_2": dict(sorted(confidence_counts.items())),
        "recency_analysis": {
            "computed": True,
            "method": "descriptive timestamp ranges and same-question repeat histories; no recent/historical cutoff",
            "time_decay_or_expiration_applied": False,
            "limitations": "No defensible age threshold or outcome target is available to evaluate recency weighting.",
        },
        "validation_claims": {
            "descriptive_statistics": "computed",
            "internal_consistency_or_reliability": "not_established",
            "predictive_performance": "not_evaluated_no_independent_targets",
            "external_validity": "not_evaluated_no_independent_knowledge_measure",
        },
        "limitations": [
            "Aggregates contain no learner or attempt identifiers.",
            "Repeated responses to one question do not increase distinct-question coverage.",
            "Threshold scenarios are descriptive sensitivity checks, not evidence that any threshold is valid.",
            "Student Studio's local demo profile is not an authenticated multi-learner sample.",
        ],
    }


def read_student_studio_attempts_read_only(database_path: str | Path) -> dict[str, Any]:
    """Read aggregate-ready attempt rows using SQLite read-only/query-only mode."""
    path = Path(database_path).expanduser().resolve(strict=True)
    uri = path.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "studio_learning_attempts" not in tables:
            return {"available": False, "reason": "Student Studio attempt table is absent.", "attempts": []}
        available = {row[1] for row in connection.execute("PRAGMA table_info(studio_learning_attempts)")}
        needed = {"attempt_id", "profile_id", "topic_id", "question_id", "is_correct", "event_timestamp", "event_sequence"}
        if not needed <= available:
            return {"available": False, "reason": "Student Studio attempt table is missing required columns.", "attempts": []}
        has_evidence = "studio_evidence_records" in tables
        select_evidence = (
            ", evidence.evidence_record"
            if has_evidence else ", NULL"
        )
        evidence_join = (
            " LEFT JOIN studio_evidence_records AS evidence "
            "ON evidence.source_event_id = attempt.attempt_id "
            "AND evidence.profile_id = attempt.profile_id"
            if has_evidence else ""
        )
        rows = connection.execute(
            "SELECT attempt.attempt_id, attempt.profile_id, attempt.topic_id, attempt.question_id, "
            "attempt.is_correct, attempt.event_timestamp" + select_evidence +
            " FROM studio_learning_attempts AS attempt" + evidence_join +
            " ORDER BY attempt.profile_id, attempt.event_sequence"
        ).fetchall()
        attempts = []
        for row in rows:
            attempt_id, profile_id, topic_id, question_id, is_correct, timestamp, evidence_raw = row
            evidence_status = "missing"
            if evidence_raw:
                try:
                    record = json.loads(evidence_raw)
                except (TypeError, json.JSONDecodeError):
                    record = {}
                provenance = record.get("provenance", {})
                content = record.get("content", {})
                evidence_status = "valid" if (
                    provenance.get("source_dataset") == "mcp-ri-student-studio"
                    and provenance.get("source_record_id") == attempt_id
                    and content.get("topic_id") == topic_id
                    and content.get("question_id") == question_id
                ) else "invalid"
            attempts.append({
                "profile_id": profile_id, "topic_id": topic_id, "question_id": question_id,
                "is_correct": bool(is_correct), "event_timestamp": timestamp,
                "source_dataset": "mcp-ri-student-studio", "evidence_status": evidence_status,
            })
        return {
            "available": True,
            "reason": "Read Student Studio attempt rows in SQLite read-only/query-only mode.",
            "attempts": attempts,
        }
    finally:
        connection.close()
