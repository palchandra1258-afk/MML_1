from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from mcp_ri.api.learning_service import LearningService
from mcp_ri.api.persistence import (
    StudentBehavioralStateVersion,
    StudentLearningAttempt,
    StudentLearningRecommendation,
    StudentStudioEvidenceRecord,
)


def _start_lesson(client, lesson_id="conditional-probability"):
    response = client.post(f"/api/v1/studio/lessons/{lesson_id}/sessions")
    assert response.status_code == 200
    return response.json()["data"]


def _answer(client, session_id, submission_id, option_id="a", question_id="conditional-probability-q1"):
    return client.post(f"/api/v1/studio/questions/{question_id}/answer", json={
        "submission_id": submission_id,
        "session_id": session_id,
        "response": {"option_ids": [option_id]},
    })


def test_attempt_evidence_state_versions_and_recommendation_are_traceable(api):
    client = api.client
    session = _start_lesson(client)

    first = _answer(client, session["session_id"], "f10-answer-1").json()["data"]
    assert first["processing"] == {
        "interaction": "saved",
        "evidence": "recorded",
        "behavioral_state": "updated",
        "behavioral_state_version": 1,
    }
    assert first["recommendation"]["status"] == "personalized"
    recommendation = first["recommendation"]["recommendation"]
    assert recommendation["activity"]["activity_type"] == "continue_lesson"
    assert recommendation["supporting_evidence_ids"] == [first["evidence_id"]]
    assert recommendation["source_behavioral_state_version"] == 1
    assert recommendation["learner_id"] == "studio-local-demo"

    second = _answer(client, session["session_id"], "f10-answer-2", option_id="b").json()["data"]
    assert second["processing"]["behavioral_state_version"] == 2
    assert second["recommendation"]["recommendation"]["activity"]["activity_type"] == "review_lesson"
    assert second["recommendation"]["recommendation"]["supporting_evidence_ids"] == [first["evidence_id"], second["evidence_id"]]

    replay = _answer(client, session["session_id"], "f10-answer-2", option_id="b").json()["data"]
    assert replay["attempt_id"] == second["attempt_id"]
    assert replay["evidence_id"] == second["evidence_id"]
    assert replay["processing"]["behavioral_state_version"] == 2
    assert replay["recommendation"] == second["recommendation"]
    assert replay["idempotent_replay"] is True

    current = client.get("/api/v1/studio/behavioral-state").json()["data"]
    assert current["state_version"] == 2
    assert current["previous_state_version"] == 1
    assert current["supporting_evidence_ids"] == [first["evidence_id"], second["evidence_id"]]
    assert current["state"]["observation_summary"]["labelled_responses"] == 2
    assert current["state"]["concept_states"] == []
    topic_state = client.get("/api/v1/studio/behavioral-state/topics/conditional-probability").json()["data"]
    assert topic_state["source"] == "student_studio_interactions"
    assert topic_state["state"]["attempts"] == 2
    assert topic_state["state"]["correct"] == 1
    assert topic_state["state"]["incorrect"] == 1
    assert topic_state["state"]["evidence_sufficiency"] == "low"
    assert topic_state["history"][0]["state_version"] == 2
    assert topic_state["history"][0]["supporting_evidence_ids"] == [first["evidence_id"], second["evidence_id"]]
    assert topic_state["history"][1]["supporting_evidence_ids"] == [first["evidence_id"]]
    empty_topic = client.get("/api/v1/studio/behavioral-state/topics/bayes-theorem").json()["data"]
    assert empty_topic["state"] is None
    assert empty_topic["history"] == []
    assert client.get("/api/v1/studio/behavioral-state/topics/not-a-curriculum-topic").status_code == 404

    versions = client.get("/api/v1/studio/behavioral-state/versions").json()["data"]
    assert versions["total"] == 2
    assert [item["state_version"] for item in versions["items"]] == [2, 1]
    assert versions["items"][0]["supporting_evidence_ids"] == [first["evidence_id"], second["evidence_id"]]
    assert versions["items"][1]["supporting_evidence_ids"] == [first["evidence_id"]]

    saved_recommendation = client.get("/api/v1/studio/recommendation").json()["data"]["decision"]["recommendation"]
    assert saved_recommendation["recommendation_id"] == second["recommendation"]["recommendation"]["recommendation_id"]
    assert saved_recommendation["source_behavioral_state_version"] == 2

    with api.app.state.database.session_factory() as db:
        assert len(db.scalars(select(StudentLearningAttempt)).all()) == 2
        assert len(db.scalars(select(StudentBehavioralStateVersion)).all()) == 2
        assert len(db.scalars(select(StudentLearningRecommendation)).all()) == 2
        assert len(db.scalars(select(StudentStudioEvidenceRecord)).all()) == 2


def test_empty_studio_uses_transparent_recommendation_fallback(api):
    response = api.client.get("/api/v1/studio/recommendation")
    assert response.status_code == 200
    decision = response.json()["data"]["decision"]
    assert decision["status"] == "more_evidence_needed"
    assert decision["message"] == "More learning evidence is needed before a personalized recommendation can be made."
    assert decision["recommendation"] is None


def test_downstream_status_reports_unsupported_studio_mapping_and_capabilities(api):
    client = api.client
    session = _start_lesson(client)
    _answer(client, session["session_id"], "f10-boundary-1")
    status = client.get("/api/v1/studio/intelligence-status").json()["data"]
    assert status["source_behavioral_state_version"] == 1
    assert status["evidence_count"] == 1
    assert status["cognitive_state"]["status"] == "not_available"
    assert "validated Phase 9 concept" in status["cognitive_state"]["reason"]
    assert status["representation_planning"]["status"] == "not_available"
    assert "all eight" in status["representation_planning"]["reason"]
    assert status["trajectory"]["status"] == "not_available"
    assert "authored learning goal" in status["trajectory"]["reason"]


def test_processing_failure_rolls_back_interaction_evidence_and_state(api, monkeypatch):
    client = api.client
    session = _start_lesson(client)

    def fail_bridge(*_args, **_kwargs):
        raise ValueError("injected evidence processing failure")

    monkeypatch.setattr("mcp_ri.api.learning_service.apply_interaction_evidence", fail_bridge)
    response = _answer(client, session["session_id"], "f10-failure-1")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LEARNING_PROCESSING_FAILED"
    with api.app.state.database.session_factory() as db:
        assert db.scalar(select(StudentLearningAttempt)) is None
        assert db.scalar(select(StudentBehavioralStateVersion)) is None
        assert db.scalar(select(StudentLearningRecommendation)) is None
        assert db.scalar(select(StudentStudioEvidenceRecord)) is None

    monkeypatch.undo()
    retried = _answer(client, session["session_id"], "f10-failure-1")
    assert retried.status_code == 200
    assert retried.json()["data"]["processing"]["behavioral_state_version"] == 1


def test_legacy_f9_attempts_are_backfilled_as_ordered_state_versions(api):
    client = api.client
    session = _start_lesson(client)
    answer = _answer(client, session["session_id"], "legacy-source-attempt").json()["data"]
    with api.app.state.database.session_factory.begin() as db:
        row = db.scalar(select(StudentLearningAttempt).where(StudentLearningAttempt.attempt_id == answer["attempt_id"]))
        row.behavioral_state_version = None
        row.processing_status = "evidence_recorded"
        db.execute(select(StudentBehavioralStateVersion).where(StudentBehavioralStateVersion.profile_id == "studio-local-demo"))
        db.query(StudentLearningRecommendation).delete()
        db.query(StudentBehavioralStateVersion).delete()
        row.feedback = {key: value for key, value in row.feedback.items() if key not in {"processing", "recommendation"}}

    state = client.get("/api/v1/studio/behavioral-state").json()["data"]
    assert state["state_version"] == 1
    assert state["supporting_evidence_ids"] == [answer["evidence_id"]]
    assert state["state"]["topic_states"][0]["concept_id"] == "conditional-probability"
    assert state["state"]["topic_states"][0]["evidence_count"] == 1
    with api.app.state.database.session_factory() as db:
        row = db.get(StudentLearningAttempt, answer["attempt_id"])
        assert row.behavioral_state_version == 1
        assert row.processing_status == "complete"


def test_concurrent_submissions_receive_unique_ordered_state_versions(api):
    client = api.client
    session = _start_lesson(client)
    payloads = [
        (f"concurrent-answer-{index}", "a" if index % 2 == 0 else "b")
        for index in range(6)
    ]
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(
            lambda pair: _answer(client, session["session_id"], pair[0], pair[1]),
            payloads,
        ))
    assert all(response.status_code == 200 for response in responses)
    versions = [response.json()["data"]["processing"]["behavioral_state_version"] for response in responses]
    assert sorted(versions) == [1, 2, 3, 4, 5, 6]
    current = client.get("/api/v1/studio/behavioral-state").json()["data"]
    assert current["state"]["observation_summary"]["total_interactions"] == 6
    topic_state = client.get("/api/v1/studio/behavioral-state/topics/conditional-probability").json()["data"]
    assert topic_state["state"]["attempts"] == 6
    assert topic_state["total"] == 6


def test_studio_evidence_and_state_stay_out_of_research_learner_index(api):
    client = api.client
    session = _start_lesson(client)
    answer = _answer(client, session["session_id"], "source-separation-1").json()["data"]
    evidence = client.get("/api/v1/studio/evidence").json()["data"]["items"][0]
    assert evidence["evidence_id"] == answer["evidence_id"]
    assert evidence["provenance"]["source_dataset"] == "mcp-ri-student-studio"
    assert evidence["provenance"]["source_record_id"] == answer["attempt_id"]
    assert evidence["learner_id"] == "studio-local-demo"
    assert evidence["temporal"]["event_timestamp"] == answer["submitted_at"]
    assert evidence["temporal"]["ingestion_timestamp"] is not None
    assert evidence["content"]["skill_ids"] == []

    learners = client.get("/api/v1/learners").json()["data"]["items"]
    assert "studio-local-demo" not in {learner["learner_id"] for learner in learners}
    assert client.get("/api/v1/learners/studio-local-demo").status_code == 404
