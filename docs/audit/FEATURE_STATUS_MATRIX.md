# MCP-RI feature status matrix

Status is based on inspected source and saved artifact evidence; “verified” means supported by the checks listed here, not necessarily production behavior.

| Feature | Status | Evidence and limitation |
|---|---|---|
| EdNet validation/preprocessing | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/ednet_preprocessing.py`, `ednet_validation.py`, `scripts/preprocess_ednet.py`; unit tests pass, full data pipeline not rerun. |
| EdNet baseline prediction | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `scripts/training/`, `src/mcp_ri/models/`, saved `models/trained/`, `results/reports/`; documented validation metrics, no locked-test result. |
| Sequence model comparison | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `scripts/training/train_ednet_sequence_models.py`, `results/reports/phase8-*`; report states validation cohort and limits; `torch` unavailable for rerun. |
| Phase 9 behavioral learner state | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/learner_state/`, `results/reports/phase9-*`; descriptive response summaries, no cognition target. |
| Phase 10 interaction evidence normalization | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/evidence/`, `results/reports/phase10-*`; EdNet interaction coverage; modality adapters beyond interaction rely on synthetic fixtures. |
| Text/audio/visual multimodal learner evidence | MOCK_OR_SYNTHETIC | `src/mcp_ri/evidence/adapters/{text,audio,visual}.py`, `docs/MODALITY_AVAILABILITY_REPORT.md`; no real synced learner media, ASR/OCR/fusion. |
| Evidence grouping/alignment | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/evidence/{grouping,aligner}.py`; provenance and uncertain links retained; integration suite not run here. |
| Phase 11 cognitive-state estimation | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/cognitive_state/`, phase 11 evaluation; deterministic rules/hypotheses, no cognitive ground truth. |
| Phase 12 representation planning | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/representation/`, saved 1,910-plan evaluation; plans traceable, but 1,910/1,910 select `none`, no delivery providers. |
| Phase 13 trajectory orchestration | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/trajectory/`, phase 13 report; valid transition/history checks, zero diversions in bounded run due to empty dependency graph. |
| Phase 14 artifact-backed research API | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/api/{main,routers,services,artifact_index}.py`, `docs/PHASE14_EVALUATION.md`; prior documented 21 synthetic API tests passed, current environment cannot rerun. |
| Durable authored trajectory storage | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/api/persistence.py`, `migrations/versions/0001_initial.py`; documented temporary SQLite transaction/recovery tests; not reverified here. |
| Studio curated topic catalog and lessons | COMPLETE_AND_VERIFIED | `src/mcp_ri/learning/curriculum.json`, `learning_service.py`, `frontend/components/studio/student-studio-client.tsx`; frontend service tests pass. Content is authored static. |
| Studio server grading and answer feedback | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | Choice/numeric grading and exact saved content versions are verified by the 51-test backend API suite; no live-browser run. |
| Studio saved attempts, evidence, progress, history | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/api/persistence.py`, `learning_service.py`, migrations 0002/0004/0005; API persistence, replay, and evidence tests pass; fixed unauthenticated profile. |
| F10.2 Studio evidence → behavioral-state versions | COMPLETE_AND_VERIFIED | `docs/F10_2_STUDENT_STUDIO_BEHAVIORAL_STATE.md`; full API suite verifies append-only snapshots, evidence links, replay, topic summaries and EdNet separation; frontend exposes the response summaries. |
| Studio recommendation generation and display | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | Backend stores evidence-linked completion/correctness rules; response and dashboard UI display rationale/limits; no cognition, representation, or trajectory input. |
| Dynamic Azure lesson generation and persistence | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `azure_openai.py`, `learning_service.py`, migration 0005, generation API tests. Mocked valid output verifies schema/persistence/retry; live Azure credentials/output quality are unverified. |
| Lesson-context Azure tutor and persisted history | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | Tutor endpoint, turn idempotency, history route/UI and API tests pass with injected responses; live provider behavior is unverified. |
| Inline checkpoints and generated assessment | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | Lesson/practice questions use server grading and canonical evidence; frontend logic and service/API tests pass; no browser workflow run. |
| Studio → Phase 11 cognitive estimate | NOT_IMPLEMENTED | `intelligence_status()` in current service says unavailable due to no validated topic/skill mapping. |
| Studio → Phase 12 plan/delivered representation | NOT_IMPLEMENTED | No Studio concept map/provider; default delivery capabilities false. |
| Studio → Phase 13 trajectory/diversion | NOT_IMPLEMENTED | Service explicitly reports unavailable; no authored Studio goal/dependency graph. |
| Research evidence/cognitive/representation views | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `frontend/components/{evidence,learner,representation}` plus API clients; artifact inspection UI, not learner delivery. |
| Research dashboard/evaluation | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | Evaluation snapshot `frontend/lib/research/evaluation-snapshot.json`; bundled report view; not live model inference. |
| Student-facing live recommendation/status | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | Frontend renders backend processing details and rule-based recommendations in answer feedback and Studio home; no browser workflow run. |
| Legacy `/learning` adaptive workspace | DOCUMENTED_BUT_NOT_IMPLEMENTED | `frontend/components/learner/learning-workspace-page.tsx` says lesson/quiz/content endpoint unavailable; distinct from `/studio`. |
| Planned dashboard subsections | PARTIALLY_IMPLEMENTED | `frontend/app/[section]/page.tsx` renders explicit planned shells for several route labels. |
| Authentication/authorization | NOT_IMPLEMENTED | No auth middleware or identity provider; fixed local demo profile. |
| Multi-user learner isolation | NOT_IMPLEMENTED | Studio uses singleton `PROFILE_ID`; research route IDs are not authorization. |
| Responsive UI | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | Responsive CSS breakpoints exist; no live browser/device audit. |
| Python source compilation | COMPLETE_AND_VERIFIED | `python3 -m compileall -q src/mcp_ri scripts migrations` passed. |
| Backend API suite | COMPLETE_AND_VERIFIED | `PYTHONPATH=src .venv-api/bin/python -m pytest tests/api -q`: 51 passed, including generated content, Azure failure handling, migration and replay coverage, using disposable SQLite. |
| Backend full unit suite | BLOCKED | 133 discovered, 130 passed, 1 skipped, 2 import errors because `joblib` and `numpy` are unavailable; no training dependencies were installed. |
| Frontend lint/type/service tests | COMPLETE_AND_VERIFIED | `npm run lint`, `npx tsc --noEmit`, `npm run test:api` passed (8 test files). |
| Frontend production build | BLOCKED | Next 16.4.6 failed parsing TypeScript `--showConfig`; direct TypeScript check passes. |

Azure integration, migration 0005, the generated OpenAPI contract and focused tests are current in this worktree. Live Azure, browser verification, production build, authentication, and downstream Phase 11/12/13 Studio integration remain unverified or unavailable as described above and in `docs/F11_AZURE_INTERACTIVE_LEARNING_PLATFORM.md`.
