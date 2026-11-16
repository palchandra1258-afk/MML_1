from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mcp_ri.api.errors import APIError
from mcp_ri.api.learning_schemas import AnswerSubmission
from mcp_ri.api.learning_service import LearningService, PROFILE_ID
from mcp_ri.api.persistence import (
    Database,
    StudentLearningAttempt,
    StudentLearningSession,
    StudentStudioEvidenceRecord,
    StudentStudioProfile,
    LearnerReference,
    utc_now,
)
from mcp_ri.evidence.normalizer import base_record


def _submit(service: LearningService, session: Session, session_id: str, submission_id: str):
    return service.submit_answer(session, "conditional-probability-q1", AnswerSubmission(
        submission_id=submission_id,
        session_id=session_id,
        response={"option_ids": ["a"]},
    ))


def test_answer_evidence_is_atomic_idempotent_filterable_and_survives_reopen(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'studio.sqlite3'}"
    database = Database(database_url)
    database.create_schema()
    service = LearningService()
    with database.session_factory.begin() as session:
        started = service.start_session(session, "conditional-probability")
        first = _submit(service, session, started["session_id"], "stable-event-key")
        assert first["evidence_id"].startswith("ev_")
        assert first["idempotent_replay"] is False
        assert first["processing"]["evidence"] == "recorded"
        record = session.get(StudentStudioEvidenceRecord, first["evidence_id"])
        assert record is not None
        assert record.source_event_id == first["attempt_id"]
        assert record.profile_id == PROFILE_ID
        assert record.topic_id == "conditional-probability"
        assert record.evidence_record["provenance"]["source_dataset"] == "mcp-ri-student-studio"
        assert record.evidence_record["provenance"]["source_record_id"] == first["attempt_id"]
        assert record.evidence_record["schema_version"] == "1.0"
        assert record.evidence_record["provenance"]["processing_version"] == "mcp-ri-evidence-1.0.0"
        assert record.evidence_record["content"]["subject_id"] == "mathematics"
        assert record.evidence_record["content"]["interaction_type"] == "answer_submission"
        assert record.evidence_record["content"]["correctness"] == 1
        assert record.evidence_record["content"]["skill_ids"] == []
        assert record.evidence_record["temporal"]["ingestion_timestamp"]
        assert record.evidence_record["processing"]["processing_timestamp"]
        attempt = session.get(StudentLearningAttempt, first["attempt_id"])
        assert attempt is not None and attempt.evidence_record is None

        replay = _submit(service, session, started["session_id"], "stable-event-key")
        assert replay["attempt_id"] == first["attempt_id"]
        assert replay["evidence_id"] == first["evidence_id"]
        assert replay["idempotent_replay"] is True
        filtered = service.evidence(session, learner_id=PROFILE_ID, topic_id="conditional-probability", limit=20, offset=0)
        assert filtered["total"] == 1
        assert filtered["items"][0]["evidence_id"] == first["evidence_id"]
        assert service.evidence(session, topic_id="expected-value", limit=20, offset=0)["total"] == 0
        assert service.evidence_record(session, first["evidence_id"], learner_id=PROFILE_ID)["provenance"]["source_record_id"] == first["attempt_id"]

    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(StudentLearningAttempt)) == 1
        assert session.scalar(select(func.count()).select_from(StudentStudioEvidenceRecord)) == 1
        assert session.scalar(select(func.count()).select_from(LearnerReference)) == 0
        with pytest.raises(APIError) as unknown_learner:
            service.evidence(session, learner_id="u135328", limit=10, offset=0)
        assert unknown_learner.value.status_code == 404
        with pytest.raises(APIError) as unknown_record:
            service.evidence_record(session, "ev_00000000000000000000000000000000")
        assert unknown_record.value.status_code == 404
    database.dispose()

    restarted = Database(database_url)
    with restarted.session_factory() as session:
        assert session.get(StudentStudioEvidenceRecord, first["evidence_id"]) is not None
        assert session.scalar(select(func.count()).select_from(StudentLearningAttempt)) == 1
    with restarted.session_factory.begin() as session:
        replay = _submit(service, session, started["session_id"], "stable-event-key")
        assert replay["idempotent_replay"] is True
        assert replay["processing"]["behavioral_state_version"] == 1
        assert replay["evidence_id"] == first["evidence_id"]
    restarted.dispose()


def test_evidence_write_failure_rolls_back_the_source_attempt(tmp_path: Path, monkeypatch):
    database = Database(f"sqlite:///{tmp_path / 'rollback.sqlite3'}")
    database.create_schema()
    service = LearningService()
    with database.session_factory.begin() as session:
        started = service.start_session(session, "conditional-probability")

    def fail_write(*_args, **_kwargs):
        raise ValueError("injected evidence write failure")

    monkeypatch.setattr(service, "_persist_evidence_record", fail_write)
    with database.session_factory() as session:
        with pytest.raises(APIError) as raised:
            _submit(service, session, started["session_id"], "failed-evidence-key")
        assert raised.value.status_code == 503
        session.rollback()
    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(StudentLearningAttempt)) == 0
        assert session.scalar(select(func.count()).select_from(StudentStudioEvidenceRecord)) == 0
    database.dispose()


def test_rejected_answer_creates_neither_attempt_nor_evidence(tmp_path: Path):
    database = Database(f"sqlite:///{tmp_path / 'rejected.sqlite3'}")
    database.create_schema()
    service = LearningService()
    with database.session_factory.begin() as session:
        started = service.start_session(session, "conditional-probability")
    with database.session_factory() as session:
        with pytest.raises(APIError) as raised:
            service.submit_answer(session, "conditional-probability-q1", AnswerSubmission(
                submission_id="invalid-answer-key",
                session_id=started["session_id"],
                response={"option_ids": ["not-an-option"]},
            ))
        assert raised.value.status_code == 422
        session.rollback()
    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(StudentLearningAttempt)) == 0
        assert session.scalar(select(func.count()).select_from(StudentStudioEvidenceRecord)) == 0
    database.dispose()


def test_0004_migration_backfills_legacy_f9_evidence_without_deleting_attempt(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'legacy.sqlite3'}"
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "0003_f10_learning_intelligence")
    database = Database(database_url)
    attempt_id = "f10-legacy-attempt-0001"
    event_timestamp = utc_now()
    evidence = base_record(
        learner_id=PROFILE_ID,
        session_id="legacy-studio-session",
        evidence_type="interaction",
        event_timestamp=event_timestamp,
        sequence_number=1,
        temporal_precision="millisecond",
        timestamp_source="server answer-submission time",
        source_dataset="mcp-ri-student-studio",
        source_file=None,
        source_record_id=attempt_id,
        source_modality="interaction",
        processing_method="student_studio_answer_evaluator",
        content={"topic_id": "conditional-probability", "lesson_id": "conditional-probability", "question_id": "q1", "correctness": 1, "skill_ids": []},
    )
    with database.engine.begin() as connection:
        connection.execute(StudentStudioProfile.__table__.insert().values(
            profile_id=PROFILE_ID, profile_type="local_demo", created_at=utc_now(),
        ))
        connection.execute(StudentLearningSession.__table__.insert().values(
            session_id="legacy-studio-session", profile_id=PROFILE_ID, lesson_id="conditional-probability",
            content_version="1.0.0", started_at=event_timestamp, last_activity_at=event_timestamp,
        ))
        connection.execute(StudentLearningAttempt.__table__.insert().values(
            attempt_id=attempt_id, profile_id=PROFILE_ID, session_id="legacy-studio-session",
            submission_id="legacy-submit", course_id="probability-foundations", topic_id="conditional-probability",
            lesson_id="conditional-probability", question_id="q1", attempt_number=1, event_sequence=1,
            submitted_response={"option_ids": ["a"]}, is_correct=True, feedback={}, content_version="1.0.0",
            event_timestamp=event_timestamp, evidence_record=evidence, processing_status="complete",
            behavioral_state_version=1,
        ))

    command.upgrade(config, "head")
    with database.session_factory() as session:
        migrated = session.get(StudentStudioEvidenceRecord, evidence["evidence_id"])
        assert migrated is not None
        assert migrated.source_event_id == attempt_id
        assert session.get(StudentLearningAttempt, attempt_id) is not None
        assert session.scalar(select(func.count()).select_from(StudentStudioEvidenceRecord)) == 1
    command.downgrade(config, "0003_f10_learning_intelligence")
    with database.session_factory() as session:
        restored = session.get(StudentLearningAttempt, attempt_id)
        assert restored is not None and restored.evidence_record["evidence_id"] == evidence["evidence_id"]
    command.upgrade(config, "head")
    with database.session_factory() as session:
        reupgraded = session.get(StudentStudioEvidenceRecord, evidence["evidence_id"])
        assert reupgraded is not None and reupgraded.source_event_id == attempt_id
        assert session.get(StudentLearningAttempt, attempt_id) is not None
    database.dispose()
