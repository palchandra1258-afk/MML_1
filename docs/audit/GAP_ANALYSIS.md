# MCP-RI gap analysis

## Critical

| Gap | Why it matters / dependency |
|---|---|
| No authentication or per-learner authorization; Studio has one fixed profile | Any shared deployment mixes student attempts and progress. Must be addressed before real student or multi-user use; it undercuts learner isolation, privacy and authorization claims. |
| Current learning-intelligence integration is uncommitted and its API contract/UI is incomplete | A checkout can contain the route/service code, but OpenAPI/frontend types and UI do not fully expose the processing/recommendation result. This makes the end-to-end loop difficult to inspect and version safely. |
| No valid Studio curriculum-to-research concept/skill mapping | Prevents meaningful Phase 11 estimate, Phase 12 grounded plan, or Phase 13 trajectory input. EdNet skill IDs/question content do not supply Studio topic ontology. |

## High

| Gap | Why it matters / dependency |
|---|---|
| No real cognition, misconception, or intervention-effect labels | Rules based on correctness cannot validate cognition or learning benefit. Requires construct definition, annotations/ground truth, study protocol and measurement before model/adaptive claims. |
| No executable representation content/provider | Phase 12 outputs no selected representation in saved evaluation; planning cannot alter actual instruction without reviewed content and delivery instrumentation. |
| Next recommendation not surfaced in Studio UI | Backend rule output and processing details are not consumable in the student journey; evidence-to-recommendation is opaque to users and reviewers. Depends on API contract and frontend integration. |
| Backend/API integration cannot be run in current environment | Missing Python dependencies prevents API tests, migration checks, and live workflow verification. Must establish supported reproducible environment before accepting current integration. |
| Frontend production build fails at Next `--showConfig` parsing | Typecheck passes, but deployment artifact is unverified. Establish cause and a passing build before release. |
| Fixed demo identity and process-local lock | One profile is suitable only for local demonstration; multiworker concurrency and correct identity-scoped event ordering require different controls. |

## Medium

| Gap | Why it matters / dependency |
|---|---|
| API contract synchronization | Generated OpenAPI and `shared/api-contracts/openapi.json` can drift from current routes and schema. Frontend currently omits Studio intelligence types/service methods. |
| Research and Studio learner views are separate | Student evidence/state cannot be inspected together in a clearly labeled source context. A separate view is needed while preserving EdNet vs Studio boundaries. |
| Empty prerequisite registry | Real diversion detection/resumption cannot be evaluated or used against actual dependencies; current zero-diversion result is not effectiveness evidence. |
| Evidence groups/alignment are not integrated into Studio evidence | Studio attempts produce individual normalized evidence; group provenance/conflict/cross-modal alignment workflow is not run for the Studio stream. |
| Long history paging is not fully represented in UI | History API supports limit/offset but frontend requests one 100-item page. Long-lived learner history may be truncated. |
| Runtime/responsive/browser verification absent | Source and unit tests do not establish route rendering, API CORS, mobile usability, or a complete runtime student journey. |

## Low

| Gap | Why it matters / dependency |
|---|---|
| Several research navigation views are explicitly planned placeholders | Navigation appears broader than implemented functions, but pages disclose their planned status. Prioritize only if those routes are in project scope. |
| Broad full test suite requires optional ML dependencies | Most standard-library tests pass, but installed requirements are not represented in current host environment; a pinned/tested environment reduces verification friction. |
| Frontend build diagnostic lacks actionable detail | The reported `Could not parse output` hides the TypeScript/Next compatibility/configuration cause even though direct `tsc` succeeds. |
