/* eslint @typescript-eslint/no-require-imports: off */
const test = require("node:test");
const assert = require("node:assert/strict");
const { runLessonGeneration } = require("../../.api-test-dist/lib/studio/lesson-generation.js");

const request = { request_id: "request-1", topic: "Geography", subject: "General learning", level: "beginner" };

test("lesson generation exposes loading and success states with the saved lesson ID", async () => {
  const states = [];
  let resolveGeneration;
  const pending = runLessonGeneration(request, (received) => {
    assert.equal(received, request);
    return new Promise((resolve) => { resolveGeneration = resolve; });
  }, (state) => states.push(state));

  assert.deepEqual(states, [{ status: "loading" }]);
  resolveGeneration({ data: { lesson: { lesson_id: "ai-lesson-1" } } });
  await pending;
  assert.deepEqual(states, [{ status: "loading" }, { status: "success", lessonId: "ai-lesson-1" }]);
});

test("lesson generation exposes provider errors and can be retried", async () => {
  const states = [];
  let attempts = 0;
  const generate = async () => {
    attempts += 1;
    if (attempts === 1) throw new Error("The configured deployment cannot generate text lessons.");
    return { data: { lesson: { lesson_id: "ai-lesson-retry" } } };
  };

  await runLessonGeneration(request, generate, (state) => states.push(state));
  await runLessonGeneration(request, generate, (state) => states.push(state));
  assert.deepEqual(states, [
    { status: "loading" },
    { status: "error", message: "The configured deployment cannot generate text lessons." },
    { status: "loading" },
    { status: "success", lessonId: "ai-lesson-retry" },
  ]);
});

test("missing generated lesson data becomes a visible workflow error", async () => {
  const states = [];
  await runLessonGeneration(request, async () => ({ data: undefined }), (state) => states.push(state));
  assert.deepEqual(states, [
    { status: "loading" },
    { status: "error", message: "The backend returned no generated lesson. Please try again." },
  ]);
});
