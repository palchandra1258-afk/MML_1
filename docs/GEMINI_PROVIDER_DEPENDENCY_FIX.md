# Gemini provider dependency and live verification report

**Date:** 20 November 2026

## Result

The original dependency failure was real: `google-genai` was listed in `requirements-api.txt`, but it was not installed in the project's `.venv-api`. The provider imports the official SDK using `from google import genai` and `from google.genai import types`. Installing the declared requirements in `.venv-api` resolved that import problem.

After dependency repair, one authorized request to the existing lesson-generation endpoint returned `503 AI_MODEL_UNAVAILABLE` for `gemini-2.5-flash`. The generation service stopped before lesson validation or persistence. No second generation request was sent. As a result, real Gemini lesson generation and persistence are **not verified**.

Google's current deprecation page says Gemini 2.5 Flash access is limited to projects that have actively used it, and lists 1 December 2026 as the shutdown date. That is consistent with the model-unavailable response. The response cannot establish whether this specific project lacks prior-use eligibility or whether the model identifier is otherwise unavailable to it. Google's page recommends `gemini-3.5-flash-lite` as the replacement. The backend configuration was not changed automatically. See [Gemini model deprecations](https://ai.google.dev/gemini-api/docs/deprecations#gemini-2.5-flash-models) and [model access guidance from the Gemini API team](https://discuss.ai.google.dev/t/does-existing-gemini-2-5-flash-access-survive-a-billing-account-change/201155).

## Findings and changes

- Required package: `google-genai`; installed version: **2.34.0**, compatible with the declared `google-genai>=1,<3` range.
- The active interpreter was `.venv-api/bin/python`; `google.genai` and `google.genai.types` imported successfully, and the installed SDK accepted the configured `HttpOptions` and JSON `GenerateContentConfig` types.
- With the private backend environment sourced, provider initialization selected `gemini`, model `gemini-2.5-flash`, and configuration status was ready. This check makes no model request.
- Dependency diagnostics now distinguish a missing distribution, an unsupported SDK version, a missing transitive import, provider authentication/model errors, network errors, rate limits, and timeouts. Diagnostics and API errors do not include credential values or raw provider exception text.
- The Gemini client is configured for one SDK attempt per request. Azure support and the existing lesson-generation architecture remain intact.
- `requirements-api.txt` already declared `google-genai>=1,<3`; no dependency-file edit was needed for this repair. No environment file was modified.

## Verification evidence

The backend returned HTTP 200 from `GET /api/v1/studio/ai/status`, reporting Gemini selected, configured, generation available, and model `gemini-2.5-flash`. The response contained no API-key field.

Exactly one `POST /api/v1/studio/lessons/generate` request was made with topic Geography, subject Geography, and beginner level. It returned HTTP 503 with code `AI_MODEL_UNAVAILABLE`. No lesson response, model token usage, saved lesson, or practice record was produced. The attempted call's billing/quota treatment was not returned by the API response.

The configured SQLite database was checked read-only after the request: Alembic revision remained `0005_azure_interactive_learning`; `studio_generated_lessons` contained zero rows; `PRAGMA integrity_check` returned `ok`; and `PRAGMA foreign_key_check` returned no violations. Automatic migrations were disabled when starting the backend. No Azure request or migration was made.

### Tests and checks

- `PYTHONPATH=src .venv-api/bin/pytest -q tests/api/test_text_generation_providers.py tests/api/test_interactive_learning.py tests/api/test_azure_openai.py` — **29 passed**. These tests use mocks and make no provider requests.
- `npm run test:api` — **9 passed**.
- `npm run lint -- --no-warn-ignored` — passed.
- `npx tsc --noEmit -p tsconfig.json` — passed.
- `PYTHONPATH=src .venv-api/bin/python scripts/api/export_openapi.py` — passed.
- `git diff --check` — passed.
- `.env.backend` remains ignored by Git. No Azure or Gemini key value was displayed or logged; no frontend file contains either key variable.

## Files changed for this repair

- `src/mcp_ri/api/text_generation.py`
- `tests/api/test_text_generation_providers.py`
- `docs/AI_LESSON_GENERATION.md`
- `docs/GEMINI_PROVIDER_DEPENDENCY_FIX.md`

The `.venv-api` environment was updated by installing the already-declared dependency and its required transitive packages. Existing uncommitted work was preserved.

## Restart and next step

From the repository root, install requirements if the environment is recreated and restart the backend with the configured provider variables:

```bash
.venv-api/bin/python -m pip install -r requirements-api.txt
set -a
. ./.env.backend
set +a
PYTHONPATH=src .venv-api/bin/uvicorn mcp_ri.api.main:app --host 127.0.0.1 --port 8000
```

Before another generation attempt, select a model that the configured Gemini project can access. Do not repeat the call with `gemini-2.5-flash` unless that project's eligibility is confirmed. This report does not claim successful real Gemini generation.
