import type { ApiClient } from "../api/client";
import { getApiClient } from "../api/client";

export type LearningObjective = { objective_id: string; text: string };
export type Topic = {
  topic_id: string;
  title: string;
  description: string;
  learning_objectives: LearningObjective[];
  estimated_minutes: number;
  prerequisites_status: "not_established" | "validated";
  prerequisite_topic_ids: string[];
  lesson_id: string;
  practice_question_count: number;
};
export type CurriculumUnit = { unit_id: string; title: string; description: string; topics: Topic[] };
export type CurriculumCourse = { course_id: string; title: string; description: string; units: CurriculumUnit[] };
export type CurriculumSubject = { subject_id: string; title: string; description: string; courses: CurriculumCourse[] };
export type CurriculumCatalog = { curriculum_version: string; subjects: CurriculumSubject[] };
export type TopicDetails = { subject_id: string; subject_title: string; course_id: string; course_title: string; unit_id: string; unit_title: string; topic: Topic };
export type LessonBlock =
  | { type: "heading"; level: 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "definition"; term: string; definition: string }
  | { type: "formula"; label: string; expression: string; explanation: string }
  | { type: "worked_example"; prompt: string; steps: string[]; result: string }
  | { type: "key_point"; text: string }
  | { type: "misconception"; claim: string; correction: string };
export type LessonSection = { section_id: string; title: string; required: boolean; blocks: LessonBlock[] };
export type Lesson = {
  lesson_id: string;
  topic_id: string;
  course_id: string;
  title: string;
  introduction: string;
  learning_objectives: LearningObjective[];
  estimated_minutes: number;
  content_version: string;
  content_source: "curated_static" | "azure_generated" | "gemini_generated" | "mock_generated";
  subject: string;
  learning_level: "beginner" | "intermediate" | "advanced";
  generation_source: "curated" | "azure_openai" | "gemini" | "mock";
  sections: LessonSection[];
};
export type LessonGenerationResult = {
  lesson: Lesson;
  question_count: number;
  usage: Record<string, number> | null;
  notice: string;
};
export type LessonGenerationRequest = {
  request_id: string;
  topic: string;
  subject?: string;
  level: "beginner" | "intermediate" | "advanced";
};
export type StudentAIStatus = {
  provider: "azure_openai" | "gemini" | "mock";
  configured: boolean;
  generation_available: boolean;
  availability_reason: string | null;
  missing_configuration: string[];
  deployment_name: string | null;
  model?: string | null;
  timeout_seconds: number;
  max_retries: number;
  voice_deployment_used: false;
};
export type TutorAnswer = {
  answer: string;
  source: "azure_supplementary_explanation" | "gemini_supplementary_explanation" | "mock_test_response";
  usage: Record<string, number> | null;
  notice: string;
};
export type TutorMessage = { role: "user" | "assistant"; content: string; created_at: string };
export type PublicQuestion = {
  question_id: string;
  lesson_id: string;
  topic_id: string;
  objective_id: string;
  question_type: "single_choice" | "multiple_choice" | "numeric";
  prompt: string;
  options: { option_id: string; text: string }[];
  difficulty: "introductory" | "intermediate" | "challenge";
  content_version: string;
};
export type Practice = { lesson_id: string; content_version: string; questions: PublicQuestion[] };
export type Profile = { profile_id: string; display_name: string; identity_mode: "local_demo"; notice: string };
export type LessonProgress = {
  lesson_id: string;
  status: "not_started" | "in_progress" | "completed" | "needs_review";
  current_section_id: string | null;
  completed_section_ids: string[];
  completed_required_sections: number;
  required_section_count: number;
  completion_percentage: number;
  content_complete: boolean;
  review_reason: string | null;
  updated_at: string | null;
};
export type LearningSession = { session_id: string; profile_id: string; lesson_id: string; started_at: string; resumed: boolean; progress: LessonProgress };
export type AnswerFeedback = {
  attempt_id: string;
  evidence_id: string;
  question_id: string;
  attempt_number: number;
  is_correct: boolean;
  submitted_response: Record<string, unknown>;
  expected_answer: string;
  explanation: string;
  feedback_message: string;
  submitted_at: string;
  content_version: string;
  idempotent_replay: boolean;
  processing?: { interaction: "saved"; evidence: "recorded"; behavioral_state: "updated"; behavioral_state_version: number } | null;
  recommendation?: RecommendationDecision | null;
};
export type RecommendationDecision = {
  status: "personalized" | "more_evidence_needed";
  message: string;
  source_behavioral_state_version: number | null;
  recommendation: {
    recommendation_id: string;
    learner_id: string;
    activity: { activity_type: "review_lesson" | "continue_lesson" | "additional_practice"; topic_id: string; lesson_id: string; title: string };
    reason: string;
    supporting_evidence_ids: string[];
    source_behavioral_state_version: number;
    created_at: string;
    status: "current" | "superseded";
    limitations: string[];
  } | null;
};
export type StudentRecommendation = { profile: Profile; decision: RecommendationDecision };
export type CourseProgress = {
  course_id: string;
  subject_id: string;
  title: string;
  status: "not_started" | "in_progress" | "completed" | "needs_review";
  lessons_completed: number;
  lesson_count: number;
  completion_percentage: number;
  topics_started: number;
  practice_attempts: number;
  correct_attempts: number;
  response_accuracy: number | null;
};
export type StudentProgress = {
  profile: Profile;
  summary: {
    courses_started: number;
    topics_started: number;
    lessons_started: number;
    lessons_completed: number;
    lessons_needing_review: number;
    lesson_sections_completed: number;
    lesson_sections_total: number;
    practice_attempts: number;
    correct_attempts: number;
    incorrect_attempts: number;
    response_accuracy: number | null;
  };
  courses: CourseProgress[];
  recent_lesson_ids: string[];
  updated_at: string | null;
};
export type HistoryEntry = {
  entry_id: string;
  event_type: "lesson_started" | "answer_submitted";
  occurred_at: string;
  course_id: string;
  topic_id: string;
  lesson_id: string;
  lesson_title: string;
  question_id: string | null;
  is_correct: boolean | null;
  attempt_number: number | null;
  content_version: string;
};
export type LearningHistory = { profile: Profile; items: HistoryEntry[]; total: number };
export type TopicBehavioralSummary = {
  concept_id: string;
  attempts: number;
  correct: number;
  incorrect: number;
  historical_accuracy: number | null;
  recent_accuracy: number | null;
  smoothed_performance: number;
  performance_trend: "improving" | "declining" | "stable" | "insufficient_evidence";
  performance_change: number | null;
  evidence_count: number;
  evidence_sufficiency: "none" | "low" | "moderate" | "high";
  estimate_confidence: "low" | "moderate" | "high";
  last_observed_interaction: { question_id: string | null; timestamp: string | null } | null;
};
export type StudentBehavioralState = {
  profile: Profile;
  source: "student_studio_interactions";
  state: {
    schema_version: string;
    student_studio_state_schema_version: string;
    state_timestamp: string | null;
    topic_states: TopicBehavioralSummary[];
  };
  state_version: number | null;
  previous_state_version: number | null;
  supporting_evidence_ids: string[];
};

export function createLearningService(client: ApiClient) {
  return {
    catalog: (signal?: AbortSignal) => client.get<CurriculumCatalog>("/curriculum", { signal }),
    search: (query: string, signal?: AbortSignal) => client.get<TopicDetails[]>(`/curriculum/search?q=${encodeURIComponent(query)}`, { signal }),
    topic: (topicId: string, signal?: AbortSignal) => client.get<TopicDetails>(`/curriculum/topics/${encodeURIComponent(topicId)}`, { signal }),
    lesson: (lessonId: string, signal?: AbortSignal) => client.get<Lesson>(`/curriculum/lessons/${encodeURIComponent(lessonId)}`, { signal }),
    generateLesson: (body: LessonGenerationRequest, signal?: AbortSignal) => client.post<LessonGenerationResult, typeof body>("/studio/lessons/generate", body, { signal }),
    aiStatus: (signal?: AbortSignal) => client.get<StudentAIStatus>("/studio/ai/status", { signal }),
    askTutor: (lessonId: string, body: { session_id: string; turn_id: string; message: string; level: "beginner" | "intermediate" | "advanced"; section_id?: string }, signal?: AbortSignal) => client.post<TutorAnswer, typeof body>(`/studio/lessons/${encodeURIComponent(lessonId)}/tutor`, body, { signal }),
    tutorHistory: (lessonId: string, sessionId: string, signal?: AbortSignal) => client.get<TutorMessage[]>(`/studio/lessons/${encodeURIComponent(lessonId)}/tutor/history?session_id=${encodeURIComponent(sessionId)}`, { signal }),
    practice: (lessonId: string, signal?: AbortSignal) => client.get<Practice>(`/curriculum/lessons/${encodeURIComponent(lessonId)}/practice`, { signal }),
    profile: (signal?: AbortSignal) => client.get<Profile>("/studio/profile", { signal }),
    startSession: (lessonId: string, signal?: AbortSignal) => client.post<LearningSession, { lesson_id: string }>(`/studio/lessons/${encodeURIComponent(lessonId)}/sessions`, { lesson_id: lessonId }, { signal }),
    saveProgress: (lessonId: string, body: { session_id: string; current_section_id: string; completed_section_ids: string[] }, signal?: AbortSignal) => client.post<LessonProgress, typeof body>(`/studio/lessons/${encodeURIComponent(lessonId)}/progress`, body, { signal }),
    submitAnswer: (questionId: string, body: { submission_id: string; session_id: string; response: Record<string, unknown> }, signal?: AbortSignal) => client.post<AnswerFeedback, typeof body>(`/studio/questions/${encodeURIComponent(questionId)}/answer`, body, { signal }),
    progress: (signal?: AbortSignal) => client.get<StudentProgress>("/studio/progress", { signal }),
    behavioralState: (signal?: AbortSignal) => client.get<StudentBehavioralState>("/studio/behavioral-state", { signal }),
    recommendation: (signal?: AbortSignal) => client.get<StudentRecommendation>("/studio/recommendation", { signal }),
    topicBehavioralState: (topicId: string, signal?: AbortSignal) => client.get<{
      profile: Profile; source: "student_studio_interactions"; topic_id: string;
      state: TopicBehavioralSummary | null; state_version: number | null;
      history: { state_version: number; state_timestamp: string; evidence_count: number; state: TopicBehavioralSummary; supporting_evidence_ids: string[] }[];
      total: number;
    }>(`/studio/behavioral-state/topics/${encodeURIComponent(topicId)}`, { signal }),
    history: (signal?: AbortSignal) => client.get<LearningHistory>("/studio/history?limit=100", { signal }),
  };
}

export function getLearningService() {
  return createLearningService(getApiClient());
}
