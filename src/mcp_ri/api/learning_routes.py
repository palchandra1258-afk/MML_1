"""Student Studio curriculum and persisted learning activity endpoints."""

from __future__ import annotations

from threading import RLock
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from .dependencies import get_learning_service, get_session
from .learning_schemas import (
    AnswerFeedback,
    AnswerSubmission,
    CurriculumCatalog,
    LearningHistoryData,
    LearningSessionData,
    LessonContent,
    LessonProgressData,
    LessonProgressUpdate,
    QuestionPractice,
    StudentBehavioralStateData,
    StudentBehavioralStateVersionsData,
    StudentTopicBehavioralStateData,
    StudentEvidenceData,
    StudentIntelligenceStatusData,
    StudentProgressData,
    StudentRecommendationData,
    StudentStudioProfile,
    TopicDetails,
    Identifier,
)
from .learning_service import LearningService
from .schemas import Envelope


learning_router = APIRouter(prefix="/api/v1", tags=["student-learning"])
_SUBMISSION_LOCK = RLock()


def _envelope(request: Request, data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "request_id": request.state.request_id}


@learning_router.get("/curriculum", response_model=Envelope[CurriculumCatalog], operation_id="getCurriculum")
def get_curriculum(request: Request, service: LearningService = Depends(get_learning_service)) -> dict[str, Any]:
    return _envelope(request, service.catalog())


@learning_router.get("/curriculum/search", response_model=Envelope[list[TopicDetails]], operation_id="searchCurriculum")
def search_curriculum(
    request: Request,
    q: str = Query(default="", max_length=160),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    return _envelope(request, service.search(q))


@learning_router.get("/curriculum/topics/{topic_id}", response_model=Envelope[TopicDetails], operation_id="getTopic")
def get_topic(
    topic_id: str,
    request: Request,
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    return _envelope(request, service.topic(topic_id))


@learning_router.get("/curriculum/lessons/{lesson_id}", response_model=Envelope[LessonContent], operation_id="getLesson")
def get_lesson(
    lesson_id: str,
    request: Request,
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    return _envelope(request, service.lesson(lesson_id))


@learning_router.get("/curriculum/lessons/{lesson_id}/practice", response_model=Envelope[QuestionPractice], operation_id="getLessonPractice")
def get_lesson_practice(
    lesson_id: str,
    request: Request,
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    return _envelope(request, service.practice(lesson_id))


@learning_router.get("/studio/profile", response_model=Envelope[StudentStudioProfile], operation_id="getStudentStudioProfile")
def get_student_profile(
    request: Request,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.profile_data()
    service._profile_row(session)
    session.commit()
    return _envelope(request, data)


@learning_router.post("/studio/lessons/{lesson_id}/sessions", response_model=Envelope[LearningSessionData], operation_id="startLessonSession")
def start_lesson_session(
    lesson_id: str,
    request: Request,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.start_session(session, lesson_id)
    session.commit()
    return _envelope(request, data)


@learning_router.post("/studio/lessons/{lesson_id}/progress", response_model=Envelope[LessonProgressData], operation_id="saveLessonProgress")
def save_lesson_progress(
    lesson_id: str,
    body: LessonProgressUpdate,
    request: Request,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.save_progress(session, lesson_id, body)
    session.commit()
    return _envelope(request, data)


@learning_router.post("/studio/questions/{question_id}/answer", response_model=Envelope[AnswerFeedback], operation_id="submitLearningAnswer")
def submit_learning_answer(
    question_id: str,
    body: AnswerSubmission,
    request: Request,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    # SQLite plus the single local demo profile needs sequence allocation and
    # the transaction commit serialized together, including concurrent retries.
    with _SUBMISSION_LOCK:
        data = service.submit_answer(session, question_id, body)
        session.commit()
    return _envelope(request, data)


@learning_router.get("/studio/progress", response_model=Envelope[StudentProgressData], operation_id="getStudentProgress")
def get_student_progress(
    request: Request,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.progress(session)
    session.commit()
    return _envelope(request, data)


@learning_router.get("/studio/history", response_model=Envelope[LearningHistoryData], operation_id="getStudentLearningHistory")
def get_student_history(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.history(session, limit=limit, offset=offset)
    session.commit()
    return _envelope(request, data)


@learning_router.get("/studio/evidence", response_model=Envelope[StudentEvidenceData], operation_id="getStudentEvidence")
def get_student_evidence(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    learner_id: Identifier | None = None,
    topic_id: Identifier | None = None,
    lesson_id: Identifier | None = None,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.evidence(session, limit=limit, offset=offset, learner_id=learner_id,
                            topic_id=topic_id, lesson_id=lesson_id)
    session.commit()
    return _envelope(request, data)


@learning_router.get(
    "/studio/evidence/{evidence_id}",
    response_model=Envelope[dict[str, Any]],
    operation_id="getStudentEvidenceRecord",
)
def get_student_evidence_record(
    evidence_id: Identifier,
    request: Request,
    learner_id: Identifier | None = None,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    return _envelope(request, service.evidence_record(session, evidence_id, learner_id=learner_id))


@learning_router.get("/studio/behavioral-state", response_model=Envelope[StudentBehavioralStateData], operation_id="getStudentBehavioralState")
def get_student_behavioral_state(
    request: Request,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.behavioral_state(session)
    session.commit()
    return _envelope(request, data)


@learning_router.get(
    "/studio/behavioral-state/versions",
    response_model=Envelope[StudentBehavioralStateVersionsData],
    operation_id="getStudentBehavioralStateVersions",
)
def get_student_behavioral_state_versions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.behavioral_state_versions(session, limit=limit, offset=offset)
    session.commit()
    return _envelope(request, data)


@learning_router.get(
    "/studio/behavioral-state/topics/{topic_id}",
    response_model=Envelope[StudentTopicBehavioralStateData],
    operation_id="getStudentTopicBehavioralState",
)
def get_student_topic_behavioral_state(
    topic_id: Identifier,
    request: Request,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.behavioral_topic_state(session, topic_id)
    session.commit()
    return _envelope(request, data)


@learning_router.get(
    "/studio/intelligence-status",
    response_model=Envelope[StudentIntelligenceStatusData],
    operation_id="getStudentIntelligenceStatus",
)
def get_student_intelligence_status(
    request: Request,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.intelligence_status(session)
    session.commit()
    return _envelope(request, data)


@learning_router.get(
    "/studio/recommendation",
    response_model=Envelope[StudentRecommendationData],
    operation_id="getStudentRecommendation",
)
def get_student_recommendation(
    request: Request,
    session: Session = Depends(get_session),
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    data = service.recommendation(session)
    session.commit()
    return _envelope(request, data)
