import type { LessonGenerationRequest, LessonGenerationResult } from "../services/learning.service";

export type LessonGenerationState =
  | { status: "loading" }
  | { status: "success"; lessonId: string }
  | { status: "error"; message: string };

type GenerationResponse = { data?: LessonGenerationResult };

/** Runs the UI-facing generation lifecycle so loading, success, and errors stay observable. */
export async function runLessonGeneration(
  request: LessonGenerationRequest,
  generate: (request: LessonGenerationRequest) => Promise<GenerationResponse>,
  onState: (state: LessonGenerationState) => void,
): Promise<void> {
  onState({ status: "loading" });
  try {
    const result = await generate(request);
    const lessonId = result.data?.lesson?.lesson_id;
    if (!lessonId) throw new Error("The backend returned no generated lesson. Please try again.");
    onState({ status: "success", lessonId });
  } catch (error) {
    onState({
      status: "error",
      message: error instanceof Error ? error.message : "Lesson generation failed. Please try again.",
    });
  }
}
