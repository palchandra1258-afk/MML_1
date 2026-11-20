"""Read-only Student Studio planning orchestration."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mcp_ri.learning.planning import build_rule_based_learning_plan
from mcp_ri.learning.knowledge_assessment import build_evidence_grounded_assessment
from mcp_ri.learning.assessment_validation import audit_question_quality
from mcp_ri.learning.providers import (
    StructuredLearningProvider,
    UnavailableStructuredLearningProvider,
)

from .learning_schemas import LearningPlanData, LearningPlanRequest
from .learning_evidence_retrieval import StudentStudioEvidenceRetrieval
from .learning_service import PROFILE_ID, curriculum
from .persistence import (
    StudentBehavioralStateVersion as StudentBehavioralStateVersionRow,
    StudentLearningAttempt as StudentLearningAttemptRow,
    StudentStudioEvidenceRecord as StudentStudioEvidenceRecordRow,
)


class LearningPlanService:
    """Build non-persisted plans from authored curriculum and saved Studio history."""

    def __init__(self, provider: StructuredLearningProvider | None = None) -> None:
        self.provider = provider or UnavailableStructuredLearningProvider()
        self.evidence_retrieval = StudentStudioEvidenceRetrieval()

    def _latest_topic_knowledge(self, session: Session) -> tuple[int | None, dict, dict[str, list[str]]]:
        """Read the latest committed F10.2 snapshot without reconstructing or writing it."""
        version = session.scalar(
            select(StudentBehavioralStateVersionRow)
            .where(StudentBehavioralStateVersionRow.profile_id == PROFILE_ID)
            .order_by(StudentBehavioralStateVersionRow.state_version.desc())
            .limit(1)
        )
        if version is None:
            return None, {}, {}

        topic_state = {
            str(item["concept_id"]): item
            for item in version.state_data.get("topic_states", [])
            if item.get("concept_id")
        }
        evidence_ids: dict[str, list[str]] = {}
        if topic_state:
            rows = session.execute(
                select(StudentStudioEvidenceRecordRow.topic_id, StudentStudioEvidenceRecordRow.evidence_id)
                .join(
                    StudentLearningAttemptRow,
                    StudentLearningAttemptRow.attempt_id == StudentStudioEvidenceRecordRow.source_event_id,
                )
                .where(
                    StudentStudioEvidenceRecordRow.profile_id == PROFILE_ID,
                    StudentLearningAttemptRow.event_sequence <= version.source_event_sequence,
                    StudentStudioEvidenceRecordRow.topic_id.in_(topic_state),
                )
                .order_by(StudentLearningAttemptRow.event_sequence)
            ).all()
            for topic_id, evidence_id in rows:
                evidence_ids.setdefault(topic_id, []).append(evidence_id)
        return version.state_version, topic_state, evidence_ids

    def preview(self, session: Session, request: LearningPlanRequest) -> dict:
        state_version, topic_state, evidence_ids = self._latest_topic_knowledge(session)
        availability = self.provider.availability("learning_plan")
        provider_status = {
            "capability": availability.capability,
            "available": availability.available,
            "provider_id": availability.provider_id,
            "reason": availability.reason,
        }
        catalog_data = curriculum().model_dump(mode="json")
        question_quality = audit_question_quality(catalog_data)
        question_quality_by_topic = {item["topic_id"]: item for item in question_quality["topics"]}
        result = build_rule_based_learning_plan(
            learning_goal=request.learning_goal,
            curriculum=catalog_data,
            state_version=state_version,
            topic_state=topic_state,
            topic_evidence_ids=evidence_ids,
            provider_availability=availability,
        )
        topic_question_ids = {
            step["topic_id"]: step["assessment"]["question_ids"]
            for step in result["learning_sequence"]
        }
        observations, assessment_state_version, retrieval_notes = self.evidence_retrieval.retrieve(
            session,
            topic_question_ids,
            profile_id=PROFILE_ID,
        )
        topic_metadata = [
            {
                "topic_id": step["topic_id"],
                "topic_title": step["topic_title"],
                "lesson_id": step["lesson_id"],
                "question_ids": question_quality_by_topic.get(step["topic_id"], {}).get("structurally_usable_question_ids", []),
                "question_quality_status": (
                    "structurally_incomplete"
                    if len(question_quality_by_topic.get(step["topic_id"], {}).get("structurally_usable_question_ids", []))
                    < len(step["assessment"]["question_ids"])
                    else "unreviewed"
                ),
            }
            for step in result["learning_sequence"]
        ]
        evidence_assessment = build_evidence_grounded_assessment(
            learner_profile_id=PROFILE_ID,
            behavioral_state_version=assessment_state_version,
            relevant_topics=topic_metadata,
            observations_by_topic=observations,
            retrieval_notes_by_topic=retrieval_notes,
        )
        assessment_guidance = []
        for item in evidence_assessment["topics"]:
            activity = item["recommended_activity"]
            assessment_guidance.append({
                "topic_id": item["topic_id"],
                "interpretation": item["status"],
                "action": activity["action"],
                "question_id": activity["question_id"],
                "lesson_id": activity["lesson_id"],
            })
            if item["status"] == "insufficient_evidence":
                result["missing_information"].append(
                    f"Current understanding of {item['topic_title']} is unassessed; no knowledge gap is inferred."
                )
            elif item["status"] == "conflicting_evidence":
                result["missing_information"].append(
                    f"Student Studio responses for {item['topic_title']} conflict; further evidence is needed."
                )
            elif item["status"] == "developing_understanding":
                result["missing_information"].append(
                    f"Responses on distinct {item['topic_title']} questions support offering review; they do not establish lack of knowledge."
                )
        result["missing_information"] = list(dict.fromkeys(result["missing_information"]))
        result["evidence_based_assessment"] = evidence_assessment
        result["assessment_guidance"] = assessment_guidance
        result["limitations"].append(
            "Assessment guidance is additional context; it does not reorder or skip the catalog learning sequence."
        )
        # Keep the provider boundary observable without invoking it or implying
        # that a rule-based plan was generated by a model.
        if provider_status["available"]:
            result["provider"]["reason"] = (
                provider_status["reason"]
                + " A provider may be available, but this foundation deliberately uses the rule-based planner."
            )
        return LearningPlanData.model_validate(result).model_dump(mode="json")
