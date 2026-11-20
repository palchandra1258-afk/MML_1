# Gemini provider setup

Student Studio lesson generation now selects its text provider in the backend. The existing Azure adapter and lesson validation, persistence, retrieval, and server-side grading remain in place. Gemini uses Google's official `google-genai` Python package (`google-genai>=1,<3`). No model name is bundled because availability varies by account and changes over time.

## Configure a personal key

Create a Gemini API key through Google's official AI Studio, then add these values to the **repository-root** `.env.backend` file (not `frontend/.env.local`):

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_personal_key
GEMINI_MODEL=your_account_available_text_model
```

Keep the existing Azure variables in that file unchanged. Do not put the key in `NEXT_PUBLIC_*`, frontend configuration, source code, logs, or Git. `.env.backend` is ignored by Git; `.env.backend.example` contains blank placeholders only. The backend reads process environment, not `.env.backend` automatically.

Install backend dependencies if needed:

```bash
.venv-api/bin/pip install -r requirements-api.txt
```

From the repository root, load the private file into the backend process environment and start the server:

```bash
set -a
. ./.env.backend
set +a
PYTHONPATH=src .venv-api/bin/uvicorn mcp_ri.api.main:app --host 127.0.0.1 --port 8000
```

`AI_PROVIDER` accepts `azure`, `gemini`, or `mock`. `mock` produces explicit test content and is not AI generation. Azure remains the default if `AI_PROVIDER` is omitted. Gemini selection does not require Azure settings. The `/api/v1/studio/ai/status` endpoint checks local configuration only; it makes no provider request and cannot prove that a key or model is accepted by the remote service.

To run no-network checks:

```bash
PYTHONPATH=src .venv-api/bin/pytest -q tests/api/test_text_generation_providers.py tests/api/test_interactive_learning.py tests/api/test_azure_openai.py
```

Real Gemini connectivity and model availability have not been verified here. No provider request is made by these tests. Request approval before conducting an actual Gemini request.

## Troubleshooting

- `AI_NOT_CONFIGURED`: verify the backend shell has `GEMINI_API_KEY` and `GEMINI_MODEL`; do not paste their values into logs or support messages.
- `AI_DEPENDENCY_MISSING`: install the backend requirements into `.venv-api` with `.venv-api/bin/python -m pip install -r requirements-api.txt`.
- `AI_DEPENDENCY_ERROR`: the SDK is installed but a transitive import is missing; reinstall requirements in `.venv-api` and use the reported module name to diagnose the environment.
- `AI_AUTHENTICATION_FAILED`: the provider rejected the configured credential; check it privately in AI Studio and update `.env.backend`.
- `AI_MODEL_UNAVAILABLE`: the selected model is not available to the account or the model identifier is wrong.
- `AI_RATE_LIMITED`, `AI_TIMEOUT`, `AI_NETWORK_ERROR`, or `AI_PROVIDER_ERROR`: check provider status/account limits and retry later.
- `AI_CONTENT_INVALID`: provider output did not pass the existing lesson schema and grading validation; malformed output is not persisted.
