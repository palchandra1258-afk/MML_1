# 01 — Database architecture audit

**Scope:** source migrations, SQLAlchemy models/services/routes, and configured SQLite database, inspected without writes on 20 November 2026. No learner identifiers or row contents are included.

## Connection and initialization

- `APISettings.from_environment()` selects `MCP_RI_DATABASE_URL`; absent that, it resolves to `data/application/mcp_ri.sqlite3` under the repository root.
- `Database` creates a SQLAlchemy engine with `pool_pre_ping=True`; SQLite connections use `check_same_thread=False`. Creating a new file uses exclusive creation and mode `0600`; the parent directory is created if needed.
- A SQLAlchemy `connect` listener runs `PRAGMA foreign_keys=ON` for each SQLite application connection. Session creation is request-scoped. `get_session` closes the session but does not itself commit.
- App startup does not migrate by default. `MCP_RI_AUTO_MIGRATE=true` or an explicit factory option runs Alembic to `head`; `create_schema_on_start=True` uses `Base.metadata.create_all` instead. These are different schema-management paths; production should use reviewed Alembic migrations.
- `create_schema()` creates model tables and writes `app_metadata.schema_contract`; this is a write. It was not run for this audit.

## Transactions, constraints, and concurrency

- Endpoint handlers explicitly call `session.commit()` for writes. Uncommitted changes are rolled back when the request session is closed after an exception, subject to SQLAlchemy's normal transaction semantics.
- A quiz answer is built and flushed with its canonical evidence record, behavioral-state snapshot, and recommendation in the same request transaction; the route commits after the service succeeds. A processing error raises a safe 503 and the transaction is not committed. The frontend retries with the same `submission_id`.
- Lesson progress and its session activity timestamp are updated together and committed by the route. Session creation and initial lesson progress are also committed together by the route.
- A module-level `RLock` serializes answer sequence allocation through commit inside one Python process. SQLite still permits only one writer at a time; this lock does not coordinate multiple worker processes. Unique constraints and idempotency are the cross-process safety net, but a conflicting concurrent request can still need a retry.
- Database uniqueness includes per-profile submission ID, per-profile/question attempt number, per-profile event sequence, one canonical evidence row per source attempt, one behavioral snapshot per source sequence, and one recommendation per state version. The trajectory event order is unique per trajectory. Primary keys protect all entity IDs.
- The current lesson-progress `revision` increments but is not used as an optimistic concurrency precondition. Concurrent section updates can race at application level; a future lifecycle API should add compare-and-swap/ETag semantics.

## SQLite and migration observations

The database was opened with SQLite URI `mode=ro` and `PRAGMA query_only=ON`. Read-only checks returned `quick_check=ok` and zero rows from `foreign_key_check`. `journal_mode` is `delete`; `user_version` is `0` (Alembic, not `user_version`, tracks schema). A standalone SQLite connection reported `foreign_keys=0`, which is a per-connection setting; the application SQLAlchemy listener enables it on its own connections.

The actual file reports Alembic revision `0004_f10_1_learning_evidence` and metadata contract `migrations/0004_f10_1_learning_evidence`. It has not applied `0005_azure_interactive_learning`. The Python model currently declares generated-lesson and tutor-interaction tables as part of schema contract 0005. App startup with migration disabled does not reconcile this mismatch; endpoints that query those tables may fail against this database until a separately reviewed upgrade is applied.

History is linear: `0001_initial` → `0002_learning_studio` → `0003_f10_learning_intelligence` → `0004_f10_1_learning_evidence` → `0005_azure_interactive_learning`. Revision 0004 copies valid legacy inline evidence into canonical rows and keeps the original inline copy. Revision 0005 adds generated lesson and tutor interaction tables. Downgrading 0005 drops those tables and therefore loses generated lesson/tutor data created after the upgrade; it is not a safe rollback after use.

## Table inventory and current row counts

Counts are aggregate only, obtained read-only from the configured database. “Research/index” identifies imported artifact indexing or trajectories; “Studio” identifies Student Studio application data.

| Table | Purpose, key, principal references and constraints | Rows | Category |
| --- | --- | ---: | --- |
| `app_metadata` | Schema contract key/value; PK `key`. | 1 | Application metadata |
| `artifact_files` | Indexed source artifact manifest; PK `artifact_name`. | 5 | Research/index |
| `artifact_records` | Byte offsets and metadata for indexed source records; composite PK `(artifact_name, record_id)`; FK to artifact file; learner/artifact index. | 121,879 | Research/index |
| `artifact_record_links` | Links between indexed records; composite PK `(artifact_name, record_id, linked_record_id)`; FK to source record; target index. | 1,000 | Research/index |
| `learner_references` | Research learner identity namespace; PK `learner_id`. | 0 | Research |
| `trajectories` | Current durable trajectory snapshot/status per research learner; PK `trajectory_id`; FK learner; learner index. | 0 | Research/application trajectory |
| `trajectory_versions` | Immutable trajectory snapshots; composite PK `(trajectory_id, version)`; FK trajectory. | 0 | Research/application trajectory |
| `trajectory_history_events` | Ordered trajectory event history; PK `event_id`; FK trajectory and prior event; unique trajectory/order; version index. | 0 | Research/application trajectory |
| `diversions` | Child paths linked to research learner and parent trajectory; PK `diversion_id`; indexes on both references. | 0 | Research/application trajectory |
| `diversion_versions` | Immutable diversion snapshots; composite PK `(diversion_id, version)`; FK diversion. | 0 | Research/application trajectory |
| `trajectory_context_snapshots` | Context snapshot pinned to a parent trajectory version; PK `context_snapshot_id`; composite FK to trajectory version. | 0 | Research/application trajectory |
| `studio_profiles` | Local Studio demo profile, not authenticated account; PK `profile_id`. | 1 | Student Studio |
| `studio_learning_sessions` | Reused profile/lesson study session; PK `session_id`; FK profile; profile/activity index. No ended/status/current-activity columns. | 1 | Student Studio |
| `studio_lesson_progress` | Profile+lesson section cursor/checklist and timestamps; composite PK `(profile_id, lesson_id)`; FK profile; profile/course index; revision integer. | 1 | Student Studio |
| `studio_learning_attempts` | Append-only raw answers, grading result, feedback, content version, event sequence and optional inline legacy evidence; PK `attempt_id`; FKs profile/session; three uniqueness constraints; profile/time and profile/lesson indexes. | 2 | Student Studio |
| `studio_evidence_records` | Canonical F10.1 evidence derived from an attempt; PK `evidence_id`; FKs profile and source attempt; unique profile/source; profile/time/topic/lesson indexes. | 2 | Student Studio evidence |
| `studio_behavioral_state_versions` | Immutable F10.2 snapshot over evidence prefix; composite PK `(profile_id, state_version)`; FK profile; unique profile/source sequence. | 2 | Student Studio state |
| `studio_learning_recommendations` | Immutable recommended next activity with supporting evidence and limitations; PK `recommendation_id`; FKs profile and composite state version; unique profile/state; profile/created index. | 2 | Student Studio state |
| `studio_generated_lessons` | Generated lesson/question snapshot and request/usage metadata; PK lesson ID; unique request ID; topic/created index. | Not present at 0004 | Student Studio; introduced by 0005 |
| `studio_tutor_interactions` | User and assistant turns keyed to lesson session; PK interaction ID; FK session; unique session/turn/role; session/time index. | Not present at 0004 | Student Studio; introduced by 0005 |

JSON payload fields preserve evidence, state and trajectory snapshots; relational constraints do not validate their internal shape. Research artifacts remain in indexed artifact tables/files, separate from the Studio profile tables. No learning-plan table exists.

## Backup and recovery assumptions

No automated backup/restore mechanism or retention policy was found in this persistence layer. Before a future schema upgrade: stop writers, make and verify a consistent SQLite backup using SQLite's backup API or `VACUUM INTO` to a separate path, record file hash/revision, test upgrade against a copy, run integrity and FK checks, and preserve a tested restore procedure. Do not treat Alembic downgrade as backup: some downgrades drop post-upgrade records.
