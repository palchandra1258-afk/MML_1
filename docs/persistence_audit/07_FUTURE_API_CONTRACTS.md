# 07 — Future API contracts (design only)

Use existing `/api/v1/studio` prefix, envelope `{success, data, request_id}`, Pydantic strict models, safe error format, and request-scoped SQLAlchemy session. These routes are **not implemented**. Every operation must authenticate/authorize learner ownership before reading or writing.

## Endpoints

| Method and route | Request | Response / behavior |
| --- | --- | --- |
| `POST /studio/learning-plans/preview` (existing) | `{learning_goal}` | Existing provider-independent preview. Add a short-lived `preview_token`/fingerprint, curriculum version, evidence-state version and expiry so acceptance can validate the reviewed preview. Current route has no token or persistence. |
| `POST /studio/learning-plans` | `{preview_token, idempotency_key}` | Create accepted plan + immutable v1 + initial progress atomically; return plan summary, version and transition. Revalidate token/freshness. |
| `GET /studio/learning-plans` | status/page filters | Only caller-owned plans; current version summary, status and updated time. |
| `GET /studio/learning-plans/{plan_id}` | optional `version` | Current or specified immutable snapshot plus matching progress; archived versions read-only. |
| `GET /studio/learning-plans/{plan_id}/versions` | page | Ordered version summaries/change reasons. |
| `POST /studio/learning-plans/{plan_id}/sessions` | `{version, idempotency_key}` | Start/resume explicit journey; return journey session, version and saved cursor. |
| `PUT /studio/learning-plans/{plan_id}/progress` | `{version, session_id, expected_revision, lesson_id, section_id, activity_id}` | Monotone checkpoint update; 409 on stale revision; return new revision and resume position. |
| `POST /studio/learning-plans/{plan_id}/lessons/{lesson_id}/complete` | `{version, session_id, expected_revision, idempotency_key}` | Validate required sections/activities; record completion and progress atomically. Does not imply mastery. |
| `POST /studio/learning-plans/{plan_id}/pause` / `resume` | `{expected_revision, idempotency_key}` | Guarded lifecycle transition and durable event. Resume may create a new session while retaining checkpoint. |
| `POST /studio/learning-plans/{plan_id}/revisions` | `{preview_token, expected_revision, change_reason, idempotency_key}` | Create immutable next version after explicit acceptance; preserve older version/progress. |
| `POST /studio/learning-plans/{plan_id}/complete` | `{version, expected_revision, idempotency_key}` | Complete only if required version steps meet explicit completion rules. |
| `POST /studio/learning-plans/{plan_id}/archive` | `{expected_revision, idempotency_key}` | Archive read-only; no cascade to attempts/evidence. |
| `POST /studio/questions/{question_id}/answer` (existing) | extend with plan/version or infer from verified session | Keep existing grading and idempotency behavior. New attempt links to the exact plan version; no duplicate attempt or evidence. Legacy planless requests remain valid. |

## Common response and errors

Plan responses include `plan_id`, `version_number`, `status`, `goal`, `current_position`, immutable step snapshot, `progress_revision`, timestamps, and provenance/limitations. Session responses include `journey_session_id`, current lesson/section/activity, saved completion, and expected revision. Use 404 for absent/not-owned identifiers to avoid enumeration; 409 for invalid state, reused key with altered body, stale revision, or stale preview; 422 for invalid step references; never expose raw SQL/credentials.

The request contract must not let the client supply learner ownership, mark arbitrary lessons complete, change frozen version content, or claim knowledge mastery. Preview acceptance should verify server-issued preview context rather than trusting a client-edited plan body.
