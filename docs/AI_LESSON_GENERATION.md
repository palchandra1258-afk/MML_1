# Student Studio AI lesson generation

## Architecture

The Explore Subjects page keeps the entered topic and selected learning level in `StudentStudioClient`. After a search finds no curated match, the student can explicitly request a generated lesson. The frontend calls `POST /api/v1/studio/lessons/generate` through the shared API client. It shows a pending state, routes to the returned lesson on success, and displays a retryable error on failure.

FastAPI validates the request with `LessonGenerationRequest`. `LearningService.generate_lesson` first returns an existing result for an identical request ID, rejects reuse of that ID with different input, and prefers an exact curated match without contacting a provider. Otherwise it calls the backend-selected JSON text-generation adapter. `AI_PROVIDER=azure` (the default) uses the existing Azure adapter and rejects `gpt-realtime` before network I/O; `AI_PROVIDER=gemini` uses Google's official `google-genai` SDK; `AI_PROVIDER=mock` returns explicitly labeled test content and is not AI generation.

The service validates the provider draft against `GeneratedLessonDraft`, converts it to the existing `LessonContent` and `QuestionRecord` schemas, and stores the lesson and grading data in `studio_generated_lessons` (migration `0005_azure_interactive_learning`). The endpoint commits the row and returns `LessonGenerationResult`. Lesson retrieval and practice use the existing curriculum lesson and grading routes; answer keys remain server-side.

Azure lessons retain `content_source: "azure_generated"` and `generation_source: "azure_openai"`; Gemini uses `gemini_generated` / `gemini`. Mock lessons use `mock_generated` / `mock` and explicitly state that they are not AI generated. All provider output passes through the same lesson, question, and grading validation before persistence. AI-generated material should be reviewed because it may contain errors and has not been independently verified.

## API

Request:

```json
{
  "request_id": "client-generated-unique-id",
  "topic": "Geography",
  "subject": "Geography",
  "level": "beginner"
}
```

`topic` and `request_id` are required. `subject` defaults to `General learning`; `level` is `beginner`, `intermediate`, or `advanced` and defaults to `beginner`.

Success is the standard API envelope containing:

```json
{
  "lesson": {
    "lesson_id": "...",
    "title": "...",
    "content_source": "azure_generated",
    "generation_source": "azure_openai",
    "learning_level": "beginner",
    "sections": []
  },
  "question_count": 5,
  "usage": null,
  "notice": "AI-generated lesson saved. Review it as generated learning material."
}
```

The API may return a different question count within the existing schema limits. Successful provider output is persisted before the response is returned. Repeating the same request ID and same input returns the stored result without another provider call; reusing the ID with different input returns `409 GENERATION_ID_REUSED`.

## Provider configuration

Azure settings are read only by the backend from process environment variables when `AI_PROVIDER=azure`:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_VERSION`
- Optional bounded settings: `AZURE_OPENAI_TIMEOUT_SECONDS` and `AZURE_OPENAI_MAX_RETRIES`

For local development, the private repository-root `.env.backend` is the supported file. The backend does not implicitly load it. Use shell-compatible assignments, then load it in the backend shell without tracing commands:

```bash
set -a
. ./.env.backend
set +a
PYTHONPATH=src .venv-api/bin/uvicorn mcp_ri.api.main:app --host 127.0.0.1 --port 8000
```

Never put these values in frontend settings or `NEXT_PUBLIC_*` variables. `.env.backend` is excluded from Git. `GET /api/v1/studio/ai/status` reports whether the current backend process has the required variables, whether the deployment is supported for lesson generation, any missing variable names, and the deployment name; it does not make an Azure request and does not prove connectivity.

For Gemini, set `AI_PROVIDER=gemini`, `GEMINI_API_KEY`, and `GEMINI_MODEL` in the same private backend-root `.env.backend` file and source it before starting the backend. No Azure settings are required when Gemini is selected. The status endpoint reports local configuration only. See [`GEMINI_PROVIDER_SETUP.md`](GEMINI_PROVIDER_SETUP.md).

The supported SDK dependency is `google-genai>=1,<3`. Install it into the active backend interpreter with `.venv-api/bin/python -m pip install -r requirements-api.txt`. `GET /api/v1/studio/ai/status` verifies local SDK import and configuration only; it does not prove the selected project can access the configured model. Only a successful generation request verifies remote credentials, model access, response validation, and persistence.

Azure lesson generation uses Chat Completions. A realtime/speech deployment such as `gpt-realtime` is not compatible and is rejected locally. Gemini requires a model identifier accessible to the user's account; no model name is assumed or discovered here. No output substitutes for missing AI generation, except the explicit test-only mock, which is visibly labeled.

## Errors and retry behavior

The API returns the stable error envelope with safe messages. Common generation errors include:

- `AI_NOT_CONFIGURED` (503): one or more required process variables are missing.
- `AI_DEPENDENCY_MISSING` (503): the `google-genai` package is not installed in the backend environment; install requirements using `.venv-api/bin/python -m pip install -r requirements-api.txt`.
- `AI_DEPENDENCY_ERROR` (503): `google-genai` is present but one of its Python imports failed; reinstall the declared requirements in `.venv-api` and inspect the missing module name.
- `AI_CONFIGURATION_INVALID` (503): invalid endpoint settings or an unsupported realtime deployment.
- `AI_CONTENT_INVALID` (502): provider content does not validate against the lesson/question schemas.
- `AI_INVALID_RESPONSE` (502): provider returned malformed structured JSON.
- `AI_AUTHENTICATION_FAILED` (502): Azure rejected credentials or deployment access.
- `AI_MODEL_UNAVAILABLE` (503): the configured Gemini model is unavailable to this project or the model identifier is invalid.
- `AI_PROVIDER_UNAVAILABLE` (503): the selected provider SDK is missing or the provider is temporarily unavailable.
- `AI_CONFIGURATION_INVALID` (503): provider selection, model, endpoint, or request configuration is invalid.
- `AI_TIMEOUT` (504): provider request timed out.
- `AI_NETWORK_ERROR` (502): the backend could not connect to Gemini.
- `AI_RATE_LIMITED` (429): provider or local request limit was reached.
- `AI_PROVIDER_ERROR` (502): other provider failures.

The frontend shows a loading status and disables duplicate submissions while generation is pending. On failure, it displays the API's safe message and a retry button. The topic and selected level remain in the form. A successful response navigates to the saved lesson; failures do not persist a generated lesson.

## Tests

Run backend generation and provider tests without any Azure calls:

```bash
PYTHONPATH=src .venv-api/bin/pytest -q tests/api/test_interactive_learning.py tests/api/test_azure_openai.py
```

Run frontend API and generation-workflow tests:

```bash
cd frontend
npm run test:api
```

Automated backend generation tests mock provider calls and cover valid lesson persistence/retrieval, duplicate request handling, schema rejection, missing configuration, timeouts, Azure selection, Gemini SDK response mapping, and explicit mock output. Frontend workflow tests cover pending, success, error, and retry state transitions. Tests do not call Azure or Gemini.

## Current verification limits

Mocked provider and persistence tests do not establish remote credentials or model availability. No live Azure or Gemini request was made for this implementation. A backend process started without sourcing `.env.backend` reports the selected provider as unconfigured even if the file exists. The configured Azure `gpt-realtime` deployment remains unsupported for text generation; Gemini can be tested only after the user configures an account-available model and approves a provider request.
