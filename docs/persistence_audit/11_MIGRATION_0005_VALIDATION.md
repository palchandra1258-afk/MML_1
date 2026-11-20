# 11 — Migration 0005 compatibility and validation

**Scope:** validate `0005_azure_interactive_learning` against the configured database by read-only inspection and disposable SQLite copies only. No migration was applied to the configured database. No Azure request was made.

## A. Existing revision and migration ancestry

The configured file is `data/application/mcp_ri.sqlite3`; read-only inspection found Alembic revision `0004_f10_1_learning_evidence` and metadata contract `migrations/0004_f10_1_learning_evidence`. The migration chain is linear:

```text
0001_initial
  → 0002_learning_studio
  → 0003_f10_learning_intelligence
  → 0004_f10_1_learning_evidence
  → 0005_azure_interactive_learning
```

`0005_azure_interactive_learning` declares `down_revision = "0004_f10_1_learning_evidence"`, with no branch labels or dependencies. The configured database is not at 0005. Application settings currently name 0005 as the model schema contract, while app startup does not run migrations by default. Do not enable automatic migration as a substitute for this reviewed rollout.

## B. Exact changes and ORM comparison

The migration creates two tables, two named unique constraints, two named indexes, one foreign key, and updates `app_metadata.schema_contract` to 0005. It does not alter, backfill, or drop any existing Student Studio table.

### `studio_generated_lessons`

| Column | SQLite/SQLAlchemy type | Nullable | Key/default |
| --- | --- | --- | --- |
| `lesson_id` | `String(160)` | No | Primary key |
| `request_id` | `String(160)` | No | Unique constraint `uq_studio_generated_request_id` |
| `request_hash` | `String(64)` | No | — |
| `topic_id` | `String(160)` | No | — |
| `subject` | `String(160)` | No | — |
| `learning_level` | `String(24)` | No | — |
| `content_version` | `String(40)` | No | — |
| `lesson_data` | `JSON` | No | — |
| `questions_data` | `JSON` | No | — |
| `usage_data` | `JSON` | Yes | — |
| `created_at` | `String(40)` | No | ORM client default `utc_now`; no server default |

Index: `ix_studio_generated_topic_created(topic_id, created_at)`. There is no FK from `topic_id` or lesson data to the static curriculum, which is not relationally stored.

### `studio_tutor_interactions`

| Column | SQLite/SQLAlchemy type | Nullable | Key/default |
| --- | --- | --- | --- |
| `interaction_id` | `String(36)` | No | Primary key |
| `session_id` | `String(36)` | No | FK to `studio_learning_sessions.session_id`, `ON DELETE RESTRICT` |
| `turn_id` | `String(80)` | No | — |
| `request_hash` | `String(64)` | No | — |
| `lesson_id` | `String(160)` | No | — |
| `role` | `String(16)` | No | — |
| `content` | `String(5000)` | No | — |
| `usage_data` | `JSON` | Yes | — |
| `created_at` | `String(40)` | No | ORM client default `utc_now`; no server default |

Unique constraint: `uq_studio_tutor_session_turn_role(session_id, turn_id, role)`. Index: `ix_studio_tutor_session_time(session_id, created_at)`.

The migration definitions match the current SQLAlchemy models for both tables: names, columns, type affinities/lengths, nullability, primary keys, FK target/action, unique constraints, and indexes. ORM `created_at` defaults are Python-side defaults, not database server defaults; the migration correctly has no SQL default. `utc_now()` produces ISO-8601 UTC text. No migration/model discrepancy was found for 0005.

## C. Disposable copy safety

Before copying, the configured file was confirmed at the path above, 16,379,904 bytes, mode `0600`. `/tmp` had ample free space. No SQLite `-wal` or `-shm` sidecar was present, and no backend writer process was running. The source connection used SQLite URI `mode=ro` plus `PRAGMA query_only=ON`; copies were made with SQLite's backup API into a private (`0700`) temporary directory, with copy files mode `0600`. The backup destination did not exist before creation.

The test never passed the configured database URL to Alembic. One copy was upgraded for preservation/ORM/service checks; another was used for downgrade/re-upgrade. Disposable copies were removed after validation.

## D. Upgrade, preservation, and database checks

The real-data disposable copy started at 0004 and upgraded successfully to `0005_azure_interactive_learning`. Both expected tables and the 0005 schema contract were present. The pre-upgrade and post-upgrade row snapshots matched exactly for all seven existing Student Studio tables: profiles, sessions, lesson progress, attempts, canonical evidence, behavioral-state versions, and recommendations. This confirms existing attempt/evidence/progress data remained intact in the tested copy without printing row contents.

On the upgraded copy:

- SQLite `quick_check`: `ok`.
- SQLite `foreign_key_check`: zero violations.
- Application SQLAlchemy connection: `PRAGMA foreign_keys=1`.
- ORM selects against `StudentGeneratedLesson` and `StudentTutorInteraction`: succeeded; the new tables were empty.
- Direct `LearningService` checks succeeded for progress retrieval and tutor-history retrieval; lookup of an unknown generated lesson produced the service's expected 404. No tutor generation or Azure call was invoked.

The added migration test uses synthetic records in isolated temporary SQLite files. It checks 0004→0005 model shape, row preservation, unique request ID, unique `(session_id, turn_id, role)`, rejection of a missing tutor-session FK, and an empty-table downgrade/re-upgrade. Test result: **3 passed**.

## E. Downgrade and reversibility

On a separate disposable copy of the configured database, the sequence 0004→0005→0004→0005 completed. At 0004 the two 0005 tables were absent; at re-upgraded 0005 they were present. Core Student Studio row snapshots remained equal throughout; integrity and FK checks passed.

The downgrade is structurally reversible only when the two 0005 tables are empty or their data is intentionally disposable. `downgrade()` drops `studio_tutor_interactions` and `studio_generated_lessons`; any generated lesson and tutor-turn records created after upgrade are permanently removed by that downgrade. The migration does not copy them elsewhere. Therefore rollback after production use requires a deliberate export/retention procedure or restore from a verified backup; routine downgrade is not data-safe.

## F. Application startup and HTTP verification

The earlier `TestClient` stall was reproduced with both this application and a bare, empty `FastAPI()` instance. The application lifespan completes normally when entered directly. A faulthandler dump located the stall in Starlette `TestClient.__enter__` while it calls `portal.start_task_soon(self.lifespan)`: the calling thread waits in AnyIO's `_spawn_task_from_thread`, while the AnyIO portal event-loop thread is idle in the selector. This places the blocking point in the TestClient/AnyIO cross-thread portal startup in this runner, before the application's lifespan begins. The installed versions were FastAPI 0.162.4, Starlette 1.10.0, AnyIO 4.16.0, and HTTPX 0.28.1. The precise underlying portal wakeup defect was not isolated.

An HTTPX ASGI-transport probe served OpenAPI, then stalled when the synchronous progress route required AnyIO worker-thread dispatch. This runner also denies local socket creation inside the ordinary sandbox (`PermissionError: [Errno 1] Operation not permitted`). The regression test therefore starts Uvicorn as a separate process with a temporary database and makes HTTP requests over loopback. That run completed successfully when executed with the narrow local-bind permission required by the sandbox.

The migrated temporary database was set in `MCP_RI_DATABASE_URL` and `MCP_RI_AUTO_MIGRATE=false` in the child environment **before** importing `mcp_ri.api.main:app`. The application started and shut down cleanly. `GET /api/v1/openapi.json` returned 200 and generated a schema containing the tested Student Studio routes.

HTTP results on the disposable 0005 database:

| Route | Result |
| --- | --- |
| `GET /api/v1/studio/progress` | 200; response envelope and `StudentProgressData` fields validated; generated-lesson course appeared in progress. |
| `GET /api/v1/studio/history` | 200; generated lesson session appeared in history. |
| `GET /api/v1/curriculum/lessons/{lesson_id}` | 200; ORM-loaded generated lesson matched the response contract. |
| `GET /api/v1/curriculum/lessons/{lesson_id}/practice` | 200; generated question returned without answer key or grading fields. |
| `GET /api/v1/studio/lessons/{lesson_id}/tutor/history?session_id=...` | 200; synthetic user/assistant turn records returned in order. |
| `GET /api/v1/curriculum/lessons/no-such-generated-lesson` | 404 with `LESSON_NOT_FOUND`. |
| Tutor-history request with a mismatched lesson/session | 409 with `SESSION_MISMATCH`. |

Application startup, route registration, OpenAPI generation, response structures, database reads, error handling, and graceful shutdown are now verified against an isolated 0005 database. The test fixtures are explicitly synthetic; no Azure endpoint was called.

## G. Commands and results

Focused command, run in a clean environment with only the local loopback permission needed for the separate Uvicorn process:

```bash
env -i PATH="$PWD/.venv-api/bin:/usr/bin:/bin" PYTHONPATH=src \
  "$PWD/.venv-api/bin/pytest" -q tests/api/test_migration_0005_compatibility.py
```

Result: **4 passed**. The test fixtures use only `tmp_path`; they build a synthetic database through revision 0004, upgrade that temporary file to 0005, and never use the configured application database URL.

The configured database was opened read-only after the tests. It remains at `0004_f10_1_learning_evidence`, `quick_check=ok`, size `16,379,904` bytes, modification time `2026-11-18 09:19:28.028012894 +0530`. Those size/time values match the prior recorded baseline. No test received its path or URL, and no migration, write transaction, or application record modification was made to it.

## H. Recommended production procedure and remaining risks

Before applying 0005 to a deployment: stop writers; confirm the target path/revision; make and verify a protected SQLite backup; rehearse this migration on a fresh backup copy with realistic existing rows; record pre/post counts and content checksums for protected tables; run `quick_check`, `foreign_key_check`, ORM smoke checks, and endpoint checks through a working HTTP test harness; then apply the migration explicitly during a maintenance window and verify schema contract/revision. Keep auto-migrate off. Retain the backup until rollback risk is accepted.

Remaining limitation: the configured database intentionally remains at 0004, so no claim is made that 0005-dependent HTTP routes work against that unupgraded file. The startup and HTTP checks apply to an isolated migrated copy. Keep the TestClient/AnyIO runner stall documented; the Uvicorn subprocess regression is the working HTTP verification in this environment. Also account for lossy 0005 downgrade if any generated lesson or tutor history has been written after migration.
