from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from mcp_ri.api.learning_schemas import LearningPlanRequest
from mcp_ri.api.learning_plan_service import LearningPlanService
from mcp_ri.api.learning_routes import learning_router
from mcp_ri.api.persistence import Base
from mcp_ri.api.persistence import (
    StudentBehavioralStateVersion,
    StudentLearningAttempt,
    StudentStudioEvidenceRecord,
    StudentStudioProfile,
    utc_now,
)
from mcp_ri.api.learning_service import curriculum
from mcp_ri.learning.planning import build_rule_based_learning_plan
from mcp_ri.learning.knowledge_assessment import StudentStudioObservation, assess_topic_knowledge
from mcp_ri.learning.providers import (
    LearningProviderUnavailable,
    UnavailableStructuredLearningProvider,
)


@pytest.fixture
def plan_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _small_curriculum() -> dict:
    topics = [
        {
            "topic_id": "advanced-topic", "title": "Advanced Concept", "description": "Apply the concept.",
            "learning_objectives": [{"objective_id": "advanced-objective", "text": "Apply the concept."}],
            "estimated_minutes": 12, "prerequisites_status": "validated",
            "prerequisite_topic_ids": ["foundation-topic"], "lesson_id": "advanced-lesson",
        },
        {
            "topic_id": "foundation-topic", "title": "Foundation Concept", "description": "Define the concept.",
            "learning_objectives": [{"objective_id": "foundation-objective", "text": "Define the concept."}],
            "estimated_minutes": 8, "prerequisites_status": "not_established",
            "prerequisite_topic_ids": [], "lesson_id": "foundation-lesson",
        },
    ]
    return {
        "curriculum_version": "test-1",
        "subjects": [{
            "subject_id": "test-subject", "title": "Test Subject", "description": "Test content.",
            "courses": [{
                "course_id": "test-course", "title": "Test Course", "description": "Test content.",
                "units": [{"unit_id": "test-unit", "title": "Test Unit", "description": "Test content.", "topics": topics}],
            }],
        }],
        "lessons": [
            {"lesson_id": topic["lesson_id"], "topic_id": topic["topic_id"], "course_id": "test-course", "estimated_minutes": topic["estimated_minutes"]}
            for topic in topics
        ],
        "questions": [{
            "question_id": "advanced-q1", "lesson_id": "advanced-lesson", "topic_id": "advanced-topic",
            "question_type": "single_choice",
        }],
    }


def test_learning_goal_validation_normalizes_and_rejects_blank_goals():
    assert LearningPlanRequest(learning_goal="  Bayes   theorem  ").learning_goal == "Bayes theorem"
    with pytest.raises(ValueError):
        LearningPlanRequest(learning_goal="   ")
    with pytest.raises(ValueError):
        LearningPlanRequest(learning_goal="x" * 501)


def test_api_maps_goal_to_curated_topic_and_explicit_rule_based_fallback(plan_session):
    plan = LearningPlanService().preview(plan_session, LearningPlanRequest(learning_goal="Learn Bayes theorem"))
    assert plan["status"] == "mapped"
    assert plan["generation_mode"] == "rule_based"
    assert plan["persisted"] is False
    assert plan["provider"]["status"] == "unavailable"
    assert plan["provider"]["invoked"] is False
    assert plan["ordered_topic_ids"] == ["bayes-theorem"]
    assert plan["learning_sequence"][0]["lesson_id"] == "bayes-theorem"
    assert plan["learning_sequence"][0]["assessment"]["source"] == "curated_questions"
    assert plan["learning_sequence"][0]["assessment"]["question_ids"] == [
        "bayes-theorem-q1", "bayes-theorem-q2",
    ]
    assert "AI provider" in plan["provider"]["reason"]


def test_validated_prerequisites_are_expanded_and_ordered_before_target():
    plan = build_rule_based_learning_plan(
        learning_goal="Advanced",
        curriculum=_small_curriculum(),
    )
    assert plan["ordered_topic_ids"] == ["foundation-topic", "advanced-topic"]
    assert [step["inclusion_reason"] for step in plan["learning_sequence"]] == [
        "validated_prerequisite", "goal_match",
    ]
    assert plan["prerequisites"]["status"] == "identified"
    assert plan["learning_sequence"][1]["prerequisite_topic_ids"] == ["foundation-topic"]
    assert plan["learning_sequence"][1]["assessment"]["evaluation_mode"] == "backend_scored_choice_or_numeric"


def test_unvalidated_prerequisites_are_not_invented_and_catalog_order_is_kept(plan_session):
    plan = LearningPlanService().preview(plan_session, LearningPlanRequest(learning_goal="Probability"))
    assert plan["ordered_topic_ids"] == [
        "introduction-to-probability", "conditional-probability", "bayes-theorem",
        "random-variables", "expected-value",
    ]
    assert plan["prerequisites"]["status"] == "not_established"
    assert plan["prerequisites"]["relationships"] == []
    assert all(step["prerequisite_topic_ids"] == [] for step in plan["learning_sequence"])
    assert any("Prerequisites are not established" in item for item in plan["missing_information"])


def test_empty_subject_reports_catalog_gap_without_fabricating_a_sequence(plan_session):
    plan = LearningPlanService().preview(plan_session, LearningPlanRequest(learning_goal="Finance"))
    assert plan["status"] == "unsupported"
    assert plan["modules"] == []
    assert plan["learning_sequence"] == []
    assert plan["mapping"]["catalog_gaps"]
    assert any("no curated courses" in item for item in plan["missing_information"])


def test_unsupported_goal_is_reported_without_fabricated_content(plan_session):
    plan = LearningPlanService().preview(plan_session, LearningPlanRequest(learning_goal="Marine biology"))
    assert plan["status"] == "unsupported"
    assert plan["learning_sequence"] == []
    assert "marine" in plan["mapping"]["unmatched_goal_terms"]
    assert plan["estimated_minutes"] == 0


def test_provider_unavailability_uses_rule_based_fallback():
    provider = UnavailableStructuredLearningProvider()
    availability = provider.availability("learning_plan")
    plan = build_rule_based_learning_plan(
        learning_goal="Bayes theorem",
        curriculum={"curriculum_version": "test", "subjects": [], "lessons": [], "questions": []},
        provider_availability=availability,
    )
    assert plan["generation_mode"] == "rule_based"
    assert plan["provider"]["status"] == "unavailable"
    assert plan["provider"]["invoked"] is False
    with pytest.raises(LearningProviderUnavailable):
        provider.generate_json(capability="learning_plan", context={})


def test_plan_endpoint_is_registered_in_api_contract():
    app = FastAPI()
    app.include_router(learning_router)
    schema = app.openapi()
    assert "/api/v1/studio/learning-plans/preview" in schema["paths"]
    plan_schema = schema["components"]["schemas"]["LearningPlanData"]
    assert "evidence_based_assessment" in plan_schema["properties"]
    assessment_schema = schema["components"]["schemas"]["EvidenceGroundedKnowledgeAssessment"]
    assert assessment_schema["properties"]["method_version"]["default"] == "studio-binary-evidence-1.1"


def test_existing_behavioral_summary_is_reused_read_only(plan_session):
    from mcp_ri.learning.planning import build_rule_based_learning_plan
    topic_id = "introduction-to-probability"
    result = build_rule_based_learning_plan(
        learning_goal="Probability", curriculum=curriculum().model_dump(mode="json"),
        state_version=4,
        topic_state={topic_id: {"attempts": 2, "correct": 1, "incorrect": 1, "evidence_sufficiency": "low"}},
        topic_evidence_ids={topic_id: ["evidence-1"]},
    )
    assert result["knowledge_assessment"]["status"] == "available"
    summary = next(item for item in result["knowledge_assessment"]["topic_summaries"] if item["topic_id"] == topic_id)
    assert summary["attempts"] == 2
    assert summary["supporting_evidence_ids"] == ["evidence-1"]
    assert summary["interpretation"] == "descriptive_response_history_only"


def test_preview_does_not_mutate_curriculum_fixture():
    curriculum = _small_curriculum()
    original = deepcopy(curriculum)
    build_rule_based_learning_plan(learning_goal="Advanced concept", curriculum=curriculum)
    assert curriculum == original


def _save_attempt(
    session: Session, *, topic_id: str, question_id: str, correct: bool,
    event_sequence: int, profile_id: str = "studio-local-demo", event_timestamp: str | None = None,
) -> tuple[str, str]:
    attempt_id = f"attempt-{profile_id}-{event_sequence}"
    evidence_id = f"evidence-{profile_id}-{event_sequence}"
    timestamp = event_timestamp or f"2026-11-{event_sequence:02d}T10:00:00+00:00"
    if session.get(StudentStudioProfile, profile_id) is None:
        session.add(StudentStudioProfile(profile_id=profile_id, profile_type="local_demo", created_at=timestamp))
    session.add(StudentLearningAttempt(
        attempt_id=attempt_id, profile_id=profile_id, session_id=None,
        submission_id=f"submission-{profile_id}-{event_sequence}",
        course_id="probability-foundations", topic_id=topic_id,
        lesson_id=topic_id, question_id=question_id, attempt_number=1,
        event_sequence=event_sequence, submitted_response={"option_ids": ["a"]},
        is_correct=correct, feedback={}, content_version="1.0.0",
        event_timestamp=timestamp, evidence_record=None,
        processing_status="evidence_recorded", behavioral_state_version=1,
    ))
    session.flush()
    session.add(StudentStudioEvidenceRecord(
        evidence_id=evidence_id, profile_id=profile_id, source_event_id=attempt_id,
        topic_id=topic_id, lesson_id=topic_id, question_id=question_id,
        evidence_record={
            "schema_version": "1.0",
            "provenance": {"source_dataset": "mcp-ri-student-studio", "source_record_id": attempt_id},
            "content": {"topic_id": topic_id, "question_id": question_id, "correctness": int(correct)},
        },
        created_at=timestamp,
    ))
    if profile_id == "studio-local-demo":
        session.merge(StudentBehavioralStateVersion(
            profile_id=profile_id, state_version=1, source_event_sequence=event_sequence,
            last_evidence_id=evidence_id, evidence_count=event_sequence,
            previous_state_version=None, state_timestamp=timestamp,
            state_data={"topic_states": []}, created_at=timestamp,
        ))
    return attempt_id, evidence_id


def _preview_with_probability_evidence(session: Session) -> dict:
    return LearningPlanService().preview(session, LearningPlanRequest(learning_goal="Probability"))


def _assessment_for(plan: dict, topic_id: str = "introduction-to-probability") -> dict:
    return next(item for item in plan["evidence_based_assessment"]["topics"] if item["topic_id"] == topic_id)


def test_no_evidence_is_unknown_and_recommends_only_existing_diagnostic(plan_session):
    attempts_before = plan_session.scalar(select(func.count()).select_from(StudentLearningAttempt))
    evidence_before = plan_session.scalar(select(func.count()).select_from(StudentStudioEvidenceRecord))
    states_before = plan_session.scalar(select(func.count()).select_from(StudentBehavioralStateVersion))
    plan = _preview_with_probability_evidence(plan_session)
    assessment = _assessment_for(plan)
    assert assessment["status"] == "insufficient_evidence"
    assert assessment["confidence"] == "insufficient"
    assert assessment["evidence_count"] == 0
    assert assessment["supporting_evidence_ids"] == []
    assert assessment["recommended_activity"]["action"] == "diagnostic_question"
    assert assessment["recommended_activity"]["question_id"] == "introduction-to-probability-q1"
    assert "no knowledge gap is inferred" in next(
        item for item in plan["missing_information"] if "unassessed" in item
    )
    assert plan["evidence_based_assessment"]["status"] == "insufficient_evidence"
    assert plan_session.scalar(select(func.count()).select_from(StudentLearningAttempt)) == attempts_before
    assert plan_session.scalar(select(func.count()).select_from(StudentStudioEvidenceRecord)) == evidence_before
    assert plan_session.scalar(select(func.count()).select_from(StudentBehavioralStateVersion)) == states_before


def test_consistent_positive_evidence_keeps_provenance_and_preview_order(plan_session):
    a1, e1 = _save_attempt(
        plan_session, topic_id="introduction-to-probability",
        question_id="introduction-to-probability-q1", correct=True, event_sequence=1,
    )
    a2, e2 = _save_attempt(
        plan_session, topic_id="introduction-to-probability",
        question_id="introduction-to-probability-q2", correct=True, event_sequence=2,
    )
    plan = _preview_with_probability_evidence(plan_session)
    assessment = _assessment_for(plan)
    assert assessment["status"] == "supported_understanding"
    assert assessment["confidence"] == "low"
    assert assessment["question_quality_status"] == "unreviewed"
    assert any("no recorded human quality review" in item.casefold() for item in assessment["confidence_basis"])
    assert assessment["supporting_attempt_ids"] == [a1, a2]
    assert assessment["supporting_evidence_ids"] == [e1, e2]
    assert assessment["observations"][0]["attempt_id"] == a1
    assert assessment["observations"][0]["evidence_id"] == e1
    assert assessment["observations"][0]["source_dataset"] == "mcp-ri-student-studio"
    assert assessment["observations"][0]["source_record_id"] == a1
    assert assessment["observed_time_range"]["earliest"].startswith("2026-11-01")
    assert assessment["observed_time_range"]["latest"].startswith("2026-11-02")
    assert plan["ordered_topic_ids"] == [
        "introduction-to-probability", "conditional-probability", "bayes-theorem",
        "random-variables", "expected-value",
    ]
    assert plan["assessment_guidance"][0]["action"] == "none"


def test_consistent_incorrect_evidence_is_a_provisional_learning_need(plan_session):
    _save_attempt(plan_session, topic_id="introduction-to-probability",
                  question_id="introduction-to-probability-q1", correct=False, event_sequence=1)
    _save_attempt(plan_session, topic_id="introduction-to-probability",
                  question_id="introduction-to-probability-q2", correct=False, event_sequence=2)
    assessment = _assessment_for(_preview_with_probability_evidence(plan_session))
    assert assessment["status"] == "developing_understanding"
    assert assessment["confidence"] == "low"
    assert len(assessment["supporting_evidence_ids"]) == 2
    assert assessment["recommended_activity"]["action"] == "review_lesson"
    assert assessment["recommended_activity"]["lesson_id"] == "introduction-to-probability"
    assert "does not prove" in assessment["explanation"]


def test_mixed_responses_are_conflicting_and_offer_an_unseen_question(plan_session):
    _save_attempt(plan_session, topic_id="introduction-to-probability",
                  question_id="introduction-to-probability-q1", correct=True, event_sequence=1)
    a2, e2 = _save_attempt(plan_session, topic_id="introduction-to-probability",
                           question_id="introduction-to-probability-q2", correct=False, event_sequence=2)
    assessment = _assessment_for(_preview_with_probability_evidence(plan_session))
    assert assessment["status"] == "conflicting_evidence"
    assert assessment["confidence"] == "low"
    assert assessment["supporting_evidence_ids"] == []
    assert assessment["contradictory_attempt_ids"] == ["attempt-studio-local-demo-1", a2]
    assert assessment["contradictory_evidence_ids"] == ["evidence-studio-local-demo-1", e2]
    assert assessment["recommended_activity"]["action"] == "none"
    assert "No unattempted curated question" in assessment["recommended_activity"]["reason"]


def test_small_sample_requests_more_assessment_without_claiming_a_gap(plan_session):
    _save_attempt(plan_session, topic_id="introduction-to-probability",
                  question_id="introduction-to-probability-q1", correct=False, event_sequence=1)
    assessment = _assessment_for(_preview_with_probability_evidence(plan_session))
    assert assessment["status"] == "needs_further_assessment"
    assert assessment["confidence"] == "low"
    assert assessment["recommended_activity"]["question_id"] == "introduction-to-probability-q2"


def test_unrelated_profile_topic_and_non_catalog_question_are_excluded(plan_session):
    _save_attempt(plan_session, topic_id="introduction-to-probability",
                  question_id="introduction-to-probability-q1", correct=False,
                  event_sequence=1, profile_id="another-profile")
    _save_attempt(plan_session, topic_id="expected-value",
                  question_id="introduction-to-probability-q1", correct=False, event_sequence=1)
    _save_attempt(plan_session, topic_id="introduction-to-probability",
                  question_id="not-a-curated-question", correct=False, event_sequence=2)
    assessment = _assessment_for(_preview_with_probability_evidence(plan_session))
    assert assessment["status"] == "insufficient_evidence"
    assert assessment["evidence_count"] == 0


def test_canonical_evidence_with_mismatched_provenance_is_excluded_and_reported(plan_session):
    _save_attempt(plan_session, topic_id="introduction-to-probability",
                  question_id="introduction-to-probability-q1", correct=True, event_sequence=1)
    evidence = plan_session.scalar(select(StudentStudioEvidenceRecord))
    evidence.evidence_record["provenance"]["source_record_id"] = "different-attempt"
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(evidence, "evidence_record")
    plan_session.flush()
    assessment = _assessment_for(_preview_with_probability_evidence(plan_session))
    assert assessment["evidence_count"] == 0
    assert assessment["status"] == "insufficient_evidence"
    assert "did not match" in assessment["retrieval_notes"][0]


def test_historical_observations_are_exposed_without_recency_decay(plan_session):
    old_time = "2020-01-01T00:00:00+00:00"
    _save_attempt(plan_session, topic_id="introduction-to-probability",
                  question_id="introduction-to-probability-q1", correct=True,
                  event_sequence=1, event_timestamp=old_time)
    _save_attempt(plan_session, topic_id="introduction-to-probability",
                  question_id="introduction-to-probability-q2", correct=True,
                  event_sequence=2, event_timestamp="2020-01-02T00:00:00+00:00")
    assessment = _assessment_for(_preview_with_probability_evidence(plan_session))
    assert assessment["status"] == "supported_understanding"
    assert assessment["observed_time_range"]["earliest"] == old_time
    assert any("No recency decay" in item for item in assessment["uncertainty"])


def test_unmapped_goal_has_no_fabricated_topic_assessment(plan_session):
    plan = LearningPlanService().preview(plan_session, LearningPlanRequest(learning_goal="Marine biology"))
    assert plan["evidence_based_assessment"]["status"] == "not_available"
    assert plan["evidence_based_assessment"]["topics"] == []


def test_assessment_reports_when_no_catalog_diagnostic_exists():
    assessment = assess_topic_knowledge(
        topic_id="topic-without-questions", topic_title="Topic without questions",
        lesson_id=None, curated_question_ids=[], observations=[],
    )
    assert assessment["status"] == "insufficient_evidence"
    assert assessment["recommended_activity"]["action"] == "none"
    assert "No unattempted curated question" in assessment["recommended_activity"]["reason"]


def test_repeated_same_question_does_not_meet_distinct_question_threshold():
    observations = [
        StudentStudioObservation(
            attempt_id=f"attempt-{index}", evidence_id=f"evidence-{index}",
            topic_id="topic", question_id="q1", is_correct=True,
            event_timestamp=f"2026-11-0{index}T10:00:00+00:00",
            source_dataset="mcp-ri-student-studio", source_record_id=f"attempt-{index}",
        )
        for index in (1, 2, 3)
    ]
    assessment = assess_topic_knowledge(
        topic_id="topic", topic_title="Topic", lesson_id="lesson",
        curated_question_ids=["q1", "q2"], observations=observations,
    )
    assert assessment["status"] == "needs_further_assessment"
    assert assessment["distinct_question_count"] == 1
    assert assessment["repeat_attempt_count"] == 2
    assert assessment["questions_with_outcome_changes"] == []
    assert assessment["recommended_activity"]["question_id"] == "q2"


def test_repeated_same_question_with_changed_outcome_is_conflicting():
    observations = [
        StudentStudioObservation(
            attempt_id="attempt-1", evidence_id="evidence-1", topic_id="topic", question_id="q1",
            is_correct=True, event_timestamp="2026-11-01T10:00:00+00:00",
            source_dataset="mcp-ri-student-studio", source_record_id="attempt-1",
        ),
        StudentStudioObservation(
            attempt_id="attempt-2", evidence_id="evidence-2", topic_id="topic", question_id="q1",
            is_correct=False, event_timestamp="2026-11-20T10:00:00+00:00",
            source_dataset="mcp-ri-student-studio", source_record_id="attempt-2",
        ),
    ]
    assessment = assess_topic_knowledge(
        topic_id="topic", topic_title="Topic", lesson_id="lesson",
        curated_question_ids=["q1", "q2"], observations=observations,
    )
    assert assessment["status"] == "conflicting_evidence"
    assert assessment["questions_with_outcome_changes"] == ["q1"]
    assert assessment["distinct_question_count"] == 1


def test_conflicting_old_and_new_observations_are_not_resolved_by_recency():
    observations = [
        StudentStudioObservation(
            attempt_id="attempt-old", evidence_id="evidence-old", topic_id="topic", question_id="q1",
            is_correct=True, event_timestamp="2020-01-01T00:00:00+00:00",
            source_dataset="mcp-ri-student-studio", source_record_id="attempt-old",
        ),
        StudentStudioObservation(
            attempt_id="attempt-new", evidence_id="evidence-new", topic_id="topic", question_id="q2",
            is_correct=False, event_timestamp="2026-11-20T00:00:00+00:00",
            source_dataset="mcp-ri-student-studio", source_record_id="attempt-new",
        ),
    ]
    assessment = assess_topic_knowledge(
        topic_id="topic", topic_title="Topic", lesson_id="lesson",
        curated_question_ids=["q1", "q2"], observations=observations,
    )
    assert assessment["status"] == "conflicting_evidence"
    assert assessment["observed_time_range"]["earliest"].startswith("2020")
    assert any("No recency decay" in item for item in assessment["uncertainty"])


def test_missing_observation_timestamps_do_not_remove_response_evidence():
    observation = StudentStudioObservation(
        attempt_id="attempt-no-time", evidence_id="evidence-no-time", topic_id="topic", question_id="q1",
        is_correct=True, event_timestamp="", source_dataset="mcp-ri-student-studio",
        source_record_id="attempt-no-time",
    )
    assessment = assess_topic_knowledge(
        topic_id="topic", topic_title="Topic", lesson_id="lesson",
        curated_question_ids=["q1"], observations=[observation],
    )
    assert assessment["status"] == "needs_further_assessment"
    assert assessment["evidence_count"] == 1
    assert assessment["observed_time_range"] is None


def test_structurally_incomplete_question_metadata_is_visible_in_assessment_confidence():
    observation = StudentStudioObservation(
        attempt_id="attempt-1", evidence_id="evidence-1", topic_id="topic", question_id="q1",
        is_correct=True, event_timestamp="2026-11-20T00:00:00+00:00",
        source_dataset="mcp-ri-student-studio", source_record_id="attempt-1",
    )
    assessment = assess_topic_knowledge(
        topic_id="topic", topic_title="Topic", lesson_id="lesson",
        curated_question_ids=["q1"], observations=[observation],
        question_quality_status="structurally_incomplete",
    )
    assert assessment["question_quality_status"] == "structurally_incomplete"
    assert assessment["confidence"] == "low"
    assert any("failed structural checks" in item for item in assessment["confidence_basis"])
