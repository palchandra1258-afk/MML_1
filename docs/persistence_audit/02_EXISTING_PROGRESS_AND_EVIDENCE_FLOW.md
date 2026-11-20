# 02 — Existing Student Studio progress and evidence flow

## Observed end-to-end path

1. **Learner identity:** `LearningService.PROFILE_ID` is the fixed `studio-local-demo`. `_profile_row()` lazily creates the local demo profile. It is not a login, authenticated identity, or multi-user boundary.
2. **Lesson retrieval:** `GET /api/v1/curriculum/lessons/{lesson_id}` resolves immutable-in-process authored curriculum content first, then the generated-lesson table. `GET .../{lesson_id}/practice` exposes public questions without grading keys. The current database is at 0004, before the generated-lesson table migration.
3. **Session and progress:** `POST /studio/lessons/{lesson_id}/sessions` reuses the most recently touched session for that fixed profile+lesson or creates one. It also creates lesson progress if absent. Progress is keyed only by profile and lesson, records current section/completed required section IDs, timestamps, content version and revision. No explicit ended state exists.
4. **Answer grading:** `POST /studio/questions/{question_id}/answer` validates a choice set or numeric value/tolerance server-side. The request's `submission_id` is an idempotency key scoped to profile. Reusing it with different question/response/session returns conflict. The server generates feedback; grading keys are not returned by practice retrieval.
5. **Attempt:** a UUID attempt row stores profile, session, curriculum IDs, submission ID, attempt number, monotonically allocated event sequence, submitted response, result, feedback, content version and timestamp. It is append-only in intended use; no update/delete API exists.
6. **Canonical evidence:** `StudentStudioInteractionAdapter` derives F10.1 evidence from the attempt event. `_persist_evidence_record` validates payload and verifies profile/source attempt/topic/lesson/question/correctness/content version/timestamp/sequence. The canonical evidence row has a unique `(profile_id, source_event_id)` and FK to the attempt. F9 legacy inline JSON remains nullable for backwards compatibility.
7. **Behavioral state and recommendation:** `_ensure_state_versions` appends learner behavioral snapshots through the attempt prefix; the attempt records the resulting version/status. `_recommend_for_attempt` creates a recommendation linked to that state version. These are descriptive/recommendation records, not mastery truth.
8. **Commit and history:** route handlers commit progress/session and answer changes. `GET /studio/history` composes lesson-start and answer events from sessions and attempts; there is no plan history. `GET /studio/progress`, `/studio/evidence`, and state/history routes expose aggregates or canonical records scoped to the fixed demo profile.

## Transaction and interruption behavior

For answer submission, attempt insert, evidence insert, state snapshot and recommendation are flushed in one SQLAlchemy transaction and committed at the route boundary. A raised application error prevents the route commit; session close rolls back pending work. This avoids a normally interrupted request leaving only an attempt without evidence/state. The `processing_status` column supports status representation, but the code path shown completes all these steps in one transaction; no separate durable outbox/recovery worker was found.

Progress updates and the session activity timestamp are written in one transaction. A browser that loses the response after commit can safely retry an answer with its same `submission_id`; the server returns saved feedback. A new key would be a new attempt. Progress writes are not keyed/idempotent and have no expected revision; retries increment revision and concurrent clients can race. Session creation retries may reuse the latest profile/lesson session.

The lock around answer submission is process-local, not distributed. SQLite writer serialization and uniqueness constraints provide additional protection, but multi-worker sequence allocation should use a transaction-safe allocator or handle integrity conflicts and retry.

## Resume boundary today

The lesson page calls `startSession`, receives persisted `current_section_id` and sets its selected section from it. On section navigation/completion the browser posts `current_section_id` and cumulative completed sections. The practice page re-fetches practice and starts/reuses a session, but the active question cursor and unsubmitted answer are client state and are not persisted. History reports lesson started and answer submitted, not every section visit or current activity. No route returns “my active lesson/plan to resume.”

The frontend creates a submission ID in a component ref; this survives in-memory request retries but not navigation/reload. Therefore the user should retain the same key during an uncertain request; after a full reload a newly generated key could duplicate a response if the previous request committed but its response was lost. A durable browser outbox or server idempotency recovery design is needed before robust offline/reload semantics.

## Data boundary

The existing plan foundation is a read-only `POST /studio/learning-plans/preview`; it queries saved behavioral/evidence context and returns a provider-independent rule-based preview. It neither accepts nor persists a plan. Phase 9–13 research artifacts and trajectory records are separate from the Studio demo profile. Evidence retrieval checks canonical provenance and returns no new records. No current flow ties an assessment/recommendation to an accepted learning-plan version.
