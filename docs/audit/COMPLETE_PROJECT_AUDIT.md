# MCP-RI complete project audit

**Audit date:** 2026-11-16  
**Scope:** Read-only audit of the checkout at `/home/mml_07/Desktop/MML`. Documentation was added under this directory; application code, schemas, data, and databases were not changed.

## Executive summary

MCP-RI is a substantial research prototype with a working EdNet preprocessing and next-answer prediction pipeline, evidence/state/representation/trajectory research modules, an artifact-backed FastAPI research API, and a separate curated Student Learning Studio. The Studio has live curriculum, lesson, practice, saved progress/history, server-side grading, evidence creation, versioned aggregate behavioral summaries, and a conservative activity recommendation path in the current source. It does **not** run Phase 11 cognition estimation, Phase 12 representation delivery, or Phase 13 trajectory orchestration on Studio events. Its fixed `studio-local-demo` identity is not authentication or multi-user isolation.

The student-facing loop is therefore operational in code through “next activity recommendation,” but not fully adaptive in the research sense. The recommendation is based on lesson section completion and latest answer correctness; it is rules-based and explicitly not mastery. The practice page currently shows correctness/explanation, but does not render the backend processing status or recommendation. Studio evidence, state, and recommendation API routes are not wired into the frontend service/UI. The interaction work is currently uncommitted in this checkout.

Research artifacts are unusually careful about boundaries: EdNet models predict recorded answer correctness, cognitive estimates are hypotheses without cognitive ground truth, representation plans have no available delivery capability, and Phase 13 evaluation is technical orchestration only. The locked test partition is reported unused. The evidence does not support claims of validated cognition, mastery, multimodal learning, or learning gains.

## Repository and architecture map

| Area | Actual responsibility and evidence |
|---|---|
| `src/mcp_ri/ednet_preprocessing.py`, `ednet_validation.py`, `models/` | EdNet validation, deterministic preprocessing/split and supervised baseline/sequence model support. Entry points are under `scripts/{preprocess,training}`. |
| `src/mcp_ri/learner_state/` | Descriptive, versioned behavioral summaries and uncertainty from interaction histories; not cognitive diagnosis. |
| `src/mcp_ri/evidence/` | Versioned evidence normalization, adapters, grouping, alignment, registry, and state bridge. Non-interaction modalities are interface-level/synthetic, not real EdNet media. |
| `src/mcp_ri/cognitive_state/` | Rule-based provisional concept estimates/hypotheses and evidence history; not a validated learned cognitive model. |
| `src/mcp_ri/representation/` | Auditable rules and plans with content grounding and availability registry. No content generation or delivery provider. |
| `src/mcp_ri/trajectory/` | Explicit state machine, dependency registry, diversion/resumption/context preservation, validation, and in-memory history core. Empty default dependency graph limits real diversions. |
| `src/mcp_ri/api/` | FastAPI app, API contracts, artifact index/lookups, trajectory persistence, and Studio API/service. `services.py` reads Phase 9–12 artifacts; `learning_service.py` owns curated Studio content and the separate demo profile. |
| `migrations/versions/` | Alembic schema revisions 0001 (research/API), 0002 (Studio attempts/progress/sessions), and 0003 (Studio state versions/recommendations). |
| `frontend/app/`, `components/`, `lib/` | Next.js 16 App Router UI, API clients/services, research screens, and Studio client. `/[section]` renders several planned placeholder views; `/studio/*` is the distinct student flow. |
| `schemas/`, `shared/api-contracts/` | JSON Schema module records and a checked-in OpenAPI/API contract. Current backend additions should be regenerated into this contract before treating it as synchronized. |
| `data/`, `models/`, `results/` | EdNet source/processed data, trained checkpoints, metrics and phase reports. Local data/results occupy about 6.7 GB/2.7 GB. No additional research run was performed. |
| `tests/` and `frontend/tests/` | Unit/schema/transition tests, API tests using synthetic fixtures and temporary SQLite, and frontend API/service logic tests. |

### Dependency and flow map

```text
EdNet archive → validation/preprocessing/split → baseline & sequence experiments
                                      └→ Phase 9 behavioral snapshots
                                           ↓
                                    Phase 10 evidence records/groups
                                           ↓
                                    Phase 11 provisional cognitive estimates
                                           ↓
                                    Phase 12 representation plans
                                           ↓
                                    Phase 13 trajectories (empty default dependency registry)
                                           ↓
Phase 14 API indexes saved Phase 9–12 JSONL read-only; persists authored Phase 13 trajectories

Studio curriculum.json → Next.js /studio → FastAPI curriculum/session/progress/practice
                                         → evaluated attempt + isolated Studio evidence
                                         → versioned aggregate Phase 9 state summary
                                         → completion/correctness rules → saved next activity
```

The research artifacts do not automatically process new Studio answers. The Studio code directly reuses the evidence normalizer/validator and learner-state accumulator/bridge, but has no supported topic-to-EdNet-skill mapping; it stops before Phase 11. Student records are stored in separate tables and tagged with `mcp-ri-student-studio`, not added to EdNet artifacts.

## Backend findings

The research API is primarily a read API over indexed JSONL snapshots. `/health` reports artifact/database readiness and model inference unavailable. It serves learner lists, behavioral and cognitive snapshots, evidence and group/alignment annotations, representation plans, and trajectory/diversion records. Trajectory creation/action paths are durable and validated; the research artifact records themselves remain read-only. Artifact indexing is an explicit setup command, not an automatic startup operation.

The Studio service serves a curated static curriculum from `src/mcp_ri/learning/curriculum.json`, checks question answers on the server, saves sessions/progress/attempts, records evidence provenance and content versions, and supports idempotent submissions. A process-local `RLock` serializes local answer submission; DB uniqueness constraints also protect submission IDs, question attempt numbers and event sequence. The entire submission/state/recommendation work is committed in one request transaction. The code derives complete missing state versions from the ordered attempt prefix and verifies evidence/version linkage. This is a single fixed profile, so these controls do not establish concurrent multi-user safety or identity isolation.

| Module | Status | Important limit |
|---|---|---|
| EdNet preprocessing and validation | Implemented; artifacts and unit coverage present | Large raw-data recreation is not rerun in this audit. |
| Prediction baselines and sequence models | Implemented; saved model/results present | Next-answer correctness only; locked test not used; environment lacks ML dependencies for full tests. |
| Evidence normalization/grouping | Implemented; validated interaction artifacts | Text/audio/visual adapters are not real-media ingestion or learned fusion. |
| Behavioral learner state | Implemented for EdNet snapshots; Studio aggregate adapter present in current source | Descriptive response history, no direct understanding measure. |
| Cognitive state | Rule-based research estimator and saved snapshots | No cognitive ground truth; not invoked for Studio topics. |
| Representation intelligence | Traceable plans and technical evaluation | All default delivery capabilities unavailable; 1,910 plans selected `none` in saved report. |
| Trajectory/diversion | Research core, API persistence for authored trajectories | No validated EdNet concept prerequisites; no automatic Studio trajectory; zero diversions in evaluated bounded sample. |
| Student Studio | Curriculum, server grading, persistence and basic recommendation code present | One unauthenticated local demo profile; current frontend does not show the new recommendation/processing payload. |
| Authentication/authorization | Not implemented | API has no identity/session authorization. Route learner IDs are resource selectors, not access control. |

## Frontend route and interaction audit

`/` is a dashboard; `/studio`, `/studio/explore`, `/studio/subjects/[subjectId]`, `/studio/topics/[topicId]`, `/studio/lessons/[lessonId]`, `/studio/practice/[lessonId]`, `/studio/progress`, and `/studio/history` are actual Studio pages. The Studio calls the real API client, shows loading/error/empty states, and provides lesson-section navigation and answer submission. Progress/history routes load saved API data. A database/API connection is required; API failures do not fall back to fixtures. Mock dashboard mode is explicit and separate.

The research workspace has routes for learning, progress, learner state, cognitive state, trajectory, representation, evidence, research, evaluation, and system status. Representation/evidence/research/evaluation/system status and learner record views use the research API or saved evaluation catalog. Several overview/workspace routes are explicitly planned shells or explanatory views; the legacy `/learning` page says lesson-content/quiz endpoints are unavailable in that research workspace. Do not confuse that route with the functional `/studio` practice journey.

The page set includes responsive CSS breakpoints, but no browser-based visual/responsive route check was possible. No frontend server was running. Route loading is therefore established by source structure and successful type/test checks, not live browser observation.

| View | Data source and real behavior |
|---|---|
| Dashboard | Live API overview when configured; explicit separate synthetic demo when mock mode is enabled. |
| Studio catalog/search/subject/topic | Live curated curriculum API; catalog content is authored static JSON, not generated from EdNet. |
| Studio lesson | Live lesson API plus start/resume session and saved section progress. Content is curated static text. |
| Studio practice | Public questions from API, backend grading on submit, answer explanation/expected answer. No model scoring. |
| Studio progress/history | Persisted local-demo profile API data; not authenticated user history. |
| Learner state/cognitive/trajectory/research/evaluation/evidence/representation/system | Artifact-backed research API or bundled evaluation snapshot; largely inspection views, not student learning delivery. |
| Other planned routes (catalog labels include assessment, etc.) | Planned shells/not implemented as functioning student workflows. |

## Research and scientific validity

The repo contains raw EdNet archives, processed compressed features (about 5.89 GB), 60 MB of model files and 2.7 GB of result artifacts. Reports document deterministic learner splits, feature leakage controls and validation-only comparisons. Project documentation gives Phase 6–8 real-data validation results, then Phase 9–13 bounded engineering outputs. These artifacts are not independently reproduced in this audit.

The saved Phase 12 evaluation validates 1,910 plans and traceability, but selected `none` for all 1,910 plans and marks zero delivery capabilities available. The saved Phase 13 report evaluates 100 trajectories, 100 valid transitions, 44/44 illegal transition rejections and 300/300 history reconstructions; it reports zero diversions and explicitly says no learning effectiveness evaluation. Phase 9/11/12 states are generated from EdNet interactions but are behavioral descriptions/rule hypotheses; EdNet has no validated cognitive labels. Text/audio/visual sample paths are synthetic fixtures. No real synchronized multimodal learning dataset or intervention outcome evidence is present.

Supported claims: recorded-response prediction on specified EdNet validation cohorts; technical schema, traceability, deterministic rule, and history checks in the bounded reports. Unsupported claims: cognition accuracy, confirmed misconceptions, learner mastery, representation preference/effectiveness, or learning gain. Engineering tests do not validate learning efficacy. The locked test partition was not used by this audit.

## Test/runtime audit

| Check | Outcome |
|---|---|
| `python3 -m compileall -q src/mcp_ri scripts migrations` | Passed. |
| `python3 -m unittest discover -s tests -v` | 133 tests discovered: 130 passed, 1 skipped, 2 import errors (`joblib`, `torch` unavailable). |
| Focused backend API pytest | Not run: system Python has no `pytest`, FastAPI, SQLAlchemy or Alembic installed. |
| Frontend `npm run lint` | Passed. |
| Frontend `npx tsc --noEmit` | Passed. |
| Frontend `npm run test:api` | Passed: 8 test files, 8 passed. |
| Frontend `npm run build` | Failed in Next.js with `Could not parse output from TypeScript's --showConfig`; direct `tsc --noEmit` passed. Build not verified. |
| Runtime/API/OpenAPI/CORS/browser workflow | Not run: no `uvicorn` or `next dev/start` process and no listeners on 3000/8000. Python API dependencies are unavailable. |
| Migration check | Not run: DB migration dependencies absent. Existing database/data was not opened or modified. |

The working tree had pre-existing uncommitted modifications in `src/mcp_ri/api/learning_routes.py`, `learning_service.py`, `tests/api/test_api.py`, `tests/api/test_learning_foundation.py`, plus untracked `tests/api/test_learning_intelligence.py`. This audit preserved them. The test output above reflects the checkout, including these changes.

## Security and readiness

The API has input schemas, bounded pagination, generic error responses with request IDs, logging, CORS allowlist configuration, SQLite foreign keys and constraints, and explicit separation between research learner IDs and Studio's demo profile. These are useful local prototype controls. There is no authentication, authorization, role separation, learner deletion/retention policy, or real account isolation. The singleton Studio identity means all local users share the same learner record. A client-provided learner ID in research routes is not proof of authorization. No production secrets service, TLS termination, deployment configuration, backup/restore, concurrency load test, or production database validation was established. Do not deploy this as a multi-user service.

## Overall status

The Student Learning Studio supports a **complete basic interactive lesson/practice loop in source**: choose curated topic → read lesson → save progress → answer → receive server-evaluated feedback → persist attempt/evidence/state → derive and persist a next activity. End-to-end runtime execution was not independently verified in this environment. The next activity is behavioral and completion-rule driven. The Studio is not connected end-to-end to Phase 11/12/13 adaptive intelligence, and the frontend does not display its new processing/recommendation response. The research workspace is a separate artifact inspection environment.

**Recommended next phase:** finish and verify the current Studio learning-evidence integration as an API/UI contract, while keeping claims bounded: synchronize OpenAPI and frontend types/service, surface processing status and next activity, add focused API-to-frontend verification and test in a supported Python environment, and document identity limitations. Do not begin cognitive or representation adaptation until topic/concept mappings and valid outcome evidence exist.

## Run and verify commands

From the repository root, the documented local API setup is:

```bash
python3 -m venv .venv-api
.venv-api/bin/python -m pip install -r requirements-api.txt
PYTHONPATH=src .venv-api/bin/python scripts/api/index_artifacts.py
PYTHONPATH=src .venv-api/bin/uvicorn mcp_ri.api.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Checks (install `requirements-training.txt`; sequence-model tests additionally require a compatible PyTorch install):

```bash
PYTHONPATH=src .venv-api/bin/python -m pytest tests/api -q
python3 -m unittest discover -s tests -v
cd frontend && npm run lint && npx tsc --noEmit && npm run test:api && npm run build
```

Live checks after startup: `curl -i http://127.0.0.1:8000/api/v1/health`, `curl -i http://127.0.0.1:8000/api/v1/openapi.json`, and browser routes `/`, `/studio`, `/studio/explore`, a topic, lesson, practice, progress, and history. The API index command and application will write to the configured local database; use a disposable database and copied artifact paths when validating outside the intended local setup. Do not retrain on or inspect the locked test split for this audit.

## Supervisor summary

MCP-RI has a real EdNet behavioral prediction pipeline and a technically rich, traceable research prototype, plus a separate functioning-by-code local Student Studio with curated instruction, saved attempts, response feedback, and simple next-activity rules. The learner-facing Studio does not currently call the cognitive-state, representation-planning, or trajectory modules; these remain separate research artifacts and APIs. The research claims are appropriately bounded: EdNet supports response prediction, while cognitive validity and educational effectiveness remain untested. The current checkout has uncommitted integration work; frontend checks mostly pass, while the production build and backend API suite could not be verified because the build tool errored and the Python environment lacks required dependencies. The immediate priority is contract/UI/runtime verification, followed by valid concept mapping and outcome-study design before adaptive claims.
