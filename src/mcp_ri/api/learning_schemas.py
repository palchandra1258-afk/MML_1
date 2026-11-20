"""Versioned curriculum, lesson, attempt, and Student Studio API models."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from typing_extensions import Union


Identifier = Annotated[str, StringConstraints(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]
ContentVersion = Annotated[str, StringConstraints(min_length=1, max_length=40)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LearningObjective(StrictModel):
    objective_id: Identifier
    text: str = Field(min_length=1, max_length=500)


class TopicSummary(StrictModel):
    topic_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1200)
    learning_objectives: list[LearningObjective]
    estimated_minutes: int = Field(ge=1, le=240)
    prerequisites_status: Literal["not_established", "validated"] = "not_established"
    prerequisite_topic_ids: list[Identifier] = Field(default_factory=list)
    lesson_id: Identifier
    practice_question_count: int = Field(ge=0)


class CurriculumUnit(StrictModel):
    unit_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1200)
    topics: list[TopicSummary]


class CurriculumCourse(StrictModel):
    course_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1200)
    units: list[CurriculumUnit]


class CurriculumSubject(StrictModel):
    subject_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1200)
    courses: list[CurriculumCourse]


class HeadingBlock(StrictModel):
    type: Literal["heading"]
    level: Literal[2, 3]
    text: str = Field(min_length=1, max_length=300)


class ParagraphBlock(StrictModel):
    type: Literal["paragraph"]
    text: str = Field(min_length=1, max_length=4000)


class DefinitionBlock(StrictModel):
    type: Literal["definition"]
    term: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=2000)


class FormulaBlock(StrictModel):
    type: Literal["formula"]
    label: str = Field(min_length=1, max_length=200)
    expression: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=1200)


class WorkedExampleBlock(StrictModel):
    type: Literal["worked_example"]
    prompt: str = Field(min_length=1, max_length=1200)
    steps: list[str] = Field(min_length=1, max_length=12)
    result: str = Field(min_length=1, max_length=500)


class KeyPointBlock(StrictModel):
    type: Literal["key_point"]
    text: str = Field(min_length=1, max_length=1200)


class MisconceptionBlock(StrictModel):
    type: Literal["misconception"]
    claim: str = Field(min_length=1, max_length=500)
    correction: str = Field(min_length=1, max_length=1200)


LessonBlock = Annotated[
    Union[
        HeadingBlock,
        ParagraphBlock,
        DefinitionBlock,
        FormulaBlock,
        WorkedExampleBlock,
        KeyPointBlock,
        MisconceptionBlock,
    ],
    Field(discriminator="type"),
]


class LessonSection(StrictModel):
    section_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    required: bool = True
    blocks: list[LessonBlock] = Field(min_length=1)


class LessonContent(StrictModel):
    lesson_id: Identifier
    topic_id: Identifier
    course_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    introduction: str = Field(min_length=1, max_length=2000)
    learning_objectives: list[LearningObjective] = Field(min_length=1)
    estimated_minutes: int = Field(ge=1, le=240)
    content_version: ContentVersion
    content_source: Literal["curated_static", "azure_generated", "gemini_generated", "mock_generated"] = "curated_static"
    subject: str = Field(default="", max_length=160)
    learning_level: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    generation_source: Literal["curated", "azure_openai", "gemini", "mock"] = "curated"
    sections: list[LessonSection] = Field(min_length=1)


class ChoiceGrading(StrictModel):
    kind: Literal["choice"]
    correct_option_ids: list[Identifier] = Field(min_length=1)


class NumericGrading(StrictModel):
    kind: Literal["numeric"]
    expected_value: Decimal
    absolute_tolerance: Decimal = Decimal("0")
    relative_tolerance: Decimal = Decimal("0")


GradingSpecification = Annotated[Union[ChoiceGrading, NumericGrading], Field(discriminator="kind")]


class GeneratedQuestionDraft(StrictModel):
    question_type: Literal["single_choice", "multiple_choice", "numeric"]
    prompt: str = Field(min_length=1, max_length=2000)
    options: list["QuestionOption"] = Field(default_factory=list, max_length=8)
    grading: GradingSpecification
    expected_answer: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=1800)
    difficulty: Literal["introductory", "intermediate", "challenge"]


class GeneratedLessonDraft(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    introduction: str = Field(min_length=1, max_length=2000)
    estimated_minutes: int = Field(ge=5, le=240)
    learning_objectives: list[LearningObjective] = Field(min_length=1, max_length=8)
    sections: list[LessonSection] = Field(min_length=3, max_length=12)
    questions: list[GeneratedQuestionDraft] = Field(min_length=3, max_length=12)


class LessonGenerationRequest(StrictModel):
    request_id: Identifier
    topic: str = Field(min_length=2, max_length=160)
    subject: str = Field(default="General learning", min_length=2, max_length=160)
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"


class LessonGenerationResult(StrictModel):
    lesson: LessonContent
    question_count: int = Field(ge=0, le=12)
    usage: dict[str, int] | None = None
    notice: str


class AzureAIStatus(StrictModel):
    provider: Literal["azure_openai", "gemini", "mock"]
    configured: bool
    generation_available: bool
    availability_reason: str | None
    missing_configuration: list[Literal[
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_API_VERSION",
        "GEMINI_API_KEY", "GEMINI_MODEL",
    ]]
    deployment_name: str | None
    model: str | None = None
    timeout_seconds: float = Field(ge=1, le=120)
    max_retries: int = Field(ge=0, le=5)
    voice_deployment_used: Literal[False]


class TutorRequest(StrictModel):
    session_id: Identifier
    turn_id: Identifier
    message: str = Field(min_length=1, max_length=2000)
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    section_id: Identifier | None = None


class TutorResponse(StrictModel):
    answer: str = Field(min_length=1, max_length=5000)
    source: Literal["azure_supplementary_explanation", "gemini_supplementary_explanation", "mock_test_response"]
    usage: dict[str, int] | None = None
    notice: str


class TutorHistoryItem(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=5000)
    created_at: str


class QuestionOption(StrictModel):
    option_id: Identifier
    text: str = Field(min_length=1, max_length=1000)


class QuestionRecord(StrictModel):
    question_id: Identifier
    lesson_id: Identifier
    topic_id: Identifier
    objective_id: Identifier
    question_type: Literal["single_choice", "multiple_choice", "numeric"]
    prompt: str = Field(min_length=1, max_length=3000)
    options: list[QuestionOption] = Field(default_factory=list)
    grading: GradingSpecification
    expected_answer: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=2000)
    difficulty: Literal["introductory", "intermediate", "challenge"]
    content_version: ContentVersion


class PublicQuestion(StrictModel):
    question_id: Identifier
    lesson_id: Identifier
    topic_id: Identifier
    objective_id: Identifier
    question_type: Literal["single_choice", "multiple_choice", "numeric"]
    prompt: str
    options: list[QuestionOption]
    difficulty: Literal["introductory", "intermediate", "challenge"]
    content_version: ContentVersion


class CurriculumFile(StrictModel):
    curriculum_version: ContentVersion
    subjects: list[CurriculumSubject]
    lessons: list[LessonContent]
    questions: list[QuestionRecord]


class CurriculumCatalog(StrictModel):
    curriculum_version: ContentVersion
    subjects: list[CurriculumSubject]


class LearningPlanRequest(StrictModel):
    learning_goal: str = Field(min_length=3, max_length=500)

    @field_validator("learning_goal")
    @classmethod
    def normalize_learning_goal(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("learning_goal must contain at least 3 non-whitespace characters")
        return normalized


class LearningProviderStatus(StrictModel):
    capability: Literal["learning_plan"]
    status: Literal["available", "unavailable"]
    provider_id: str | None = None
    reason: str
    invoked: Literal[False] = False


class LearningPlanAssessment(StrictModel):
    source: Literal["curated_questions", "unavailable"]
    question_ids: list[Identifier]
    question_types: list[Literal["single_choice", "multiple_choice", "numeric"]]
    evaluation_mode: Literal["backend_scored_choice_or_numeric", "not_available"]


class LearningPlanKnowledgeSummary(StrictModel):
    topic_id: Identifier
    attempts: int = Field(ge=0)
    correct: int = Field(ge=0)
    incorrect: int = Field(ge=0)
    historical_accuracy: float | None = Field(default=None, ge=0, le=1)
    recent_accuracy: float | None = Field(default=None, ge=0, le=1)
    evidence_sufficiency: Literal["none", "low", "moderate", "high"]
    performance_trend: Literal["improving", "declining", "stable", "insufficient_evidence"]
    state_version: int = Field(ge=1)
    supporting_evidence_ids: list[Identifier]
    interpretation: Literal["descriptive_response_history_only"] = "descriptive_response_history_only"


class LearningPlanKnowledge(StrictModel):
    status: Literal["available", "not_available"]
    source: Literal["student_studio_phase9_behavioral_summary"] | None = None
    state_version: int | None = Field(default=None, ge=1)
    topic_summaries: list[LearningPlanKnowledgeSummary]
    reason: str


class KnowledgeAssessmentRecommendation(StrictModel):
    action: Literal["diagnostic_question", "review_lesson", "none"]
    topic_id: Identifier
    lesson_id: Identifier | None = None
    question_id: Identifier | None = None
    title: str | None = None
    reason: str


class KnowledgeAssessmentObservation(StrictModel):
    attempt_id: Identifier
    evidence_id: Identifier | None = None
    question_id: Identifier
    outcome: Literal["correct", "incorrect"]
    event_timestamp: str
    source_dataset: Literal["mcp-ri-student-studio"] | None = None
    source_record_id: Identifier | None = None


class LearningTopicKnowledgeAssessment(StrictModel):
    topic_id: Identifier
    topic_title: str
    status: Literal[
        "supported_understanding", "developing_understanding", "needs_further_assessment",
        "insufficient_evidence", "conflicting_evidence",
    ]
    confidence: Literal["insufficient", "low"]
    confidence_basis: list[str]
    question_quality_status: Literal["unreviewed", "structurally_incomplete"]
    evidence_count: int = Field(ge=0)
    distinct_question_count: int = Field(ge=0)
    repeat_attempt_count: int = Field(ge=0)
    questions_with_outcome_changes: list[Identifier]
    supporting_attempt_ids: list[Identifier]
    supporting_evidence_ids: list[Identifier]
    contradictory_attempt_ids: list[Identifier]
    contradictory_evidence_ids: list[Identifier]
    observations: list[KnowledgeAssessmentObservation]
    observed_time_range: dict[str, str] | None = None
    retrieval_notes: list[str]
    explanation: str
    uncertainty: list[str]
    recommended_activity: KnowledgeAssessmentRecommendation


class EvidenceGroundedKnowledgeAssessment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    method_version: Literal["studio-binary-evidence-1.1"] = "studio-binary-evidence-1.1"
    status: Literal["available", "insufficient_evidence", "not_available"]
    source: Literal["student_studio_attempts"] | None = None
    learner_profile_id: Identifier
    behavioral_state_version: int | None = Field(default=None, ge=1)
    topics: list[LearningTopicKnowledgeAssessment]
    reason: str
    limitations: list[str]


class LearningAssessmentGuidance(StrictModel):
    topic_id: Identifier
    interpretation: str
    action: Literal["diagnostic_question", "review_lesson", "none"]
    question_id: Identifier | None = None
    lesson_id: Identifier | None = None


class LearningPlanStep(StrictModel):
    sequence: int = Field(ge=1)
    topic_id: Identifier
    topic_title: str
    subject_id: Identifier
    subject_title: str
    course_id: Identifier
    course_title: str
    unit_id: Identifier
    unit_title: str
    lesson_id: Identifier
    learning_objectives: list[LearningObjective]
    estimated_minutes: int = Field(ge=1)
    inclusion_reason: Literal["goal_match", "validated_prerequisite"]
    prerequisite_topic_ids: list[Identifier]
    prerequisites_status: Literal["not_established", "validated"]
    assessment: LearningPlanAssessment
    prior_response_summary: LearningPlanKnowledgeSummary | None = None


class LearningPlanModule(StrictModel):
    module_id: Identifier
    title: str
    description: str
    course_id: Identifier
    ordered_topic_ids: list[Identifier]


class LearningPlanPrerequisite(StrictModel):
    prerequisite_topic_id: Identifier
    topic_id: Identifier
    source: Literal["curriculum"]
    verification_status: Literal["validated"]


class LearningPlanPrerequisites(StrictModel):
    status: Literal["identified", "not_established"]
    relationships: list[LearningPlanPrerequisite]
    topics_without_validated_prerequisites: list[Identifier]
    reason: str


class LearningPlanMapping(StrictModel):
    status: Literal["mapped", "partially_mapped", "unsupported"]
    method: Literal["catalog_keyword_match"]
    matched_goal_terms: list[str]
    unmatched_goal_terms: list[str]
    catalog_gaps: list[str]
    reason: str


class LearningPlanData(StrictModel):
    plan_id: Identifier
    plan_schema_version: Literal["1.0"] = "1.0"
    status: Literal["mapped", "partially_mapped", "unsupported"]
    generation_mode: Literal["rule_based"]
    persisted: Literal[False] = False
    learner_profile_id: Identifier
    learning_goal: str
    curriculum_version: ContentVersion
    created_at: str
    provider: LearningProviderStatus
    mapping: LearningPlanMapping
    knowledge_assessment: LearningPlanKnowledge
    evidence_based_assessment: EvidenceGroundedKnowledgeAssessment | None = None
    assessment_guidance: list[LearningAssessmentGuidance] = Field(default_factory=list)
    prerequisites: LearningPlanPrerequisites
    modules: list[LearningPlanModule]
    ordered_topic_ids: list[Identifier]
    learning_sequence: list[LearningPlanStep]
    estimated_minutes: int = Field(ge=0)
    missing_information: list[str]
    limitations: list[str]


class TopicDetails(StrictModel):
    subject_id: Identifier
    subject_title: str
    course_id: Identifier
    course_title: str
    unit_id: Identifier
    unit_title: str
    topic: TopicSummary


class StudentStudioProfile(StrictModel):
    profile_id: Identifier
    display_name: str
    identity_mode: Literal["local_demo"]
    notice: str


class LessonProgressUpdate(StrictModel):
    session_id: Identifier
    current_section_id: Identifier
    completed_section_ids: list[Identifier] = Field(default_factory=list)


class LessonProgressData(StrictModel):
    lesson_id: Identifier
    status: Literal["not_started", "in_progress", "completed", "needs_review"]
    current_section_id: Identifier | None
    completed_section_ids: list[Identifier]
    completed_required_sections: int
    required_section_count: int
    completion_percentage: int = Field(ge=0, le=100)
    content_complete: bool
    review_reason: str | None = None
    updated_at: str | None = None


class LearningSessionData(StrictModel):
    session_id: Identifier
    profile_id: Identifier
    lesson_id: Identifier
    started_at: str
    resumed: bool
    progress: LessonProgressData


class LearningSessionRequest(StrictModel):
    lesson_id: Identifier


class AnswerSubmission(StrictModel):
    submission_id: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    response: dict[str, Any]
    session_id: Identifier | None = None


class LearningProcessingStatus(StrictModel):
    interaction: Literal["saved"]
    evidence: Literal["recorded"]
    behavioral_state: Literal["updated"]
    behavioral_state_version: int = Field(ge=1)


class RecommendedActivity(StrictModel):
    activity_type: Literal["review_lesson", "continue_lesson", "additional_practice"]
    topic_id: Identifier
    lesson_id: Identifier
    title: str = Field(min_length=1, max_length=200)


class PersonalizedRecommendation(StrictModel):
    recommendation_id: Identifier
    learner_id: Identifier
    activity: RecommendedActivity
    reason: str = Field(min_length=1, max_length=1000)
    supporting_evidence_ids: list[Identifier] = Field(min_length=1)
    source_behavioral_state_version: int = Field(ge=1)
    created_at: str
    status: Literal["current", "superseded"]
    limitations: list[str]


class RecommendationDecision(StrictModel):
    status: Literal["personalized", "more_evidence_needed"]
    message: str
    source_behavioral_state_version: int | None = Field(default=None, ge=1)
    recommendation: PersonalizedRecommendation | None = None


class QuestionPractice(StrictModel):
    lesson_id: Identifier
    content_version: ContentVersion
    questions: list[PublicQuestion]


class AnswerFeedback(StrictModel):
    attempt_id: Identifier
    evidence_id: Identifier
    question_id: Identifier
    attempt_number: int = Field(ge=1)
    is_correct: bool
    submitted_response: dict[str, Any]
    expected_answer: str
    explanation: str
    feedback_message: str
    submitted_at: str
    content_version: ContentVersion
    idempotent_replay: bool = False
    processing: LearningProcessingStatus | None = None
    recommendation: RecommendationDecision | None = None


class CourseProgress(StrictModel):
    course_id: Identifier
    subject_id: Identifier
    title: str
    status: Literal["not_started", "in_progress", "completed", "needs_review"]
    lessons_completed: int = Field(ge=0)
    lesson_count: int = Field(ge=0)
    completion_percentage: int = Field(ge=0, le=100)
    topics_started: int = Field(ge=0)
    practice_attempts: int = Field(ge=0)
    correct_attempts: int = Field(ge=0)
    response_accuracy: float | None = Field(default=None, ge=0, le=1)


class StudentProgressSummary(StrictModel):
    courses_started: int = Field(ge=0)
    topics_started: int = Field(ge=0)
    lessons_started: int = Field(ge=0)
    lessons_completed: int = Field(ge=0)
    lessons_needing_review: int = Field(ge=0)
    lesson_sections_completed: int = Field(ge=0)
    lesson_sections_total: int = Field(ge=0)
    practice_attempts: int = Field(ge=0)
    correct_attempts: int = Field(ge=0)
    incorrect_attempts: int = Field(ge=0)
    response_accuracy: float | None = Field(default=None, ge=0, le=1)


class StudentProgressData(StrictModel):
    profile: StudentStudioProfile
    summary: StudentProgressSummary
    courses: list[CourseProgress]
    recent_lesson_ids: list[Identifier]
    updated_at: str | None = None


class LearningHistoryEntry(StrictModel):
    entry_id: Identifier
    event_type: Literal["lesson_started", "answer_submitted"]
    occurred_at: str
    course_id: Identifier
    topic_id: Identifier
    lesson_id: Identifier
    lesson_title: str
    question_id: Identifier | None = None
    is_correct: bool | None = None
    attempt_number: int | None = Field(default=None, ge=1)
    content_version: ContentVersion


class LearningHistoryData(StrictModel):
    profile: StudentStudioProfile
    items: list[LearningHistoryEntry]
    total: int = Field(ge=0)


class StudentEvidenceData(StrictModel):
    profile: StudentStudioProfile
    items: list[dict[str, Any]]
    total: int = Field(ge=0)


class StudentBehavioralStateVersionData(StrictModel):
    profile_id: Identifier
    state_version: int = Field(ge=1)
    source_event_sequence: int = Field(ge=0)
    last_evidence_id: Identifier
    evidence_count: int = Field(ge=1)
    previous_state_version: int | None = Field(default=None, ge=1)
    state_timestamp: str
    state: dict[str, Any]
    supporting_evidence_ids: list[Identifier]
    created_at: str


class StudentBehavioralStateVersionsData(StrictModel):
    profile: StudentStudioProfile
    items: list[StudentBehavioralStateVersionData]
    total: int = Field(ge=0)


class StudentBehavioralStateData(StrictModel):
    profile: StudentStudioProfile
    source: Literal["student_studio_interactions"]
    state: dict[str, Any]
    state_version: int | None = Field(default=None, ge=1)
    previous_state_version: int | None = Field(default=None, ge=1)
    supporting_evidence_ids: list[Identifier] = Field(default_factory=list)


class StudentTopicBehavioralStateVersion(StrictModel):
    state_version: int = Field(ge=1)
    state_timestamp: str
    evidence_count: int = Field(ge=1)
    state: dict[str, Any]
    supporting_evidence_ids: list[Identifier]


class StudentTopicBehavioralStateData(StrictModel):
    profile: StudentStudioProfile
    source: Literal["student_studio_interactions"]
    topic_id: Identifier
    state: dict[str, Any] | None
    state_version: int | None = Field(default=None, ge=1)
    history: list[StudentTopicBehavioralStateVersion]
    total: int = Field(ge=0)


class DownstreamAvailability(StrictModel):
    status: Literal["available", "not_available"]
    reason: str


class StudentIntelligenceStatusData(StrictModel):
    profile: StudentStudioProfile
    source_behavioral_state_version: int | None = Field(default=None, ge=1)
    evidence_count: int = Field(ge=0)
    cognitive_state: DownstreamAvailability
    representation_planning: DownstreamAvailability
    trajectory: DownstreamAvailability


class StudentRecommendationData(StrictModel):
    profile: StudentStudioProfile
    decision: RecommendationDecision
