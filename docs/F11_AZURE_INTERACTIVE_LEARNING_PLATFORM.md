# F11 — Azure Interactive Learning Platform

**Status:** Azure lesson generation, lesson persistence, tutor conversations, and the curated Studio path are implemented in source. The backend flow is verified with mocked Azure responses on temporary SQLite databases. A live Azure workflow and browser workflow remain unverified because no Azure credentials or deployment were provided. This is a local-demo feature, not a multi-user service.

## Dependency-aware implementation plan and outcome

1. Preserve the curated F9 catalog and existing F10.1 canonical evidence path. **Done.** Existing curated lookup and grading remain in use.
2. Add server-only Azure configuration, bounded REST client behavior, structured content validation, and additive persistence. **Implemented and verified** with unit tests and migration upgrade/downgrade/re-upgrade on disposable SQLite.
3. Route generated lessons through the existing session, progress, grading, evidence, and Phase 9 aggregate behavior paths. **Implemented and API-tested** with generated synthetic lesson fixtures; no live model output is claimed.
4. Add the student discovery, explicit generate action, inline checkpoints, tutor history, assessment feedback, and progress recommendation surfaces. **Implemented in the frontend.** TypeScript, lint, and service tests pass; browser rendering is not verified.
5. Continue into Phase 11 cognitive estimates, Phase 12 representation delivery, and Phase 13 trajectories only when their grounding and capability prerequisites are met. **Pending.** F9/F10.1 confirms Studio topics have no reviewed mapping to research concepts, no available representation providers, and no supported Studio objective/prerequisite graph. These integrations remain unavailable.

## Architecture and boundaries

```text
Topic search (curated only; no model request while typing)
  ├─ exact curated lesson → existing lesson workflow
  └─ student selects Generate → Azure JSON response → Pydantic validation
       → immutable generated lesson/question snapshot (SQLite)
       → lesson session/section checkpoints/server grading
       → F10.1 canonical evidence → versioned Phase 9 response summary
       → conservative activity recommendation

Lesson session → Azure tutor with lesson/section and prior turns
  → append-only tutor history; lesson definitions and assessment records are unchanged
```

The Azure deployment is a text-generation deployment. `gpt-realtime` is not used. The API key, endpoint, deployment name, and API version are read only by the backend from environment variables; no frontend setting or response contains the key or endpoint. The status endpoint reports missing variable names, not their values.

## Configuration

Set these in the backend process environment or a backend-only secret store. For local development, the repository root `.env.backend` is the supported file location. It is intentionally separate from `frontend/.env.local`; the backend reads process environment variables and does not load frontend configuration files.

| Variable | Purpose |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | HTTPS Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | Backend API key |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Text-generation deployment name; must not be `gpt-realtime` |
| `AZURE_OPENAI_API_VERSION` | Azure API version |
| `AZURE_OPENAI_TIMEOUT_SECONDS` | Request timeout, clamped to 1–120 seconds; default 30 |
| `AZURE_OPENAI_MAX_RETRIES` | Retry count, clamped to 0–5; default 2 |

`GET /api/v1/studio/ai/status` reports configuration readiness. Generation and tutor calls return `AI_NOT_CONFIGURED` and list the exact missing variables when required settings are absent. They do not return fabricated content. The REST client uses bounded `max_completion_tokens`, a JSON response format, server-side Pydantic validation, bounded timeout/retry handling, safe provider errors, and token-usage metadata when Azure provides it. Authentication failures, throttling, provider errors, invalid responses, and timeouts have distinct safe error codes. Incoming AI calls are limited to 12 per minute per client IP in one process; this is a local cost guard, not a distributed quota.

The tracked `.env.backend.example` contains blank values only. Create a private local copy and fill it with a local editor; do not paste credentials into shell commands, frontend variables, source files, or chat:

```bash
cd /home/mml_07/Desktop/MML
install -m 600 .env.backend.example .env.backend
nano .env.backend
```

Use shell-compatible quoted assignments, for example `AZURE_OPENAI_API_KEY='value'`. Then load the file only into the backend shell and start the server:

```bash
set -a
. ./.env.backend
set +a
PYTHONPATH=src .venv-api/bin/uvicorn mcp_ri.api.main:app --reload --host 127.0.0.1 --port 8000
```

The root `.gitignore` excludes `.env` and `.env.*` files and allows only the blank `.env.backend.example` template. Frontend settings stay in `frontend/.env.local`; never put Azure values in a `NEXT_PUBLIC_*` variable. The backend settings and REST client are the only application code that read Azure credentials.

Check configuration readiness without making an Azure request:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/studio/ai/status
```

This reports whether required settings are present and the deployment name; it does not reveal the key or endpoint and does not prove provider connectivity. The prepared connection checker defaults to no network request. Its explicit connectivity mode sends one small chat-completions request and may incur Azure usage charges:

```bash
PYTHONPATH=src .venv-api/bin/python scripts/api/check_azure_connection.py
PYTHONPATH=src .venv-api/bin/python scripts/api/check_azure_connection.py --send-request
```

The first command validates local configuration only. The second is opt-in and prints only a success result or safe error code/message; it withholds credentials, endpoint, prompt, response content, and raw provider exceptions. No live Azure request is part of setup or migration verification.

Usage counts are retained with generated lesson records and returned with tutor responses, but no currency estimate is shown because the configured model/pricing was not supplied.

## Lesson generation and student workflow

`GET /api/v1/curriculum/search?q=...` continues to search curated records only. Typing does not contact Azure. After no curated match, the student explicitly selects **Generate lesson**, chooses a learning level, and submits a topic. The backend checks for an exact curated lesson first; on a hit it returns that lesson without an Azure request.

For new topics, the service requires objectives, at least three sections, and three to twelve questions. It validates section/objective identifiers, block schemas, question types, grading rules, options, and answer-key references. Choice and numeric questions use the existing server-side evaluator. Generated answer keys are stored with the private grading record and omitted from lesson/practice responses until after submission. Open-ended AI grading is not implemented.

Generated records include topic, subject, selected level, lesson title, duration, content version, generation source, sections, and validated questions. `0005_azure_interactive_learning` adds `studio_generated_lessons` and `studio_tutor_interactions`; records are versioned and preserved. Request IDs prevent a successful generate retry from creating another record or paying for a second model call. A reused ID with changed input returns a conflict.

The existing lesson route displays inline checkpoints from the lesson’s question set; the practice route presents the remaining assessment questions. Each answer is graded on the server against the exact saved question/version and creates an append-only attempt plus canonical F10.1 evidence. Saved section progress, generated lesson history, response feedback, the Phase 9 aggregate, and the backend’s completion/correctness-driven recommendation are available. Recommendations are labeled as behavioral activity suggestions, not mastery decisions.

The tutor receives the saved lesson, current section, requested level, and up to the latest 20 stored turns from that study session. Its prompt does not include grading keys. User/assistant turns are stored only after a successful provider response; turn IDs make successful retries idempotent. Tutor text is labeled supplementary and cannot change the persisted lesson or answer records. Tutor history is restored for the resumed lesson session.

## Persistence, migration, and identity

Migration `0005_azure_interactive_learning` is additive and downgrades by dropping only the two new tables. Upgrade, downgrade, and re-upgrade were tested on a temporary SQLite database. No migration was run against the configured application database during F11.

The migration chain is linear from `0001_initial` through `0005_azure_interactive_learning`. Migration 0005 creates `studio_generated_lessons` and `studio_tutor_interactions` and references the existing `studio_learning_sessions` table. It does not rewrite or backfill existing F9/F10.1 rows. The local configured database inspected on 20 November 2026 was at revision `0004_f10_1_learning_evidence`, so it lacks the two 0005 tables. Startup migration is disabled by default.

**Do not run the following until the configured database has been reviewed and a consistent backup has been verified.** Stop the backend first. For the default database, a SQLite backup can be made without overwriting an existing backup:

```bash
umask 077
.venv-api/bin/python - <<'PY'
from pathlib import Path
import sqlite3

source_path = Path("data/application/mcp_ri.sqlite3")
backup_path = Path("data/application/mcp_ri.pre-0005.sqlite3")
if backup_path.exists():
    raise SystemExit(f"Refusing to overwrite existing backup: {backup_path}")
source = sqlite3.connect(source_path)
backup = sqlite3.connect(backup_path)
try:
    source.backup(backup)
    result = backup.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"Backup integrity check failed: {result}")
finally:
    backup.close()
    source.close()
backup_path.chmod(0o600)
print(f"Verified SQLite backup: {backup_path}")
PY
```

After the backup and migration plan are reviewed and approved, apply the migration explicitly:

```bash
PYTHONPATH=src .venv-api/bin/python scripts/api/migrate_database.py
```

Then verify the Alembic revision, that both new tables exist, and `PRAGMA integrity_check` before restarting the API. The 0005 downgrade drops `studio_generated_lessons` and `studio_tutor_interactions`; after those tables contain data, a downgrade is not data-preserving. Preserve the backup as the rollback path or forward-fix the schema. Restoring a pre-migration backup also discards all database writes made after that backup, so stop the service and account for those writes before restore.

API startup no longer creates or migrates tables by default. `MCP_RI_AUTO_MIGRATE=true` is an explicit opt-in. Unit/API test apps create their own temporary schemas. The existing fixed `studio-local-demo` profile remains unauthenticated and shared. It is not multi-user isolation or suitable for public deployment.

## MCP-RI evidence and downstream state

Generated lesson answers use the existing `StudentStudioInteractionAdapter` and canonical Phase 10 schema, with `mcp-ri-student-studio` provenance, source attempt ID, lesson/version, question, topic, submitted response, server evaluation, and timestamp. Evidence is persisted separately from EdNet records and transactionally linked to the attempt. Existing submission IDs and database uniqueness constraints keep answer/evidence retries idempotent.

The actual Phase 9 accumulator consumes the Studio response stream and emits immutable aggregate snapshots. Generated topic IDs can have descriptive response summaries, but are not asserted to map to EdNet skills. Correctness remains observed behavior, not proof of understanding.

Phase 11 cognitive estimates remain unavailable for Studio topics because no validated topic/concept map exists. Phase 12 planning and delivery remain unavailable because no Studio concept grounding or executable delivery providers exist. Phase 13 Studio trajectories remain unavailable because there is no reviewed objective/prerequisite graph. No cognitive state or effectiveness result is fabricated.

## API contract and key files

The generated OpenAPI contract is `shared/api-contracts/openapi.json`.

| API | Purpose |
|---|---|
| `GET /api/v1/studio/ai/status` | Safe Azure readiness diagnostics |
| `POST /api/v1/studio/lessons/generate` | Curated precedence, explicit Azure generation, validation, and persistence |
| `GET /api/v1/curriculum/lessons/{lesson_id}` | Curated or persisted generated lesson |
| `GET /api/v1/curriculum/lessons/{lesson_id}/practice` | Public generated/curated questions with grading keys removed |
| `POST /api/v1/studio/lessons/{lesson_id}/tutor` | Contextual Azure tutor turn |
| `GET /api/v1/studio/lessons/{lesson_id}/tutor/history` | Persisted session tutor history |
| Existing `/studio/*` session, progress, answer, evidence, behavioral-state and recommendation routes | Reused Studio persistence/evaluation path |

Implementation is in `src/mcp_ri/api/azure_openai.py`, `learning_service.py`, `learning_schemas.py`, `learning_routes.py`, `persistence.py`, `migrations/versions/0005_azure_interactive_learning.py`, `frontend/lib/services/learning.service.ts`, and `frontend/components/studio/student-studio-client.tsx`.

## Verification and status

- Azure client unit tests cover missing configuration, request headers/JSON mode/usage, bounded retries, timeout, rate-limit, and authentication failures.
- Generated API workflow tests use a validated fixture response, not a mock presented as live Azure acceptance. They cover curated precedence, generation persistence/replay, public answer-key removal, dynamic session/practice, grading, evidence, behavioral state, recommendations, tutor, and persisted history.
- Migration upgrade/downgrade/re-upgrade passed on a temporary database.
- Frontend `npm run test:api`, `npx tsc --noEmit`, and `npm run lint` passed.
- `PYTHONPATH=src .venv-api/bin/python -m pytest tests/api -q`: **51 passed**. `scripts/api/export_openapi.py` regenerated the checked-in contract, and the API suite asserts it matches.
- Full Python unit discovery: 133 tests, 130 passed, 1 skipped, and 2 module import errors because `joblib` and `numpy` are unavailable. No training packages were installed.
- `git diff --check`: passed.
- Production `npm run build` still fails in Next.js 16.4.6 with `Could not parse output from TypeScript's --showConfig`; direct TypeScript passes. Browser workflow has not been verified.
- Live Azure generation/tutor and Azure authentication/timeout/throttling against the provider remain unverified because backend Azure settings were not supplied; equivalent failures are covered with injected client responses.

## Remaining work and limitations

- No authentication, per-learner isolation, distributed AI quota, or production deployment controls.
- Live Azure credential/deployment configuration and a real end-to-end generated lesson review are still required.
- No web citations or independent fact-checking are performed for generated content.
- Generated content quality, factual accuracy, and educational effectiveness have not been evaluated.
- Tutor output may be wrong; it is supplementary and should be reviewed.
- Only choice and numeric answer grading is supported; no AI/open-ended grading.
- Studio does not connect to Phase 11/12/13 until reviewed topic mapping, capability, and objective prerequisites are established.
- Frontend production build/browser acceptance remains outstanding.
