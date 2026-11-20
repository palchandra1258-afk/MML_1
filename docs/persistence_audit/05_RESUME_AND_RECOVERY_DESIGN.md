# 05 — Resume and recovery design

## State of record

Persist state needed to resume in the same request transaction as the activity that changes it:

- accepted plan/version and lifecycle status;
- current lesson, section and activity/question pointer;
- completed required lesson sections and version-scoped lesson status;
- current journey session and last activity timestamp;
- submitted attempts, their idempotency key, plan/version context, and canonical evidence references;
- progress revision used for conflict detection.

The current lesson cursor and completed sections already persist in `studio_lesson_progress`; answer attempts and evidence persist separately. The practice question cursor, active question, in-progress unsent answer, active plan/version, and cross-plan resume target do not persist. Browser state should be a cache only, never the sole record of progress.

## Resume read algorithm

For an authenticated profile (authentication is not implemented today):

1. Select the learner's most recently active plan, unless they explicitly choose a different one; verify ownership and non-archived status.
2. Load current accepted version and its version-scoped progress.
3. Resolve the current step to an immutable lesson/content version and validate it belongs to that version's snapshot.
4. Return current lesson/section/activity, incomplete activity, completed lesson states, outstanding objectives/activities, last committed progress revision, and last activity time.
5. If saved content is no longer retrievable or version/hash mismatches, return a recoverable conflict and preserve data; never jump silently to a newer lesson.

## Write and retry behavior

- Autosave section/activity position synchronously before navigation and on explicit section changes. Debounced telemetry can supplement but must not replace the checkpoint write.
- Use client-generated idempotency key for answer submission and journey transitions; persist it with the operation. A repeated key plus same payload returns the original result; same key plus different payload returns 409.
- Use optimistic revision (`If-Match`/expected revision) for progress updates to prevent stale tabs overwriting each other. Return latest revision on conflict so UI can reload/merge only safe monotone completion sets.
- Store active-question position, not unsent answer text by default. If resuming a submitted question, derive completion/feedback by attempt linked to the plan version. If a submission outcome is uncertain, query by idempotency key before creating a new attempt.
- On request interruption before commit, all coupled rows roll back. After commit but before response, idempotent retry returns the committed result. Add fault-injection tests for both boundaries.
- Session timeout/close should be explicit (`ended_at`, status) and not erase the checkpoint. A paused session resumes through a new or reactivated journey session according to an explicit policy.

## Reconstructable vs synchronously saved

Can be reconstructed from canonical attempts/evidence: graded response outcome, answer feedback, evidence IDs/provenance, attempt counts, and behavioral snapshots. Must be saved as plan-specific state because it is not inferable reliably: accepted version, selected plan, sequence cursor, current section/activity, manual completion/skip decisions, plan pause/completion/cancellation, and revision history. Never reconstruct plan completion from response correctness alone.
