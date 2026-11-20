"""Transparent, uncalibrated interpretation of Student Studio answer evidence."""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from typing import Any, Literal, Mapping, Sequence


ASSESSMENT_METHOD_VERSION = "studio-binary-evidence-1.1"


@dataclass(frozen=True)
class StudentStudioObservation:
    attempt_id: str
    evidence_id: str | None
    topic_id: str
    question_id: str
    is_correct: bool
    event_timestamp: str
    source_dataset: str | None
    source_record_id: str | None


def _activity(
    *, topic_id: str, topic_title: str, lesson_id: str | None, unanswered_question_ids: Sequence[str],
    action: str, reason: str,
) -> dict[str, Any]:
    question_id = unanswered_question_ids[0] if action == "diagnostic_question" and unanswered_question_ids else None
    if action == "diagnostic_question" and question_id is None:
        action = "none"
        reason = "No unattempted curated question is available for this topic."
    return {
        "action": action,
        "topic_id": topic_id,
        "lesson_id": lesson_id if action == "review_lesson" else None,
        "question_id": question_id,
        "title": (
            f"Try a diagnostic question for {topic_title}" if question_id else
            (f"Review the lesson for {topic_title}" if action == "review_lesson" else None)
        ),
        "reason": reason,
    }


def assess_topic_knowledge(
    *,
    topic_id: str,
    topic_title: str,
    lesson_id: str | None,
    curated_question_ids: Sequence[str],
    observations: Sequence[StudentStudioObservation],
    retrieval_notes: Sequence[str] = (),
    question_quality_status: Literal["unreviewed", "structurally_incomplete"] = "unreviewed",
) -> dict[str, Any]:
    """Apply fixed qualitative rules; no numeric mastery score is computed.

    Two distinct curated questions are the minimum for a supported or
    developing interpretation. This is a conservative engineering heuristic,
    not a validated educational threshold. A mixed result is always conflicting.
    """
    relevant = [item for item in observations if item.topic_id == topic_id and item.question_id in curated_question_ids]
    unique_questions = {item.question_id for item in relevant}
    correct = [item for item in relevant if item.is_correct]
    incorrect = [item for item in relevant if not item.is_correct]
    distinct_count = len(unique_questions)
    outcomes_by_question: dict[str, set[bool]] = defaultdict(set)
    for observation in relevant:
        outcomes_by_question[observation.question_id].add(observation.is_correct)
    changed_questions = sorted(question_id for question_id, outcomes in outcomes_by_question.items() if len(outcomes) > 1)

    if correct and incorrect:
        status = "conflicting_evidence"
        confidence = "low"
        supporting = []
        contradictory = relevant
        explanation = "Saved responses include both correct and incorrect outcomes; the observations conflict and do not establish a stable understanding estimate."
        action = _activity(
            topic_id=topic_id, topic_title=topic_title, lesson_id=lesson_id,
            unanswered_question_ids=[qid for qid in curated_question_ids if qid not in unique_questions],
            action="diagnostic_question",
            reason="A new curated question can provide another observation; prior responses conflict.",
        )
    elif distinct_count >= 2 and correct:
        status = "supported_understanding"
        confidence = "low"
        supporting = correct
        contradictory = []
        explanation = "Responses to at least two distinct curated questions were correct. This supports performance on those items, not general mastery."
        action = _activity(
            topic_id=topic_id, topic_title=topic_title, lesson_id=lesson_id, unanswered_question_ids=[], action="none",
            reason="No additional activity is selected solely from these correct responses.",
        )
    elif distinct_count >= 2 and incorrect:
        status = "developing_understanding"
        confidence = "low"
        supporting = incorrect
        contradictory = []
        explanation = "Responses to at least two distinct curated questions were incorrect. This supports offering review, but does not prove the learner lacks topic knowledge."
        action = _activity(
            topic_id=topic_id, topic_title=topic_title, lesson_id=lesson_id, unanswered_question_ids=[],
            action="review_lesson" if lesson_id else "none",
            reason="Multiple distinct responses were incorrect; reviewing the existing lesson is available." if lesson_id else "No linked lesson is available for review.",
        )
    elif relevant:
        status = "needs_further_assessment"
        confidence = "low"
        supporting = relevant
        contradictory = []
        explanation = "There are saved responses, but they cover fewer than two distinct curated questions; the sample is too small for a topic-level interpretation."
        action = _activity(
            topic_id=topic_id, topic_title=topic_title, lesson_id=lesson_id,
            unanswered_question_ids=[qid for qid in curated_question_ids if qid not in unique_questions],
            action="diagnostic_question",
            reason="A different curated question is available to gather more evidence.",
        )
    else:
        status = "insufficient_evidence"
        confidence = "insufficient"
        supporting = []
        contradictory = []
        explanation = "No relevant Student Studio response was found; the learner's current understanding is unknown."
        action = _activity(
            topic_id=topic_id, topic_title=topic_title, lesson_id=lesson_id,
            unanswered_question_ids=list(curated_question_ids), action="diagnostic_question",
            reason="This topic has no saved response evidence; an existing curated question can serve as a diagnostic.",
        )

    timestamps = sorted(item.event_timestamp for item in relevant if item.event_timestamp)
    confidence_basis = (
        ["No matching observations are available; confidence is insufficient."]
        if not relevant else [
            f"The available history covers {distinct_count} distinct curated question(s) across {len(relevant)} response attempt(s).",
            (
                f"Canonical Phase 10 evidence is linked and provenance-checked for {sum(item.evidence_id is not None for item in relevant)} of {len(relevant)} observations."
            ),
            (
                "One or more catalog questions failed structural checks and were excluded from this interpretation."
                if question_quality_status == "structurally_incomplete" else
                "Question content has no recorded human quality review or psychometric validation."
            ),
            "Exact topic and question identifiers support traceability; no validated skill/concept mapping exists.",
            "Historical timestamps are descriptive; recency is not weighted or used as an expiration rule.",
        ]
    )
    return {
        "topic_id": topic_id,
        "topic_title": topic_title,
        "status": status,
        "confidence": confidence,
        "confidence_basis": confidence_basis,
        "question_quality_status": question_quality_status,
        "evidence_count": len(relevant),
        "distinct_question_count": distinct_count,
        "repeat_attempt_count": max(0, len(relevant) - distinct_count),
        "questions_with_outcome_changes": changed_questions,
        "supporting_attempt_ids": sorted({item.attempt_id for item in supporting}),
        "supporting_evidence_ids": sorted({item.evidence_id for item in supporting if item.evidence_id}),
        "contradictory_attempt_ids": sorted({item.attempt_id for item in contradictory}),
        "contradictory_evidence_ids": sorted({item.evidence_id for item in contradictory if item.evidence_id}),
        "observations": [{
            "attempt_id": item.attempt_id,
            "evidence_id": item.evidence_id,
            "question_id": item.question_id,
            "outcome": "correct" if item.is_correct else "incorrect",
            "event_timestamp": item.event_timestamp,
            "source_dataset": item.source_dataset,
            "source_record_id": item.source_record_id,
        } for item in relevant],
        "observed_time_range": {"earliest": timestamps[0], "latest": timestamps[-1]} if timestamps else None,
        "retrieval_notes": list(retrieval_notes),
        "explanation": explanation,
        "uncertainty": [
            "This rule-based interpretation is not scientifically validated or calibrated.",
            "Question correctness is one observed response and does not establish mastery or lack of knowledge.",
            "No recency decay is applied; timestamps are provided for context only.",
        ],
        "recommended_activity": action,
    }


def build_evidence_grounded_assessment(
    *,
    learner_profile_id: str,
    behavioral_state_version: int | None,
    relevant_topics: Sequence[Mapping[str, Any]],
    observations_by_topic: Mapping[str, Sequence[StudentStudioObservation]],
    retrieval_notes_by_topic: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    topics = [
        assess_topic_knowledge(
            topic_id=str(topic["topic_id"]),
            topic_title=str(topic["topic_title"]),
            lesson_id=topic.get("lesson_id"),
            curated_question_ids=topic.get("question_ids", []),
            observations=observations_by_topic.get(str(topic["topic_id"]), []),
            retrieval_notes=(retrieval_notes_by_topic or {}).get(str(topic["topic_id"]), []),
            question_quality_status=topic.get("question_quality_status", "unreviewed"),
        )
        for topic in relevant_topics
    ]
    if not topics:
        status = "not_available"
        reason = "No relevant catalog topics were mapped to the learning goal, so there is no justified topic mapping for learner evidence."
        source = None
    elif not any(item["evidence_count"] for item in topics):
        status = "insufficient_evidence"
        reason = "Relevant catalog topics were identified, but no matching Student Studio response evidence is available."
        source = "student_studio_attempts"
    else:
        status = "available"
        reason = "Assessment uses only exact Student Studio topic and curated-question mappings from saved attempts."
        source = "student_studio_attempts"
    return {
        "schema_version": "1.0",
        "method_version": ASSESSMENT_METHOD_VERSION,
        "status": status,
        "source": source,
        "learner_profile_id": learner_profile_id,
        "behavioral_state_version": behavioral_state_version,
        "topics": topics,
        "reason": reason,
        "limitations": [
            "Knowledge categories are provisional qualitative interpretations of binary question outcomes, not mastery scores.",
            "Two distinct curated questions are a conservative engineering heuristic, not an empirically validated threshold.",
            "Evidence is limited to the local Student Studio profile and does not include EdNet research records.",
            "Only topics with exact catalog topic and question identifiers are assessed; no semantic skill mapping is inferred.",
        ],
    }
