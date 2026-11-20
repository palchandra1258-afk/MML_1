"""Read-only retrieval of catalog-mapped Student Studio attempts and evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from mcp_ri.learning.knowledge_assessment import StudentStudioObservation

from .learning_service import PROFILE_ID
from .persistence import (
    StudentBehavioralStateVersion,
    StudentLearningAttempt,
    StudentStudioEvidenceRecord,
)


class StudentStudioEvidenceRetrieval:
    """Retrieve only exact topic/question matches for the local Studio profile."""

    source_dataset = "mcp-ri-student-studio"

    def retrieve(
        self,
        session: Session,
        topic_question_ids: Mapping[str, Sequence[str]],
        *,
        profile_id: str = PROFILE_ID,
    ) -> tuple[dict[str, list[StudentStudioObservation]], int | None, dict[str, list[str]]]:
        topic_ids = list(topic_question_ids)
        question_ids = sorted({question_id for values in topic_question_ids.values() for question_id in values})
        if not topic_ids or not question_ids:
            return {}, self._latest_state_version(session, profile_id), {}

        latest = session.scalar(
            select(StudentBehavioralStateVersion)
            .where(StudentBehavioralStateVersion.profile_id == profile_id)
            .order_by(StudentBehavioralStateVersion.state_version.desc())
            .limit(1)
        )
        statement = (
            select(StudentLearningAttempt, StudentStudioEvidenceRecord)
            .outerjoin(
                StudentStudioEvidenceRecord,
                (StudentStudioEvidenceRecord.source_event_id == StudentLearningAttempt.attempt_id)
                & (StudentStudioEvidenceRecord.profile_id == StudentLearningAttempt.profile_id),
            )
            .where(
                StudentLearningAttempt.profile_id == profile_id,
                StudentLearningAttempt.topic_id.in_(topic_ids),
                StudentLearningAttempt.question_id.in_(question_ids),
            )
            .order_by(StudentLearningAttempt.event_sequence)
        )
        if latest is not None:
            statement = statement.where(StudentLearningAttempt.event_sequence <= latest.source_event_sequence)

        observations: dict[str, list[StudentStudioObservation]] = defaultdict(list)
        retrieval_notes: dict[str, list[str]] = defaultdict(list)
        for attempt, evidence in session.execute(statement).all():
            valid_questions = set(topic_question_ids.get(attempt.topic_id, ()))
            if attempt.question_id not in valid_questions:
                continue
            if evidence is None:
                evidence_id = None
                source_dataset = None
                source_record_id = None
            else:
                payload = evidence.evidence_record
                provenance = payload.get("provenance", {})
                content = payload.get("content", {})
                source_dataset = provenance.get("source_dataset")
                source_record_id = provenance.get("source_record_id")
                # Only trust the canonical row if its source and catalog identity
                # agree with the persisted attempt being evaluated.
                if (
                    source_dataset != self.source_dataset
                    or source_record_id != attempt.attempt_id
                    or content.get("topic_id") != attempt.topic_id
                    or content.get("question_id") != attempt.question_id
                ):
                    retrieval_notes[attempt.topic_id].append(
                        f"A saved evidence record for attempt {attempt.attempt_id} did not match its Student Studio source provenance and was excluded."
                    )
                    continue
                evidence_id = evidence.evidence_id
            observations[attempt.topic_id].append(StudentStudioObservation(
                attempt_id=attempt.attempt_id,
                evidence_id=evidence_id,
                topic_id=attempt.topic_id,
                question_id=attempt.question_id,
                is_correct=bool(attempt.is_correct),
                event_timestamp=attempt.event_timestamp,
                source_dataset=source_dataset,
                source_record_id=source_record_id,
            ))
        return (
            dict(observations),
            latest.state_version if latest is not None else None,
            dict(retrieval_notes),
        )

    @staticmethod
    def _latest_state_version(session: Session, profile_id: str) -> int | None:
        return session.scalar(
            select(StudentBehavioralStateVersion.state_version)
            .where(StudentBehavioralStateVersion.profile_id == profile_id)
            .order_by(StudentBehavioralStateVersion.state_version.desc())
            .limit(1)
        )
