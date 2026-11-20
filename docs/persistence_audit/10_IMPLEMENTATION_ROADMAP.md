# 10 — Implementation roadmap

This is a dependency-ordered proposal, not an authorization to execute migrations or begin lifecycle implementation.

| Stage | Work | Depends on / release gate |
| --- | --- | --- |
| 0. Operational baseline | Resolve actual database at 0004 versus source migration 0005; choose whether/when to upgrade; backup/restore rehearsal; no automatic startup migration. | Migration owner approval; preserve generated/tutor data if any; 0005 downgrade is lossy. |
| 1. Product and ownership contracts | Confirm one active plan policy, cancellation/archival rules, version carry-forward rules, learner identity/auth boundary, content retention/version scheme, and preview expiry. | This audit review; privacy/security review. |
| 2. API/schema review | Freeze lifecycle transitions, request/response examples, idempotency, stale preview policy, concurrency revisions, and table constraints. | Stage 1 decisions; OpenAPI contract review. |
| 3. Migration 0006 core | Add plan identity, immutable versions, lifecycle event log. Copy-test on 0005 DB; zero legacy backfill. | Stage 0 and 2; verified backup. |
| 4. Migration 0007 progress/session | Add version-scoped plan progress, lesson progress, journey session state. Test unique/composite FKs and indexes. | 0006; retry/restore rehearsal. |
| 5. Migration 0008 activity context | Add nullable plan-version association to existing session/attempt architecture; test SQLite batch rebuild preserves rows, FKs, indexes, JSON. | 0007; owner-matching design and referential checks. |
| 6. Backend lifecycle services | Implement acceptance, transitions, versioning, resume, progress CAS, attempt association in one transaction; retain planless F9 flows. | 0006–0008; security tests; no unvalidated adaptation. |
| 7. API integration | Add owner-checked routes and strict schemas/OpenAPI; stable errors/idempotency. | Stage 6; API contract tests. |
| 8. Frontend integration | Add goal preview/acceptance/history/resume/revision UI and propagate plan context into existing lesson/practice screens. | Stage 7; accessibility and API error handling. |
| 9. Verification and rollout | Test 0004→0005→0008 copy upgrades, fresh DB, retries/crashes, concurrent tabs/workers, cross-owner access, backup restore, and version history. Roll out behind a feature flag; observe aggregates without logging student content. | All earlier stages; explicit release approval. |

Do not couple phases 9–13 research migrations or files to Studio plan tables. Do not connect current assessment classifications to automatic skipping/adaptation. Stop after each stage for review of migration and data-retention consequences.
