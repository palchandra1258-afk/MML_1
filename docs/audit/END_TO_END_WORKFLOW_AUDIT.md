# Student Learning Studio end-to-end workflow audit

## Actual student journey

| Step | Actual implementation | Result / break |
|---|---|---|
| Enter Studio | `/studio` renders `StudentStudioClient(view="home")`; calls profile, catalog, progress APIs. | Loads real backend data when API is available. Fixed local demo identity is shown. |
| Select subject/topic | `/studio/explore`, `/studio/subjects/[subjectId]`, `/studio/topics/[topicId]`; curriculum from `src/mcp_ri/learning/curriculum.json` via `/curriculum*`. | Supported for authored catalog entries. Topic links lead to lesson. |
| View lesson | `/studio/lessons/[lessonId]`; `/curriculum/lessons/{id}` and `/studio/lessons/{id}/sessions`. | Curated static content; session and current progress are saved/resumed. |
| Save checkpoints | `POST /studio/lessons/{lessonId}/progress`; required section IDs validated and merged. | Persisted; section completion is a content activity measure, not mastery. |
| Start assessment/practice | `/studio/practice/[lessonId]`; `/curriculum/lessons/{id}/practice`; session started. | Authored questions and choices/numeric inputs; question set is static. |
| Submit answers | `POST /studio/questions/{questionId}/answer`; server validates and grades. | Choice/numeric grading is server-side; no model inference. Submission IDs are replay-safe and unique per demo profile. |
| Feedback | Backend returns correctness, expected answer, explanation, saved attempt/evidence IDs; UI displays correctness, explanation, answer and attempt number. | Meaningful authored response feedback. UI does not currently render backend `processing` or `recommendation` fields. |
| Persist event/evidence | Attempt row stores answer, content version, timestamp, evidence JSON/provenance, event sequence; separate Studio tables and source label. | Persisted in transaction; no cross-pollination into EdNet artifacts. All local visitors share the one demo profile. |
| Update behavioral state | `_ensure_state_versions()` validates ordered event prefix and appends Phase 9 accumulator snapshots. | Current source implements aggregate response state; not a concept/topic state because `skill_ids` are empty. |
| Cognitive estimate | `intelligence_status()` returns `not_available`. | Breaks before Phase 11; no validated topic-to-skill/concept mapping or Studio estimate invocation. |
| Representation plan/activity | `intelligence_status()` returns `not_available`; Phase 12 defaults have no available providers. | No selected or delivered representation. |
| Trajectory/diversion | `intelligence_status()` returns `not_available`. | No Studio objective/dependency graph; research trajectories are a separate authored API. |
| Next activity | Current backend `_recommend_for_attempt()` persists a rule-based recommendation per state version: review after wrong answer; continue incomplete lesson after correct answer; additional practice when sections complete and an unattempted question remains. | Basic next step exists in backend, with evidence IDs and limitations. It is activity/completion logic, not adaptive intelligence or mastery. No frontend method/view currently displays it. |
| Resume/history | `start_session`, `/studio/progress`, `/studio/history`; the frontend has progress/history pages. | Saved history and resume path exist for the singleton profile. |

## Current data flow

```text
Browser Studio
  GET curriculum + lesson/practice + profile/progress
  POST start session / section checkpoint
  POST answer {submission_id, session_id, response}
        ↓
FastAPI learning_routes → LearningService
        ↓ one SQLAlchemy request transaction (local submission lock)
server-side grading → append-only Studio attempt
        ↓
Phase 10 normalized interaction evidence JSON stored on the attempt
        ↓
Phase 9 LearnerStateAccumulator replay over ordered Studio events
        ↓
versioned aggregate behavioral snapshot stored separately
        ↓
simple completion/last-answer rules → recommendation row
        ↓
feedback response returned to practice UI (only grading feedback rendered)
```

No Studio event is sent to `ArtifactService` or appended to the historical EdNet evidence/state files. No Phase 11 cognitive estimator, Phase 12 plan builder, or Phase 13 trajectory manager is invoked by answer submission. New recommendation API (`/studio/recommendation`), state/evidence/status routes exist in the current uncommitted backend route file, but no corresponding frontend methods/views were found. `shared/api-contracts/openapi.json` and frontend `AnswerFeedback` types should be synchronized with the current server schemas.

## Reliability and identity observations

- Submission idempotency is enforced by lookup plus a DB uniqueness constraint; a replay with changed answer/question/session returns conflict.
- Per-question attempts and overall event sequence are allocated from row counts/max values while the local route lock is held. The lock is process-local, so it does not serialize multiple worker processes; uniqueness constraints are the last line of defense, and sequence conflicts are not automatically retried.
- State versions are append-only and tied to source event sequence/evidence ID. Existing history consistency is checked during replay. State reconstruction, recommendation persistence and attempt persistence share the transaction.
- The single `studio-local-demo` profile is not a learner identity boundary. Session ownership checks only establish association to that shared profile.
- History endpoint pagination is bounded; frontend requests up to 100 items, so longer histories need paging behavior if displayed as complete.
- API request errors are normalized, but API runtime was unavailable in this environment; error behavior was not exercised live.

## Workflow conclusion

The basic content-to-response feedback workflow is implemented in source and has frontend service-test coverage. The current branch additionally connects answers to isolated evidence, aggregate behavioral-state versioning, and a saved simple next-activity rule. The workflow succeeds through that rule in code, but the recommendation/status is not presented in the student interface, and independent runtime/API verification was blocked by missing Python dependencies and no running services. It breaks as a research-adaptive workflow at cognitive-state estimation: representation delivery and trajectory orchestration are not connected. It should be described as a persisted local-demo learning loop with rule-based next steps, not a complete adaptive-intelligence loop.
