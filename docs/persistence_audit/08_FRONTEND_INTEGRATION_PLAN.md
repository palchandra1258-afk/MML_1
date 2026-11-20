# 08 — Frontend integration plan

## Existing screens and boundary

`frontend/app/studio` is the active Student Studio: home, explore/subject/topic, lesson, practice, progress and history. `StudentStudioClient` calls `learning.service.ts`, starts/reuses a lesson session, saves section progress, submits answers, and loads aggregate progress/history. The active-section cursor is restored from the backend; practice question index and unsent answer are client-only. There is no learner-plan preview integration in this frontend service today.

`frontend/components/learner/learning-workspace-page.tsx` is a separate research-data workspace: it reads Phase 12 representation plans and persisted trajectories and explicitly does not deliver lessons or activities. Do not repurpose research learner IDs or this screen as a Student Studio account/journey.

## Incremental component/route plan (future)

1. **Plan preview:** add typed plan-preview request/response and API method to `frontend/lib/services/learning.service.ts`; a `/studio/plan` (or focused section of home) screen accepts a goal and displays ordered modules/topics/lessons, missing information, provenance, rule-based/provider status, and limitations. No save until student acceptance.
2. **Acceptance/history:** acceptance action with pending/error/idempotent states; after API confirms, route to `/studio/plans/{planId}`. Plan list/history shows active, paused, completed, cancelled, archived plans and version history without mixing research trajectory cards.
3. **Active journey:** plan overview displays version, progress and ordered steps; each step links to the existing `/studio/lessons/[lessonId]` and `/studio/practice/[lessonId]` routes with opaque plan/version context validated by backend.
4. **Resume:** home adds “Resume learning” using backend resume endpoint. The server-returned checkpoint selects lesson, section and activity; browser state is only a cache. Show stale-content and version conflict recovery states.
5. **Lesson progress:** keep current section content and checkpoints, add journey context to API calls, optimistic revision handling, save/error indicator and retry. Do not redesign the lesson layout.
6. **Completion/revision:** plan page distinguishes content completion from knowledge evidence; revision preview compares old/new steps and asks confirmation for incomplete activity handling. Version history is read-only.

## UI and compatibility constraints

Preserve current non-plan `/studio` exploration and attempt APIs. Plan-bound route errors must not break generic Student Studio activities. Existing `/progress` remains descriptive and gains plan progress only through a separate typed section. Provide accessible focus/status announcements and explicit offline/network retry state. Avoid writing learner goal, session tokens, or sensitive answer data into analytics/local storage.
