# 06 — Migration and data safety design

**No migration was created or executed. The configured SQLite database remains at `0004_f10_1_learning_evidence`.** The 0005 revision exists in source but is unapplied to that database.

## Proposed ordered revisions

First resolve and review the existing 0004→0005 environment mismatch independently. Do not combine Azure lesson/tutor schema rollout with plan lifecycle rollout.

1. **Existing `0005_azure_interactive_learning` (existing source migration):** apply only after backup/restore rehearsal, and after confirming the intended database. It creates generated-lesson and tutor tables and updates contract metadata; it does not transform current Studio rows. Its downgrade drops tables and is lossy after either table contains records.
2. **`0006_learning_plan_core` (proposed):** create `learning_plans`, immutable `learning_plan_versions`, and append-only lifecycle-event records with owner/version uniqueness and indexes. No backfill; existing learning history is not a plan.
3. **`0007_learning_plan_progress` (proposed):** create per-version plan progress, plan-scoped lesson progress, and resumable journey-session table with composite foreign keys/indexes. No attempt/evidence copies.
4. **`0008_learning_plan_activity_context` (proposed):** add nullable plan/version references to existing Studio session and attempt rows (or the reviewed equivalent link table), plus consistency checks/indexes. SQLite changes must use Alembic batch table recreation. Existing rows get NULL plan context and keep their IDs/payloads.

Keep migrations linear from 0005 and update the application schema contract only within each successful migration transaction. Review `Base.metadata` parity with migrations and test fresh DB plus copies of both 0004 and 0005 DBs.

## SQLite safety and rollback

- Before each rollout, quiesce writers, use SQLite backup API or `VACUUM INTO` to a separate backup file, verify backup opens, record Alembic revision and integrity-check result, and rehearse upgrade on a copy.
- Apply one migration at a time with the intended database URL explicitly confirmed; `MCP_RI_AUTO_MIGRATE` should remain off for normal startup. Verify `alembic_version`, metadata contract, table/constraint/index presence, `quick_check`, `foreign_key_check`, and before/after counts of existing tables.
- For additive 0006/0007, downgrade is technically possible before lifecycle rows are created. Once plans/progress/session data exist, downgrade would delete user history and is not an acceptable rollback. Roll forward with a corrective migration or restore the verified backup during a maintenance window.
- For 0008, downgrade can remove nullable columns/link data and must not run if any plan-context references exist. SQLite batch rebuild must preserve the 18 attempt columns, existing row keys, JSON payloads, constraints, and indexes. Validate row counts and checksums on a copy.
- Never downgrade 0005 after generated lesson/tutor records exist without a separate export/retention plan; its current downgrade drops those records.
- Keep research artifact files and their indexes untouched. No migration should rewrite EdNet or source research artifacts.

## Release gate

Require backup/restore evidence, migration review, copy-based upgrade and rollback rehearsal, constraint/index inspection, existing-table count/key/payload verification, and application compatibility tests before applying any migration to the configured database. The current audit did none of these writes or rehearsals against the live file.
