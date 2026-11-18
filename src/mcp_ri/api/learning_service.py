"""Curated Student Studio content, activity persistence and evidence integration."""

from __future__ import annotations

import json
import math
import uuid
import hashlib
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from mcp_ri.evidence.adapters.student_studio import StudentStudioInteractionAdapter
from mcp_ri.evidence.evidence_schema import validate_evidence
from mcp_ri.evidence.state_bridge import apply_interaction_evidence
from mcp_ri.learner_state.state_builder import LearnerStateAccumulator

from .errors import APIError
from .azure_openai import AzureOpenAIClient
from .learning_schemas import (
    AnswerFeedback,
    CurriculumCatalog,
    CurriculumFile,
    LearningHistoryEntry,
    LearningSessionData,
    LessonContent,
    LessonProgressData,
    PublicQuestion,
    QuestionPractice,
    StudentBehavioralStateData,
    StudentBehavioralStateVersionData,
    StudentBehavioralStateVersionsData,
    StudentEvidenceData,
    StudentIntelligenceStatusData,
    StudentRecommendationData,
    StudentProgressData,
    StudentProgressSummary,
    StudentStudioProfile,
    TopicDetails,
    AnswerSubmission,
    CourseProgress,
    GeneratedLessonDraft,
    LessonGenerationRequest,
    LessonGenerationResult,
    TutorRequest,
    TutorResponse,
    TutorHistoryItem,
    QuestionRecord,
)
from .settings import APISettings
from .persistence import StudentStudioProfile as StudentStudioProfileRow
from .persistence import StudentLearningAttempt as StudentLearningAttemptRow
from .persistence import StudentLearningSession as StudentLearningSessionRow
from .persistence import StudentLessonProgress as StudentLessonProgressRow
from .persistence import StudentBehavioralStateVersion as StudentBehavioralStateVersionRow
from .persistence import StudentLearningRecommendation as StudentLearningRecommendationRow
from .persistence import StudentStudioEvidenceRecord as StudentStudioEvidenceRecordRow
from .persistence import StudentGeneratedLesson as StudentGeneratedLessonRow
from .persistence import StudentTutorInteraction as StudentTutorInteractionRow
from .persistence import utc_now


PROFILE_ID = "studio-local-demo"
PROFILE_NAME = "Local demo learner"
PROFILE_NOTICE = "This local demonstration profile is separate from research and EdNet learner records. It is not an authenticated account."
CURRICULUM_PATH = Path(__file__).resolve().parents[1] / "learning" / "curriculum.json"


def _load_curriculum() -> CurriculumFile:
    raw = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))
    question_counts: dict[str, int] = {}
    for question in raw["questions"]:
        question_counts[question["lesson_id"]] = question_counts.get(question["lesson_id"], 0) + 1
    for subject in raw["subjects"]:
        for course in subject["courses"]:
            for unit in course["units"]:
                for topic in unit["topics"]:
                    if "objectives" in topic:  # Compact authored source, expanded to the API schema here.
                        topic["learning_objectives"] = [
                            {"objective_id": f"{topic['topic_id']}-objective-{index + 1}", "text": text}
                            for index, text in enumerate(topic.pop("objectives"))
                        ]
                    if "minutes" in topic:
                        topic["estimated_minutes"] = topic.pop("minutes")
                    topic.setdefault("prerequisites_status", "not_established")
                    topic.setdefault("prerequisite_topic_ids", [])
                    topic.setdefault("lesson_id", topic["topic_id"])
                    topic.setdefault("practice_question_count", question_counts.get(topic["lesson_id"], 0))
    curriculum = CurriculumFile.model_validate(raw)
    lesson_ids = {lesson.lesson_id for lesson in curriculum.lessons}
    question_ids: set[str] = set()
    for subject in curriculum.subjects:
        for course in subject.courses:
            for unit in course.units:
                for topic in unit.topics:
                    if topic.lesson_id not in lesson_ids:
                        raise ValueError(f"curriculum topic {topic.topic_id!r} references an unknown lesson")
    for lesson in curriculum.lessons:
        if lesson.topic_id not in {topic.topic_id for subject in curriculum.subjects for course in subject.courses for unit in course.units for topic in unit.topics}:
            raise ValueError(f"curriculum lesson {lesson.lesson_id!r} references an unknown topic")
    for question in curriculum.questions:
        if question.question_id in question_ids or question.lesson_id not in lesson_ids:
            raise ValueError(f"curriculum question {question.question_id!r} has a duplicate ID or unknown lesson")
        question_ids.add(question.question_id)
        option_ids = {option.option_id for option in question.options}
        if question.grading.kind == "choice" and not set(question.grading.correct_option_ids) <= option_ids:
            raise ValueError(f"curriculum question {question.question_id!r} has an unknown answer option")
        if question.grading.kind == "numeric" and min(question.grading.absolute_tolerance, question.grading.relative_tolerance) < 0:
            raise ValueError(f"curriculum question {question.question_id!r} has a negative tolerance")
    return curriculum


@lru_cache(maxsize=1)
def curriculum() -> CurriculumFile:
    return _load_curriculum()


class LearningService:
    """Own Student Studio rules while keeping the research learner namespace separate."""

    evidence_adapter = StudentStudioInteractionAdapter()

    def __init__(self, settings: APISettings | None = None):
        self.settings = settings or APISettings.from_environment()
        self.azure = AzureOpenAIClient(self.settings)

    def _profile_row(self, session: Session) -> StudentStudioProfileRow:
        profile = session.get(StudentStudioProfileRow, PROFILE_ID)
        if profile is None:
            profile = StudentStudioProfileRow(profile_id=PROFILE_ID, profile_type="local_demo", created_at=utc_now())
            session.add(profile)
            session.flush()
        return profile

    @staticmethod
    def profile_data() -> dict[str, Any]:
        return StudentStudioProfile(
            profile_id=PROFILE_ID,
            display_name=PROFILE_NAME,
            identity_mode="local_demo",
            notice=PROFILE_NOTICE,
        ).model_dump()

    def catalog(self) -> dict[str, Any]:
        data = CurriculumCatalog(curriculum_version=curriculum().curriculum_version, subjects=curriculum().subjects)
        return data.model_dump(mode="json")

    def search(self, query: str) -> list[dict[str, Any]]:
        normalized = query.strip().casefold()
        items: list[dict[str, Any]] = []
        if not normalized:
            return items
        for subject in curriculum().subjects:
            for course in subject.courses:
                for unit in course.units:
                    for topic in unit.topics:
                        searchable = " ".join((topic.title, topic.description, course.title, subject.title)).casefold()
                        if normalized in searchable:
                            items.append(TopicDetails(
                                subject_id=subject.subject_id,
                                subject_title=subject.title,
                                course_id=course.course_id,
                                course_title=course.title,
                                unit_id=unit.unit_id,
                                unit_title=unit.title,
                                topic=topic,
                            ).model_dump(mode="json"))
        return items

    def topic(self, topic_id: str) -> dict[str, Any]:
        for subject in curriculum().subjects:
            for course in subject.courses:
                for unit in course.units:
                    for topic in unit.topics:
                        if topic.topic_id == topic_id:
                            return TopicDetails(
                                subject_id=subject.subject_id,
                                subject_title=subject.title,
                                course_id=course.course_id,
                                course_title=course.title,
                                unit_id=unit.unit_id,
                                unit_title=unit.title,
                                topic=topic,
                            ).model_dump(mode="json")
        raise APIError(404, "TOPIC_NOT_FOUND", "The requested topic is not available in the curated curriculum.")

    def lesson(self, lesson_id: str, session: Session | None = None) -> dict[str, Any]:
        lesson = next((item for item in curriculum().lessons if item.lesson_id == lesson_id), None)
        if lesson is not None:
            return lesson.model_dump(mode="json")
        generated = session.get(StudentGeneratedLessonRow, lesson_id) if session is not None else None
        if generated is None:
            raise APIError(404, "LESSON_NOT_FOUND", "The requested lesson is not available.")
        return generated.lesson_data

    def ai_status(self) -> dict[str, Any]:
        return self.azure.diagnostics()

    def generate_lesson(self, session: Session, body: LessonGenerationRequest) -> dict[str, Any]:
        request_hash = hashlib.sha256(json.dumps(body.model_dump(exclude={"request_id"}), sort_keys=True).encode()).hexdigest()
        prior = session.scalar(select(StudentGeneratedLessonRow).where(
            StudentGeneratedLessonRow.request_id == body.request_id,
        ))
        if prior is not None:
            if prior.request_hash != request_hash:
                raise APIError(409, "GENERATION_ID_REUSED", "This generation request ID was already used with different inputs.")
            return self._generation_result(prior, notice="Previously generated lesson returned for this request.")

        # Prefer exact curated content when the student explicitly requests generation.
        curated = next((item for item in curriculum().lessons
                        if item.title.casefold().strip() == body.topic.casefold().strip()
                        or item.topic_id.casefold().strip() == body.topic.casefold().strip()), None)
        if curated is not None:
            count = sum(item.lesson_id == curated.lesson_id for item in curriculum().questions)
            return LessonGenerationResult(
                lesson=curated,
                question_count=count,
                notice="A curated lesson already covers this topic; no Azure request was made.",
            ).model_dump(mode="json")

        system = (
            "You are an educational lesson author. Return only a JSON object with keys title, introduction, "
            "estimated_minutes, learning_objectives, sections, questions. Use the requested level and clear, "
            "accurate teaching. Use 3-8 objectives, 3-8 short sections, and exactly 5 assessable questions. "
            "Sections use section_id, title, required, blocks. Blocks must be heading, paragraph, definition, "
            "formula, worked_example, key_point, or misconception. Questions use question_type, prompt, options, "
            "grading, expected_answer, explanation, difficulty. Grading is either {kind: choice, correct_option_ids} "
            "or {kind: numeric, expected_value, absolute_tolerance, relative_tolerance}. Choice questions need 4 "
            "distinct options with exactly one correct answer. Numerical grading must be independently checkable. "
            "Do not include citations or claims of external verification. Never include keys outside the question objects."
        )
        user = json.dumps({"topic": body.topic.strip(), "subject": body.subject.strip(), "learning_level": body.level,
                           "requirements": "Include objectives, an introduction, detailed concept sections, formulas/derivations where relevant, examples, and five practice questions."})
        result = self.azure.chat_json(system=system, user=user, max_tokens=6500)
        try:
            draft = GeneratedLessonDraft.model_validate(json.loads(result.content))
        except Exception as exc:
            raise APIError(502, "AI_CONTENT_INVALID", "Azure OpenAI returned lesson content that failed validation.") from exc
        if len({section.section_id for section in draft.sections}) != len(draft.sections):
            raise APIError(502, "AI_CONTENT_INVALID", "Azure OpenAI returned duplicate lesson section IDs.")
        objective_ids = {objective.objective_id for objective in draft.learning_objectives}
        if len(objective_ids) != len(draft.learning_objectives):
            raise APIError(502, "AI_CONTENT_INVALID", "Azure OpenAI returned duplicate learning objective IDs.")

        token = uuid.uuid4().hex
        topic_id = f"ai-topic-{token}"
        lesson_id = f"ai-lesson-{token}"
        course_id = f"ai-course-{hashlib.sha256((body.subject + body.topic).encode()).hexdigest()[:12]}"
        content_version = f"azure-{token[:12]}"
        lesson = LessonContent(
            lesson_id=lesson_id, topic_id=topic_id, course_id=course_id, title=draft.title,
            introduction=draft.introduction, learning_objectives=draft.learning_objectives,
            estimated_minutes=draft.estimated_minutes, content_version=content_version,
            content_source="azure_generated", subject=body.subject.strip(), learning_level=body.level,
            generation_source="azure_openai", sections=draft.sections,
        )
        questions = []
        for draft_question in draft.questions:
            option_ids = {option.option_id for option in draft_question.options}
            if draft_question.grading.kind == "choice":
                correct = set(draft_question.grading.correct_option_ids)
                if (draft_question.question_type not in {"single_choice", "multiple_choice"}
                        or len(option_ids) != len(draft_question.options) or not correct or not correct <= option_ids
                        or (draft_question.question_type == "single_choice" and len(correct) != 1)):
                    raise APIError(502, "AI_CONTENT_INVALID", "Azure OpenAI returned an inconsistent choice question.")
            elif draft_question.question_type != "numeric" or draft_question.options:
                raise APIError(502, "AI_CONTENT_INVALID", "Azure OpenAI returned an inconsistent numeric question.")
            questions.append(QuestionRecord(
                question_id=f"ai-question-{uuid.uuid4().hex}", lesson_id=lesson_id, topic_id=topic_id,
                objective_id=draft.learning_objectives[len(questions) % len(draft.learning_objectives)].objective_id,
                question_type=draft_question.question_type, prompt=draft_question.prompt,
                options=draft_question.options, grading=draft_question.grading,
                expected_answer=draft_question.expected_answer, explanation=draft_question.explanation,
                difficulty=draft_question.difficulty, content_version=content_version,
            ))
        row = StudentGeneratedLessonRow(
            lesson_id=lesson_id, request_id=body.request_id, request_hash=request_hash,
            topic_id=topic_id, subject=body.subject.strip(), learning_level=body.level,
            content_version=content_version, lesson_data=lesson.model_dump(mode="json"),
            questions_data=[item.model_dump(mode="json") for item in questions],
            usage_data=result.usage, created_at=utc_now(),
        )
        session.add(row)
        session.flush()
        return self._generation_result(row, notice="AI-generated lesson saved. Review it as generated learning material.")

    @staticmethod
    def _generation_result(row: StudentGeneratedLessonRow, *, notice: str) -> dict[str, Any]:
        lesson = LessonContent.model_validate(row.lesson_data)
        return LessonGenerationResult(
            lesson=lesson, question_count=len(row.questions_data), usage=row.usage_data, notice=notice,
        ).model_dump(mode="json")

    def tutor(self, session: Session, lesson_id: str, body: TutorRequest) -> dict[str, Any]:
        session_row = session.get(StudentLearningSessionRow, body.session_id)
        if session_row is None or session_row.profile_id != PROFILE_ID or session_row.lesson_id != lesson_id:
            raise APIError(409, "SESSION_MISMATCH", "The learning session does not belong to this lesson.")
        lesson, _, _, _ = self._lesson_and_course(session, lesson_id)
        if body.section_id is not None and not any(item.section_id == body.section_id for item in lesson.sections):
            raise APIError(422, "INVALID_TUTOR_SECTION", "The requested section is not part of this lesson.")
        section = next((item for item in lesson.sections if item.section_id == body.section_id), None) if body.section_id else None
        request_hash = hashlib.sha256(json.dumps({"message": body.message.strip(), "level": body.level,
                                                  "section_id": body.section_id}, sort_keys=True).encode()).hexdigest()
        prior = session.scalar(select(StudentTutorInteractionRow).where(
            StudentTutorInteractionRow.session_id == body.session_id,
            StudentTutorInteractionRow.turn_id == body.turn_id,
            StudentTutorInteractionRow.role == "assistant",
        ))
        if prior is not None:
            if prior.request_hash != request_hash:
                raise APIError(409, "TUTOR_TURN_ID_REUSED", "This tutor turn ID was already used with different inputs.")
            return TutorResponse(answer=prior.content, source="azure_supplementary_explanation",
                                 usage=prior.usage_data,
                                 notice="Supplementary explanation generated for this lesson; review it critically.").model_dump(mode="json")
        recent = list(session.scalars(select(StudentTutorInteractionRow).where(
            StudentTutorInteractionRow.session_id == body.session_id,
        ).order_by(StudentTutorInteractionRow.created_at.desc()).limit(20)))
        recent.reverse()
        history = [{"role": row.role, "content": row.content} for row in recent]
        lesson_context = lesson.model_dump(mode="json")
        system = (
            "You are a patient educational tutor. Answer at the learner's requested level, use the supplied lesson "
            "and section as the main context, and say clearly when the lesson does not support a claim. Do not claim "
            "independent verification or invent citations. Never reveal or infer hidden grading keys or answers to "
            "unsubmitted assessment questions. This is supplementary generated explanation, not a change to the saved lesson. "
            "Return JSON only with one string key named answer."
        )
        user = json.dumps({"learning_level": body.level, "lesson": lesson_context,
                           "current_section": None if section is None else section.model_dump(mode="json"),
                           "conversation": history, "student_question": body.message.strip()})
        result = self.azure.chat_json(system=system, user=user, max_tokens=1200)
        try:
            answer = json.loads(result.content)["answer"]
            if not isinstance(answer, str) or not answer.strip() or len(answer) > 5000:
                raise ValueError("invalid answer")
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            raise APIError(502, "AI_CONTENT_INVALID", "Azure OpenAI returned an invalid tutor response.") from None
        now = utc_now()
        assistant_time = (datetime.fromisoformat(now) + timedelta(microseconds=1)).isoformat()
        session.add_all([
            StudentTutorInteractionRow(interaction_id=str(uuid.uuid4()), session_id=body.session_id,
                                       turn_id=body.turn_id, request_hash=request_hash, lesson_id=lesson_id,
                                       role="user", content=body.message.strip(), created_at=now),
            StudentTutorInteractionRow(interaction_id=str(uuid.uuid4()), session_id=body.session_id,
                                       turn_id=body.turn_id, request_hash=request_hash, lesson_id=lesson_id,
                                       role="assistant", content=answer.strip(), usage_data=result.usage, created_at=assistant_time),
        ])
        session.flush()
        return TutorResponse(answer=answer.strip(), source="azure_supplementary_explanation",
                             usage=result.usage, notice="Supplementary explanation generated for this lesson; review it critically.").model_dump(mode="json")

    def tutor_history(self, session: Session, lesson_id: str, session_id: str) -> list[dict[str, Any]]:
        study_session = session.get(StudentLearningSessionRow, session_id)
        if study_session is None or study_session.profile_id != PROFILE_ID or study_session.lesson_id != lesson_id:
            raise APIError(409, "SESSION_MISMATCH", "The learning session does not belong to this lesson.")
        rows = session.scalars(select(StudentTutorInteractionRow).where(
            StudentTutorInteractionRow.session_id == session_id,
        ).order_by(StudentTutorInteractionRow.created_at.asc(), StudentTutorInteractionRow.interaction_id.asc()))
        return [TutorHistoryItem(role=row.role, content=row.content, created_at=row.created_at).model_dump(mode="json")
                for row in rows]

    def practice(self, lesson_id: str, session: Session | None = None) -> dict[str, Any]:
        lesson = next((item for item in curriculum().lessons if item.lesson_id == lesson_id), None)
        if lesson is None:
            generated = session.get(StudentGeneratedLessonRow, lesson_id) if session is not None else None
            if generated is None:
                raise APIError(404, "LESSON_NOT_FOUND", "The requested lesson is not available.")
            lesson = LessonContent.model_validate(generated.lesson_data)
            records = [QuestionRecord.model_validate(item) for item in generated.questions_data]
        else:
            records = [item for item in curriculum().questions if item.lesson_id == lesson_id]
        questions = [PublicQuestion.model_validate(item.model_dump(exclude={"grading", "expected_answer", "explanation"})).model_dump(mode="json")
                     for item in records]
        return QuestionPractice(lesson_id=lesson_id, content_version=lesson.content_version, questions=questions).model_dump(mode="json")

    def _question(self, question_id: str, session: Session):
        question = next((item for item in curriculum().questions if item.question_id == question_id), None)
        if question is None:
            for generated in session.scalars(select(StudentGeneratedLessonRow)):
                item = next((item for item in generated.questions_data if item.get("question_id") == question_id), None)
                if item is not None:
                    return QuestionRecord.model_validate(item)
            raise APIError(404, "QUESTION_NOT_FOUND", "The requested practice question is not available.")
        return question

    def _lesson_and_course(self, session: Session, lesson_id: str) -> tuple[LessonContent, str, str, str]:
        lesson = next((item for item in curriculum().lessons if item.lesson_id == lesson_id), None)
        if lesson is None:
            generated = session.get(StudentGeneratedLessonRow, lesson_id)
            if generated is None:
                raise APIError(404, "LESSON_NOT_FOUND", "The requested lesson is not available.")
            lesson = LessonContent.model_validate(generated.lesson_data)
            subject_id = f"ai-subject-{hashlib.sha256(generated.subject.encode()).hexdigest()[:12]}"
            return lesson, lesson.course_id, lesson.topic_id, subject_id
        for subject in curriculum().subjects:
            for course in subject.courses:
                for unit in course.units:
                    for topic in unit.topics:
                        if topic.topic_id == lesson.topic_id:
                            return lesson, course.course_id, topic.topic_id, subject.subject_id
        raise APIError(500, "CURRICULUM_INVALID", "The lesson is not connected to a valid curriculum topic.")

    def _progress(self, session: Session, lesson: LessonContent) -> dict[str, Any]:
        row = session.get(StudentLessonProgressRow, (PROFILE_ID, lesson.lesson_id))
        required = [section.section_id for section in lesson.sections if section.required]
        completed = [] if row is None else [section_id for section_id in row.completed_section_ids if section_id in required]
        content_complete = bool(required) and all(section_id in completed for section_id in required)
        latest = session.scalar(select(StudentLearningAttemptRow).where(
            StudentLearningAttemptRow.profile_id == PROFILE_ID,
            StudentLearningAttemptRow.lesson_id == lesson.lesson_id,
        ).order_by(StudentLearningAttemptRow.event_sequence.desc()).limit(1))
        status = "completed" if content_complete else "needs_review" if latest is not None and not latest.is_correct else "in_progress" if row is not None else "not_started"
        reason = "A recent response was incorrect. Revisit the lesson and try again; this is activity feedback, not a diagnosis." if status == "needs_review" else None
        return LessonProgressData(
            lesson_id=lesson.lesson_id,
            status=status,
            current_section_id=None if row is None else row.current_section_id,
            completed_section_ids=completed,
            completed_required_sections=len(completed),
            required_section_count=len(required),
            completion_percentage=round(100 * len(completed) / len(required)) if required else 0,
            content_complete=content_complete,
            review_reason=reason,
            updated_at=None if row is None else row.updated_at,
        ).model_dump(mode="json")

    def start_session(self, session: Session, lesson_id: str) -> dict[str, Any]:
        lesson, _, _, _ = self._lesson_and_course(session, lesson_id)
        self._profile_row(session)
        progress_row = session.get(StudentLessonProgressRow, (PROFILE_ID, lesson_id))
        now = utc_now()
        latest = session.scalar(select(StudentLearningSessionRow).where(
            StudentLearningSessionRow.profile_id == PROFILE_ID,
            StudentLearningSessionRow.lesson_id == lesson_id,
        ).order_by(StudentLearningSessionRow.last_activity_at.desc()).limit(1))
        resumed = latest is not None
        if latest is None:
            latest = StudentLearningSessionRow(
                session_id=str(uuid.uuid4()), profile_id=PROFILE_ID, lesson_id=lesson_id,
                content_version=lesson.content_version, started_at=now, last_activity_at=now,
            )
            session.add(latest)
        else:
            latest.last_activity_at = now
        if progress_row is None:
            _, course_id, topic_id, _ = self._lesson_and_course(session, lesson_id)
            progress_row = StudentLessonProgressRow(
                profile_id=PROFILE_ID, lesson_id=lesson_id, course_id=course_id, topic_id=topic_id,
                content_version=lesson.content_version, current_section_id=lesson.sections[0].section_id,
                completed_section_ids=[], started_at=now, updated_at=now, completed_at=None, revision=1,
            )
            session.add(progress_row)
        session.flush()
        return LearningSessionData(
            session_id=latest.session_id, profile_id=PROFILE_ID, lesson_id=lesson_id,
            started_at=latest.started_at, resumed=resumed, progress=self._progress(session, lesson),
        ).model_dump(mode="json")

    def save_progress(self, session: Session, lesson_id: str, body: Any) -> dict[str, Any]:
        lesson, course_id, topic_id, _ = self._lesson_and_course(session, lesson_id)
        row_session = session.get(StudentLearningSessionRow, body.session_id)
        if row_session is None or row_session.profile_id != PROFILE_ID or row_session.lesson_id != lesson_id:
            raise APIError(409, "SESSION_MISMATCH", "The learning session does not belong to this lesson.")
        section_ids = {section.section_id for section in lesson.sections}
        required = {section.section_id for section in lesson.sections if section.required}
        if body.current_section_id not in section_ids or not set(body.completed_section_ids) <= required:
            raise APIError(422, "INVALID_LESSON_PROGRESS", "The requested section is not part of this lesson.")
        self._profile_row(session)
        row = session.get(StudentLessonProgressRow, (PROFILE_ID, lesson_id))
        now = utc_now()
        if row is None:
            row = StudentLessonProgressRow(
                profile_id=PROFILE_ID, lesson_id=lesson_id, course_id=course_id, topic_id=topic_id,
                content_version=lesson.content_version, current_section_id=body.current_section_id,
                completed_section_ids=[], started_at=now, updated_at=now, completed_at=None, revision=1,
            )
            session.add(row)
        row.current_section_id = body.current_section_id
        row.completed_section_ids = sorted(set(row.completed_section_ids) | set(body.completed_section_ids))
        row.content_version = lesson.content_version
        row.updated_at = now
        row.revision += 1
        row_session.last_activity_at = now
        if required and required <= set(row.completed_section_ids):
            row.completed_at = row.completed_at or now
        session.flush()
        return self._progress(session, lesson)

    @staticmethod
    def _evaluate(question: Any, response: dict[str, Any]) -> bool:
        if question.grading.kind == "choice":
            if set(response) != {"option_ids"} or not isinstance(response["option_ids"], list):
                raise APIError(422, "INVALID_ANSWER", "Choice answers must contain an option_ids list.")
            values = response["option_ids"]
            if not values or any(not isinstance(value, str) for value in values) or len(values) != len(set(values)):
                raise APIError(422, "INVALID_ANSWER", "Select one or more distinct answer options.")
            option_ids = {option.option_id for option in question.options}
            if not set(values) <= option_ids:
                raise APIError(422, "INVALID_ANSWER", "The response contains an option that is not part of this question.")
            if question.question_type == "single_choice" and len(values) != 1:
                raise APIError(422, "INVALID_ANSWER", "Select exactly one option for this question.")
            return set(values) == set(question.grading.correct_option_ids)
        if question.grading.kind == "numeric":
            if set(response) != {"value"} or not isinstance(response["value"], (int, float, str)) or isinstance(response["value"], bool):
                raise APIError(422, "INVALID_ANSWER", "Numeric answers must contain one numeric value.")
            try:
                submitted = float(response["value"])
                expected = float(question.grading.expected_value)
            except (TypeError, ValueError):
                raise APIError(422, "INVALID_ANSWER", "Enter a valid finite number.") from None
            if not math.isfinite(submitted):
                raise APIError(422, "INVALID_ANSWER", "Enter a valid finite number.")
            tolerance = max(float(question.grading.absolute_tolerance), abs(expected) * float(question.grading.relative_tolerance))
            return abs(submitted - expected) <= tolerance
        raise APIError(422, "UNSUPPORTED_QUESTION", "This question type does not have an automatic evaluator.")

    def submit_answer(self, session: Session, question_id: str, body: AnswerSubmission) -> dict[str, Any]:
        question = self._question(question_id, session)
        lesson, course_id, topic_id, subject_id = self._lesson_and_course(session, question.lesson_id)
        self._profile_row(session)
        existing = session.scalar(select(StudentLearningAttemptRow).where(
            StudentLearningAttemptRow.profile_id == PROFILE_ID,
            StudentLearningAttemptRow.submission_id == body.submission_id,
        ))
        if existing is not None:
            if (existing.question_id != question_id or existing.submitted_response != body.response
                    or (body.session_id is not None and existing.session_id != body.session_id)):
                raise APIError(409, "SUBMISSION_ID_REUSED", "This submission ID was already used for a different answer.")
            feedback = dict(existing.feedback)
            feedback["idempotent_replay"] = True
            return AnswerFeedback.model_validate(feedback).model_dump(mode="json")
        session_row = None
        if body.session_id is not None:
            session_row = session.get(StudentLearningSessionRow, body.session_id)
            if session_row is None or session_row.profile_id != PROFILE_ID or session_row.lesson_id != question.lesson_id:
                raise APIError(409, "SESSION_MISMATCH", "The learning session does not belong to this question’s lesson.")
        else:
            session_data = self.start_session(session, question.lesson_id)
            session_row = session.get(StudentLearningSessionRow, session_data["session_id"])
        is_correct = self._evaluate(question, body.response)
        attempt_number = (session.scalar(select(func.count()).select_from(StudentLearningAttemptRow).where(
            StudentLearningAttemptRow.profile_id == PROFILE_ID,
            StudentLearningAttemptRow.question_id == question_id,
        )) or 0) + 1
        event_sequence = (session.scalar(select(func.max(StudentLearningAttemptRow.event_sequence)).where(
            StudentLearningAttemptRow.profile_id == PROFILE_ID,
        )) or 0) + 1
        now = utc_now()
        attempt_id = str(uuid.uuid4())
        event_for_evidence = {
            "attempt_id": attempt_id,
            "profile_id": PROFILE_ID,
            "session_id": session_row.session_id,
            "event_sequence": event_sequence,
            "event_timestamp": now,
            "subject_id": subject_id,
            "course_id": course_id,
            "topic_id": topic_id,
            "lesson_id": question.lesson_id,
            "question_id": question_id,
            "submitted_response": body.response,
            "is_correct": is_correct,
            "content_version": question.content_version,
        }
        evidence = self.evidence_adapter.from_answer_event(event_for_evidence)
        validate_evidence(evidence)
        feedback = AnswerFeedback(
            attempt_id=attempt_id,
            evidence_id=evidence["evidence_id"],
            question_id=question_id,
            attempt_number=attempt_number,
            is_correct=is_correct,
            submitted_response=body.response,
            expected_answer=question.expected_answer,
            explanation=question.explanation,
            feedback_message="Correct. Review the explanation to reinforce the reasoning." if is_correct else "Not quite. Review the explanation and try another question.",
            submitted_at=now,
            content_version=question.content_version,
        ).model_dump(mode="json")
        attempt = StudentLearningAttemptRow(
            attempt_id=attempt_id,
            profile_id=PROFILE_ID,
            session_id=session_row.session_id,
            submission_id=body.submission_id,
            course_id=course_id,
            topic_id=topic_id,
            lesson_id=question.lesson_id,
            question_id=question_id,
            attempt_number=attempt_number,
            event_sequence=event_sequence,
            submitted_response=body.response,
            is_correct=is_correct,
            feedback=feedback,
            content_version=question.content_version,
            event_timestamp=now,
            evidence_record=None,
            processing_status="evidence_recorded",
        )
        session.add(attempt)
        session_row.last_activity_at = now
        session.flush()
        try:
            self._persist_evidence_record(session, attempt, evidence)
            versions = self._ensure_state_versions(session)
            current_version = versions[-1]
            attempt.behavioral_state_version = current_version.state_version
            attempt.processing_status = "complete"
            processing = {
                "interaction": "saved",
                "evidence": "recorded",
                "behavioral_state": "updated",
                "behavioral_state_version": current_version.state_version,
            }
            recommendation = self._recommend_for_attempt(session, attempt, current_version.state_version, persist=True)
        except (ValueError, KeyError, TypeError) as exc:
            raise APIError(503, "LEARNING_PROCESSING_FAILED", "The answer could not be fully connected to evidence and learner state. Retry with the same submission ID.") from exc
        feedback["processing"] = processing
        feedback["recommendation"] = recommendation
        # JSON comparison sees equality with the original in-place-mutated dict;
        # explicitly mark the replacement dirty so retry feedback is persisted.
        attempt.feedback = dict(feedback)
        flag_modified(attempt, "feedback")
        session.flush()
        return feedback

    def progress(self, session: Session) -> dict[str, Any]:
        self._profile_row(session)
        generated_rows = session.scalars(select(StudentGeneratedLessonRow)).all()
        generated_lessons = [LessonContent.model_validate(row.lesson_data) for row in generated_rows]
        lessons_by_id = {lesson.lesson_id: lesson for lesson in [*curriculum().lessons, *generated_lessons]}
        rows = session.scalars(select(StudentLessonProgressRow).where(
            StudentLessonProgressRow.profile_id == PROFILE_ID,
        ).order_by(StudentLessonProgressRow.updated_at.desc())).all()
        attempts = session.scalars(select(StudentLearningAttemptRow).where(
            StudentLearningAttemptRow.profile_id == PROFILE_ID,
        )).all()
        course_refs = {
            course.course_id: (subject.subject_id, course.title)
            for subject in curriculum().subjects for course in subject.courses
        }
        for generated in generated_rows:
            lesson = lessons_by_id[generated.lesson_id]
            subject_id = f"ai-subject-{hashlib.sha256(generated.subject.encode()).hexdigest()[:12]}"
            course_refs[lesson.course_id] = (subject_id, generated.subject)
        attempts_by_course: dict[str, list[StudentLearningAttemptRow]] = {}
        for attempt in attempts:
            attempts_by_course.setdefault(attempt.course_id, []).append(attempt)
        rows_by_course: dict[str, list[StudentLessonProgressRow]] = {}
        for row in rows:
            rows_by_course.setdefault(row.course_id, []).append(row)
        courses: list[dict[str, Any]] = []
        for course_id, (subject_id, title) in course_refs.items():
            lessons = [lesson for lesson in lessons_by_id.values() if lesson.course_id == course_id]
            course_rows = rows_by_course.get(course_id, [])
            statuses = [self._progress(session, lesson)["status"] for lesson in lessons]
            completed = sum(status == "completed" for status in statuses)
            course_attempts = attempts_by_course.get(course_id, [])
            correct = sum(attempt.is_correct for attempt in course_attempts)
            started_topics = {row.topic_id for row in course_rows}
            status = "completed" if lessons and completed == len(lessons) else "needs_review" if "needs_review" in statuses else "in_progress" if course_rows else "not_started"
            courses.append(CourseProgress(
                course_id=course_id,
                subject_id=subject_id,
                title=title,
                status=status,
                lessons_completed=completed,
                lesson_count=len(lessons),
                completion_percentage=round(100 * completed / len(lessons)) if lessons else 0,
                topics_started=len(started_topics),
                practice_attempts=len(course_attempts),
                correct_attempts=correct,
                response_accuracy=correct / len(course_attempts) if course_attempts else None,
            ).model_dump(mode="json"))
        all_status = [self._progress(session, lesson)["status"] for lesson in lessons_by_id.values()]
        summary = StudentProgressSummary(
            courses_started=sum(bool(rows_by_course.get(course_id)) for course_id in course_refs),
            topics_started=len({row.topic_id for row in rows}),
            lessons_started=len(rows),
            lessons_completed=sum(status == "completed" for status in all_status),
            lessons_needing_review=sum(status == "needs_review" for status in all_status),
            lesson_sections_completed=sum(len(self._progress(session, lessons_by_id[row.lesson_id])["completed_section_ids"]) for row in rows if row.lesson_id in lessons_by_id),
            lesson_sections_total=sum(len([section for section in lessons_by_id[row.lesson_id].sections if section.required]) for row in rows if row.lesson_id in lessons_by_id),
            practice_attempts=len(attempts),
            correct_attempts=sum(attempt.is_correct for attempt in attempts),
            incorrect_attempts=sum(not attempt.is_correct for attempt in attempts),
            response_accuracy=sum(attempt.is_correct for attempt in attempts) / len(attempts) if attempts else None,
        )
        return StudentProgressData(
            profile=StudentStudioProfile.model_validate(self.profile_data()),
            summary=summary,
            courses=courses,
            recent_lesson_ids=[row.lesson_id for row in rows[:8]],
            updated_at=max((row.updated_at for row in rows), default=None),
        ).model_dump(mode="json")

    def history(self, session: Session, *, limit: int, offset: int) -> dict[str, Any]:
        self._profile_row(session)
        lesson_titles = {lesson.lesson_id: lesson.title for lesson in curriculum().lessons}
        lesson_titles.update({row.lesson_id: row.lesson_data["title"] for row in session.scalars(select(StudentGeneratedLessonRow))})
        course_by_id = {course.course_id: subject.subject_id for subject in curriculum().subjects for course in subject.courses}
        items: list[dict[str, Any]] = []
        sessions = session.scalars(select(StudentLearningSessionRow).where(
            StudentLearningSessionRow.profile_id == PROFILE_ID,
        )).all()
        for row in sessions:
            _, course_id, topic_id, _ = self._lesson_and_course(session, row.lesson_id)
            items.append(LearningHistoryEntry(
                entry_id=row.session_id,
                event_type="lesson_started",
                occurred_at=row.started_at,
                course_id=course_id,
                topic_id=topic_id,
                lesson_id=row.lesson_id,
                lesson_title=lesson_titles.get(row.lesson_id, row.lesson_id),
                content_version=row.content_version,
            ).model_dump(mode="json"))
        attempts = session.scalars(select(StudentLearningAttemptRow).where(
            StudentLearningAttemptRow.profile_id == PROFILE_ID,
        )).all()
        for row in attempts:
            items.append(LearningHistoryEntry(
                entry_id=row.attempt_id,
                event_type="answer_submitted",
                occurred_at=row.event_timestamp,
                course_id=row.course_id,
                topic_id=row.topic_id,
                lesson_id=row.lesson_id,
                lesson_title=lesson_titles.get(row.lesson_id, row.lesson_id),
                question_id=row.question_id,
                is_correct=row.is_correct,
                attempt_number=row.attempt_number,
                content_version=row.content_version,
            ).model_dump(mode="json"))
        items.sort(key=lambda item: (item["occurred_at"], item["entry_id"]), reverse=True)
        total = len(items)
        return {"profile": self.profile_data(), "items": items[offset:offset + limit], "total": total}

    @staticmethod
    def _persist_evidence_record(
        session: Session,
        attempt: StudentLearningAttemptRow,
        evidence: dict[str, Any] | None = None,
    ) -> StudentStudioEvidenceRecordRow:
        record = evidence if evidence is not None else attempt.evidence_record
        if record is None:
            raise ValueError("source event has no evidence payload to persist")
        validate_evidence(record)
        existing = session.scalar(select(StudentStudioEvidenceRecordRow).where(
            StudentStudioEvidenceRecordRow.profile_id == attempt.profile_id,
            StudentStudioEvidenceRecordRow.source_event_id == attempt.attempt_id,
        ))
        if existing is not None:
            if existing.evidence_id != record["evidence_id"] or existing.evidence_record != record:
                raise ValueError("stored evidence does not match its source learning event")
            return existing
        content = record["content"]
        evidence_row = StudentStudioEvidenceRecordRow(
            evidence_id=record["evidence_id"],
            profile_id=attempt.profile_id,
            source_event_id=attempt.attempt_id,
            topic_id=attempt.topic_id,
            lesson_id=attempt.lesson_id,
            question_id=attempt.question_id,
            evidence_record=record,
            created_at=record["temporal"]["ingestion_timestamp"],
        )
        temporal = record["temporal"]
        provenance = record["provenance"]
        if (
            record["learner_id"] != attempt.profile_id
            or provenance.get("source_dataset") != StudentStudioInteractionAdapter.source_dataset
            or provenance.get("source_record_id") != attempt.attempt_id
            or content.get("topic_id") != attempt.topic_id
            or content.get("lesson_id") != attempt.lesson_id
            or content.get("question_id") != attempt.question_id
            or content.get("correctness") != int(attempt.is_correct)
            or content.get("content_version") != attempt.content_version
            or temporal.get("event_timestamp") != attempt.event_timestamp
            or temporal.get("sequence_number") != attempt.event_sequence
        ):
            raise ValueError("evidence provenance or context does not match its source learning event")
        session.add(evidence_row)
        session.flush()
        return evidence_row

    def evidence(
        self,
        session: Session,
        *,
        limit: int,
        offset: int,
        learner_id: str | None = None,
        topic_id: str | None = None,
        lesson_id: str | None = None,
    ) -> dict[str, Any]:
        if learner_id is not None and learner_id != PROFILE_ID:
            raise APIError(404, "LEARNER_NOT_FOUND", "The requested Student Studio learner is not available.")
        self._profile_row(session)
        filters = [StudentStudioEvidenceRecordRow.profile_id == PROFILE_ID]
        if topic_id is not None:
            filters.append(StudentStudioEvidenceRecordRow.topic_id == topic_id)
        if lesson_id is not None:
            filters.append(StudentStudioEvidenceRecordRow.lesson_id == lesson_id)
        query = select(StudentStudioEvidenceRecordRow).where(*filters)
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.scalars(query.order_by(StudentStudioEvidenceRecordRow.created_at.desc(),
                                               StudentStudioEvidenceRecordRow.evidence_id.desc())
                               .limit(limit).offset(offset)).all()
        return StudentEvidenceData(
            profile=StudentStudioProfile.model_validate(self.profile_data()),
            items=[row.evidence_record for row in rows],
            total=total,
        ).model_dump(mode="json")

    def evidence_record(self, session: Session, evidence_id: str, *, learner_id: str | None = None) -> dict[str, Any]:
        if learner_id is not None and learner_id != PROFILE_ID:
            raise APIError(404, "EVIDENCE_NOT_FOUND", "The requested Student Studio evidence record is not available.")
        row = session.get(StudentStudioEvidenceRecordRow, evidence_id)
        if row is None or row.profile_id != PROFILE_ID:
            raise APIError(404, "EVIDENCE_NOT_FOUND", "The requested Student Studio evidence record is not available.")
        return row.evidence_record

    def behavioral_state(self, session: Session) -> dict[str, Any]:
        self._profile_row(session)
        versions = self._ensure_state_versions(session)
        if versions:
            latest = versions[-1]
            state = dict(latest.state_data)
            if "topic_states" not in state:
                state.update(self._studio_topic_extension(session, latest.source_event_sequence))
            version = latest.state_version
            previous = latest.previous_state_version
            supporting_ids = self._supporting_evidence_ids(session, latest.source_event_sequence)
        else:
            state = self._studio_state_snapshot(LearnerStateAccumulator(PROFILE_ID))
            version = previous = None
            supporting_ids = []
        return StudentBehavioralStateData(
            profile=StudentStudioProfile.model_validate(self.profile_data()),
            source="student_studio_interactions",
            state=state,
            state_version=version,
            previous_state_version=previous,
            supporting_evidence_ids=supporting_ids,
        ).model_dump(mode="json")

    @staticmethod
    def _studio_state_snapshot(accumulator: LearnerStateAccumulator) -> dict[str, Any]:
        state = accumulator.snapshot()
        state["student_studio_state_schema_version"] = "1.0"
        state["topic_states"] = [
            accumulator.topics[topic_id].to_state(topic_id)
            for topic_id in sorted(accumulator.topics)
        ]
        state["limitations"] = [
            limitation for limitation in state["limitations"]
            if "EdNet timestamps" not in limitation
        ] + [
            "Student Studio records use server answer-submission timestamps and an aggregate response summary.",
            "Student Studio events are separate from EdNet. Topic summaries group observed responses by authored curriculum topic identifier; they do not imply a validated skill, prerequisite, cognitive estimate, or mastery judgment.",
        ]
        return state

    def behavioral_topic_state(self, session: Session, topic_id: str) -> dict[str, Any]:
        """Return only Studio snapshots with observed evidence for this topic."""
        self._profile_row(session)
        known_topic_ids = {item.topic.topic_id for item in self._all_topics()}
        if topic_id not in known_topic_ids:
            raise APIError(404, "TOPIC_NOT_FOUND", "The requested Student Studio topic is not available.")
        versions = self._ensure_state_versions(session)
        items = []
        for version in versions:
            version_state = version.state_data
            if "topic_states" not in version_state:
                version_state = {**version_state, **self._studio_topic_extension(session, version.source_event_sequence)}
            topic = next((item for item in version_state.get("topic_states", [])
                          if item.get("concept_id") == topic_id), None)
            if topic is None:
                continue
            evidence_ids = self._supporting_topic_evidence_ids(session, version.source_event_sequence, topic_id)
            items.append({
                "state_version": version.state_version,
                "state_timestamp": version.state_timestamp,
                "evidence_count": topic["evidence_count"],
                "state": topic,
                "supporting_evidence_ids": evidence_ids,
            })
        return {
            "profile": self.profile_data(),
            "source": "student_studio_interactions",
            "topic_id": topic_id,
            "state": items[-1]["state"] if items else None,
            "state_version": items[-1]["state_version"] if items else None,
            "history": list(reversed(items)),
            "total": len(items),
        }

    @staticmethod
    def _all_topics():
        return [
            TopicDetails(
                subject_id=subject.subject_id, subject_title=subject.title,
                course_id=course.course_id, course_title=course.title,
                unit_id=unit.unit_id, unit_title=unit.title, topic=topic,
            )
            for subject in curriculum().subjects
            for course in subject.courses
            for unit in course.units
            for topic in unit.topics
        ]

    def _studio_topic_extension(self, session: Session, sequence: int) -> dict[str, Any]:
        accumulator = LearnerStateAccumulator(PROFILE_ID)
        attempts = session.scalars(select(StudentLearningAttemptRow).where(
            StudentLearningAttemptRow.profile_id == PROFILE_ID,
            StudentLearningAttemptRow.event_sequence <= sequence,
        ).order_by(StudentLearningAttemptRow.event_sequence)).all()
        for attempt in attempts:
            evidence_row = session.scalar(select(StudentStudioEvidenceRecordRow).where(
                StudentStudioEvidenceRecordRow.profile_id == PROFILE_ID,
                StudentStudioEvidenceRecordRow.source_event_id == attempt.attempt_id,
            ))
            evidence = evidence_row.evidence_record if evidence_row is not None else attempt.evidence_record
            if evidence is None or evidence.get("provenance", {}).get("source_record_id") != attempt.attempt_id:
                raise ValueError("source event is missing matching evidence provenance")
            validate_evidence(evidence)
            apply_interaction_evidence(accumulator, evidence)
        return {
            "student_studio_state_schema_version": "1.0",
            "topic_states": [accumulator.topics[key].to_state(key) for key in sorted(accumulator.topics)],
        }

    def _supporting_topic_evidence_ids(self, session: Session, sequence: int, topic_id: str) -> list[str]:
        rows = session.scalars(select(StudentStudioEvidenceRecordRow).where(
            StudentStudioEvidenceRecordRow.profile_id == PROFILE_ID,
        ).order_by(StudentStudioEvidenceRecordRow.created_at, StudentStudioEvidenceRecordRow.evidence_id)).all()
        evidence_by_source = {row.source_event_id: row.evidence_record for row in rows}
        attempts = session.scalars(select(StudentLearningAttemptRow).where(
            StudentLearningAttemptRow.profile_id == PROFILE_ID,
            StudentLearningAttemptRow.event_sequence <= sequence,
        ).order_by(StudentLearningAttemptRow.event_sequence)).all()
        return [
            evidence["evidence_id"] for attempt in attempts
            for evidence in [evidence_by_source.get(attempt.attempt_id) or attempt.evidence_record]
            if evidence is not None and evidence.get("content", {}).get("topic_id") == topic_id
        ]

    def _ensure_state_versions(self, session: Session) -> list[StudentBehavioralStateVersionRow]:
        """Append any missing snapshots while preserving the full ordered Studio history."""
        attempts = session.scalars(select(StudentLearningAttemptRow).where(
            StudentLearningAttemptRow.profile_id == PROFILE_ID,
        ).order_by(StudentLearningAttemptRow.event_sequence)).all()
        versions = session.scalars(select(StudentBehavioralStateVersionRow).where(
            StudentBehavioralStateVersionRow.profile_id == PROFILE_ID,
        ).order_by(StudentBehavioralStateVersionRow.state_version)).all()
        if len(versions) > len(attempts):
            raise ValueError("stored Student Studio state history exceeds its interaction history")
        accumulator = LearnerStateAccumulator(PROFILE_ID)
        for index, attempt in enumerate(attempts):
            if attempt.event_sequence != index + 1:
                raise ValueError("Student Studio interaction sequence is not a complete prefix")
            evidence_row = session.scalar(select(StudentStudioEvidenceRecordRow).where(
                StudentStudioEvidenceRecordRow.profile_id == attempt.profile_id,
                StudentStudioEvidenceRecordRow.source_event_id == attempt.attempt_id,
            ))
            evidence = evidence_row.evidence_record if evidence_row is not None else attempt.evidence_record
            if evidence is None:
                raise ValueError("source event has no normalized evidence record")
            if (evidence.get("provenance", {}).get("source_record_id") != attempt.attempt_id
                    or evidence.get("learner_id") != attempt.profile_id):
                raise ValueError("evidence provenance does not match its source learning event")
            validate_evidence(evidence)
            apply_interaction_evidence(accumulator, evidence)
            expected_version = index + 1
            if index < len(versions):
                version = versions[index]
                if (version.state_version != expected_version
                        or version.source_event_sequence != attempt.event_sequence
                        or version.last_evidence_id != evidence["evidence_id"]
                        or attempt.behavioral_state_version != expected_version):
                    raise ValueError("stored Student Studio state history does not match its evidence prefix")
                continue
            state = self._studio_state_snapshot(accumulator)
            version = StudentBehavioralStateVersionRow(
                profile_id=PROFILE_ID,
                state_version=expected_version,
                source_event_sequence=attempt.event_sequence,
                last_evidence_id=evidence["evidence_id"],
                evidence_count=expected_version,
                previous_state_version=expected_version - 1 if expected_version > 1 else None,
                state_timestamp=state["state_timestamp"] or attempt.event_timestamp,
                state_data=state,
                created_at=utc_now(),
            )
            session.add(version)
            attempt.behavioral_state_version = expected_version
            attempt.processing_status = "complete"
            session.flush()
            versions.append(version)
        return versions

    def _supporting_evidence_ids(self, session: Session, source_event_sequence: int) -> list[str]:
        rows = session.scalars(select(StudentLearningAttemptRow).where(
            StudentLearningAttemptRow.profile_id == PROFILE_ID,
            StudentLearningAttemptRow.event_sequence <= source_event_sequence,
        ).order_by(StudentLearningAttemptRow.event_sequence)).all()
        evidence_ids: list[str] = []
        for attempt in rows:
            evidence_row = session.scalar(select(StudentStudioEvidenceRecordRow).where(
                StudentStudioEvidenceRecordRow.profile_id == attempt.profile_id,
                StudentStudioEvidenceRecordRow.source_event_id == attempt.attempt_id,
            ))
            record = evidence_row.evidence_record if evidence_row is not None else attempt.evidence_record
            if (record is None or record.get("learner_id") != attempt.profile_id
                    or record.get("provenance", {}).get("source_record_id") != attempt.attempt_id):
                raise ValueError("source event is missing matching evidence provenance")
            evidence_ids.append(record["evidence_id"])
        return evidence_ids

    def behavioral_state_versions(self, session: Session, *, limit: int, offset: int) -> dict[str, Any]:
        self._profile_row(session)
        self._ensure_state_versions(session)
        query = select(StudentBehavioralStateVersionRow).where(
            StudentBehavioralStateVersionRow.profile_id == PROFILE_ID,
        )
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.scalars(query.order_by(StudentBehavioralStateVersionRow.state_version.desc())
                               .limit(limit).offset(offset)).all()
        return StudentBehavioralStateVersionsData(
            profile=StudentStudioProfile.model_validate(self.profile_data()),
            items=[StudentBehavioralStateVersionData(
                profile_id=row.profile_id,
                state_version=row.state_version,
                source_event_sequence=row.source_event_sequence,
                last_evidence_id=row.last_evidence_id,
                evidence_count=row.evidence_count,
                previous_state_version=row.previous_state_version,
                state_timestamp=row.state_timestamp,
                state=row.state_data,
                supporting_evidence_ids=self._supporting_evidence_ids(session, row.source_event_sequence),
                created_at=row.created_at,
            ) for row in rows],
            total=total,
        ).model_dump(mode="json")

    @staticmethod
    def _fallback_recommendation(state_version: int | None) -> dict[str, Any]:
        return {
            "status": "more_evidence_needed",
            "message": "More learning evidence is needed before a personalized recommendation can be made.",
            "source_behavioral_state_version": state_version,
            "recommendation": None,
        }

    def _recommend_for_attempt(
        self,
        session: Session,
        attempt: StudentLearningAttemptRow,
        state_version: int,
        *,
        persist: bool,
    ) -> dict[str, Any]:
        existing = session.scalar(select(StudentLearningRecommendationRow).where(
            StudentLearningRecommendationRow.profile_id == PROFILE_ID,
            StudentLearningRecommendationRow.source_state_version == state_version,
        ))
        if existing is not None:
            return self._recommendation_data(existing, state_version)

        lesson = next((item for item in curriculum().lessons if item.lesson_id == attempt.lesson_id), None)
        generated = None if lesson is not None else session.get(StudentGeneratedLessonRow, attempt.lesson_id)
        if generated is not None:
            lesson = LessonContent.model_validate(generated.lesson_data)
        if lesson is None:
            return self._fallback_recommendation(state_version)
        progress = self._progress(session, lesson)
        topic_title = next((topic.title for subject in curriculum().subjects for course in subject.courses
                            for unit in course.units for topic in unit.topics if topic.topic_id == attempt.topic_id), None)
        if topic_title is None and generated is not None:
            topic_title = lesson.title
        if topic_title is None:
            return self._fallback_recommendation(state_version)

        if not attempt.is_correct:
            activity_type = "review_lesson"
            reason = (
                f"Your latest response on {topic_title} was incorrect. Review the lesson explanation and try again; "
                "this is feedback about the response, not a diagnosis or mastery judgment."
            )
        elif not progress["content_complete"]:
            activity_type = "continue_lesson"
            reason = (
                f"You have uncompleted sections in {lesson.title}. Continue the lesson using your saved progress; "
                "this suggestion reflects activity and completion records, not mastery."
            )
        else:
            prior_questions = set(session.scalars(select(StudentLearningAttemptRow.question_id).where(
                StudentLearningAttemptRow.profile_id == PROFILE_ID,
                StudentLearningAttemptRow.lesson_id == attempt.lesson_id,
            )).all())
            available_practice = any(
                question.lesson_id == attempt.lesson_id and question.question_id not in prior_questions
                for question in curriculum().questions
            )
            if generated is not None:
                available_practice = any(item.get("question_id") not in prior_questions for item in generated.questions_data)
            if not available_practice:
                return self._fallback_recommendation(state_version)
            activity_type = "additional_practice"
            reason = (
                f"The required sections in {lesson.title} are complete and another curated practice question is available. "
                "Completion is not a mastery judgment."
            )

        evidence_ids = self._supporting_evidence_ids(session, attempt.event_sequence)
        if not evidence_ids:
            return self._fallback_recommendation(state_version)
        identity = f"{PROFILE_ID}:{state_version}:{activity_type}:{attempt.topic_id}:{attempt.lesson_id}"
        recommendation_id = "rec_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        limitations = [
            "Uses only saved Student Studio progress and response records.",
            "Does not infer understanding, misconception, mastery, or learning benefit.",
            "Does not use EdNet history, a validated prerequisite graph, or Phase 11 topic estimates.",
        ]
        title = {
            "review_lesson": f"Review {topic_title}",
            "continue_lesson": f"Continue {lesson.title}",
            "additional_practice": f"Try more {topic_title} practice",
        }[activity_type]
        recommendation = {
            "recommendation_id": recommendation_id,
            "learner_id": PROFILE_ID,
            "activity": {
                "activity_type": activity_type,
                "topic_id": attempt.topic_id,
                "lesson_id": attempt.lesson_id,
                "title": title,
            },
            "reason": reason,
            "supporting_evidence_ids": evidence_ids,
            "source_behavioral_state_version": state_version,
            "created_at": utc_now(),
            "status": "current",
            "limitations": limitations,
        }
        if persist:
            session.add(StudentLearningRecommendationRow(
                recommendation_id=recommendation_id,
                profile_id=PROFILE_ID,
                source_state_version=state_version,
                activity_type=activity_type,
                topic_id=attempt.topic_id,
                lesson_id=attempt.lesson_id,
                title=title,
                reason=reason,
                supporting_evidence_ids=evidence_ids,
                limitations=limitations,
                created_at=recommendation["created_at"],
            ))
            session.flush()
        return {"status": "personalized", "message": "A next activity is available from your saved learning activity.", "source_behavioral_state_version": state_version, "recommendation": recommendation}

    @staticmethod
    def _recommendation_data(row: StudentLearningRecommendationRow, latest_state_version: int) -> dict[str, Any]:
        recommendation = {
            "recommendation_id": row.recommendation_id,
            "learner_id": row.profile_id,
            "activity": {
                "activity_type": row.activity_type,
                "topic_id": row.topic_id,
                "lesson_id": row.lesson_id,
                "title": row.title,
            },
            "reason": row.reason,
            "supporting_evidence_ids": row.supporting_evidence_ids,
            "source_behavioral_state_version": row.source_state_version,
            "created_at": row.created_at,
            "status": "current" if row.source_state_version == latest_state_version else "superseded",
            "limitations": row.limitations,
        }
        return {
            "status": "personalized" if row.source_state_version == latest_state_version else "more_evidence_needed",
            "message": "A next activity is available from your saved learning activity." if row.source_state_version == latest_state_version else "More learning evidence is needed before a personalized recommendation can be made.",
            "source_behavioral_state_version": row.source_state_version,
            "recommendation": recommendation if row.source_state_version == latest_state_version else None,
        }

    def recommendation(self, session: Session) -> dict[str, Any]:
        self._profile_row(session)
        versions = self._ensure_state_versions(session)
        if not versions:
            return StudentRecommendationData(
                profile=StudentStudioProfile.model_validate(self.profile_data()),
                decision=self._fallback_recommendation(None),
            ).model_dump(mode="json")
        latest_version = versions[-1].state_version
        row = session.scalar(select(StudentLearningRecommendationRow).where(
            StudentLearningRecommendationRow.profile_id == PROFILE_ID,
            StudentLearningRecommendationRow.source_state_version == latest_version,
        ))
        if row is None:
            latest_attempt = session.scalar(select(StudentLearningAttemptRow).where(
                StudentLearningAttemptRow.profile_id == PROFILE_ID,
                StudentLearningAttemptRow.behavioral_state_version == latest_version,
            ))
            decision = self._fallback_recommendation(latest_version) if latest_attempt is None else self._recommend_for_attempt(
                session, latest_attempt, latest_version, persist=True,
            )
        else:
            decision = self._recommendation_data(row, latest_version)
        return StudentRecommendationData(
            profile=StudentStudioProfile.model_validate(self.profile_data()),
            decision=decision,
        ).model_dump(mode="json")

    def intelligence_status(self, session: Session) -> dict[str, Any]:
        state = self.behavioral_state(session)
        state_version = state["state_version"]
        evidence_count = state["state"]["observation_summary"]["total_interactions"]
        data = StudentIntelligenceStatusData(
            profile=StudentStudioProfile.model_validate(self.profile_data()),
            source_behavioral_state_version=state_version,
            evidence_count=evidence_count,
            cognitive_state={
                "status": "not_available",
                "reason": "Student Studio topics have no validated Phase 9 concept or skill mapping, so no topic-linked Phase 11 estimate or hypothesis is supported.",
            },
            representation_planning={
                "status": "not_available",
                "reason": "Phase 12 requires a supported concept-level input and executable capability; all eight default delivery capabilities are unavailable.",
            },
            trajectory={
                "status": "not_available",
                "reason": "No Studio trajectory is created without an authored learning goal and validated dependency information; no automatic diversion is supported.",
            },
        )
        return data.model_dump(mode="json")
