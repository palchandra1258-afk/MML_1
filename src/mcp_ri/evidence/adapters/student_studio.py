"""Adapter from one persisted Student Studio answer event to Phase 10 evidence."""

from __future__ import annotations

from typing import Any, Mapping

from ..normalizer import base_record


class StudentStudioInteractionAdapter:
    source_dataset = "mcp-ri-student-studio"

    def from_answer_event(self, event: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize only fields supported by the persisted, server-graded event."""
        attempt_id = str(event["attempt_id"])
        response = event["submitted_response"]
        return base_record(
            learner_id=str(event["profile_id"]),
            session_id=event.get("session_id"),
            evidence_type="interaction",
            event_timestamp=str(event["event_timestamp"]),
            sequence_number=int(event["event_sequence"]),
            temporal_precision="millisecond",
            timestamp_source="server answer-submission time",
            source_dataset=self.source_dataset,
            source_file=None,
            source_record_id=attempt_id,
            source_modality="interaction",
            processing_method="student_studio_answer_evaluator",
            content={
                "subject_id": str(event["subject_id"]),
                "course_id": str(event["course_id"]),
                "topic_id": str(event["topic_id"]),
                "lesson_id": str(event["lesson_id"]),
                "question_id": str(event["question_id"]),
                "interaction_type": "answer_submission",
                "submitted_answer": response,
                "correctness": int(bool(event["is_correct"])),
                "skill_ids": [],
                "is_exact_duplicate": False,
                "content_version": str(event["content_version"]),
            },
            extraction_method="server_evaluated_response",
            transformation_history=[
                "Student Studio answer evaluated and normalized as separate platform evidence."
            ],
            uncertainty_flags=["local_demo_profile"],
            uncertainty_notes=[
                "This response is behavioral activity and does not establish understanding or mastery."
            ],
        )
