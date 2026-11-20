# 04 — Plan lifecycle and versioning

## State model

“Previewed” is an ephemeral preview response, not a saved plan status. Durable states begin when the student accepts.

| Current state | Allowed next state | Trigger/guard |
| --- | --- | --- |
| Preview (ephemeral) | Accepted | Student explicitly accepts a still-valid preview; server revalidates current curriculum/evidence context. |
| Accepted | Active, Cancelled, Archived | Start a journey; cancel before meaningful activity; explicit archive where policy allows. |
| Active | Paused, Completed, Cancelled, Archived | Student pause; all required plan work explicitly complete; explicit cancellation/archive. |
| Paused | Active, Cancelled, Archived | Student resumes/cancels/archives. |
| Completed | Archived | Explicit archive; completion is terminal otherwise. |
| Cancelled | Archived | Explicit archive; cancelled plan remains inspectable. |
| Archived | — | Read-only historical state; restore by creating a new accepted version or plan, not mutating archived history. |

Reject invalid transitions with conflict response and leave all rows unchanged. Record transition actor, timestamp, request ID, and reason in an append-only lifecycle event table or versioned audit log. A state column is a projection, not the complete history.

## Acceptance and revision

1. Preview uses existing rule-based planning and reports source/version/provenance. It remains provider-independent.
2. Acceptance validates the preview fingerprint/token, curriculum version, and any context version; validates ownership and current status; then transactionally creates plan identity, immutable version 1, initial progress, acceptance event, and initial journey pointer.
3. A material revision to the same journey creates version `n+1`, stores a human-readable reason and immutable snapshot, and sets the plan's current version pointer atomically. Prior version and progress remain readable. Default policy: a revised goal/sequence on the same journey is a new version. A clearly unrelated goal starts a separate plan.
4. Acceptance must not turn assessment categories into lesson skipping or difficulty adaptation. Existing recommendation/assessment guidance may be attached as provenance but cannot reorder the current plan without separately validated policy.

## Progress across versions

Each accepted version gets its own plan progress. Carry forward a completed lesson/objective only when the exact stable objective, lesson content version, and required activity definition are unchanged; record the carry-forward mapping and reason. If content changed or mapping is ambiguous, preserve old completion as historical and mark the new step not started. Keep incomplete activities in the old version; require explicit student confirmation to continue them under the new sequence. Answers already submitted remain attached to the version on which they were answered.

Archived versions are read-only and available by version ID. Do not delete/archive by cascading into attempts/evidence. Archive changes visibility/current selection, not historical records.
