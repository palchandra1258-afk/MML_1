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
| Studio server grading and answer feedback | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `LearningService._evaluate/submit_answer`, `learning_routes.py`, frontend learning service; code checks choice/numeric answers; browser/API end-to-end not run. |
| Studio saved attempts, evidence, progress, history | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `src/mcp_ri/api/persistence.py`, `learning_service.py`, migration 0002; fixed unauthenticated profile; API pytest unavailable. |
| Studio evidence → behavioral state versions | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | Current uncommitted `learning_service.py`, migration 0003; prefix validation/versioning code exists; not exposed in UI; API tests unavailable. |
| Studio recommendation generation | PARTIALLY_IMPLEMENTED | Current uncommitted `learning_service.py` saves completion/correctness-driven rule recommendations; no cognition/representation/trajectory input; API contract and frontend do not surface it. |
| Studio → Phase 11 cognitive estimate | NOT_IMPLEMENTED | `intelligence_status()` in current service says unavailable due to no validated topic/skill mapping. |
| Studio → Phase 12 plan/delivered representation | NOT_IMPLEMENTED | No Studio concept map/provider; default delivery capabilities false. |
| Studio → Phase 13 trajectory/diversion | NOT_IMPLEMENTED | Service explicitly reports unavailable; no authored Studio goal/dependency graph. |
| Research evidence/cognitive/representation views | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | `frontend/components/{evidence,learner,representation}` plus API clients; artifact inspection UI, not learner delivery. |
| Research dashboard/evaluation | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | Evaluation snapshot `frontend/lib/research/evaluation-snapshot.json`; bundled report view; not live model inference. |
| Student-facing live recommendation/status | DOCUMENTED_BUT_NOT_IMPLEMENTED | Backend response code exists, but no frontend `learning.service.ts` method for the new recommendation/state routes and no rendered processing/recommendation panel. |
| Legacy `/learning` adaptive workspace | DOCUMENTED_BUT_NOT_IMPLEMENTED | `frontend/components/learner/learning-workspace-page.tsx` says lesson/quiz/content endpoint unavailable; distinct from `/studio`. |
| Planned dashboard subsections | PARTIALLY_IMPLEMENTED | `frontend/app/[section]/page.tsx` renders explicit planned shells for several route labels. |
| Authentication/authorization | NOT_IMPLEMENTED | No auth middleware or identity provider; fixed local demo profile. |
| Multi-user learner isolation | NOT_IMPLEMENTED | Studio uses singleton `PROFILE_ID`; research route IDs are not authorization. |
| Responsive UI | IMPLEMENTED_BUT_NOT_FULLY_VERIFIED | Responsive CSS breakpoints exist; no live browser/device audit. |
| Python source compilation | COMPLETE_AND_VERIFIED | `python3 -m compileall -q src/mcp_ri scripts migrations` passed. |
| Backend full unit suite | BLOCKED | 133 discovered, 130 passed, 1 skipped, 2 import errors from unavailable `joblib` and `torch`; pytest/API dependencies absent. |
| Frontend lint/type/service tests | COMPLETE_AND_VERIFIED | `npm run lint`, `npx tsc --noEmit`, `npm run test:api` passed (8 tests). |
| Frontend production build | BLOCKED | Next 16.4.6 failed parsing TypeScript `--showConfig`; direct TypeScript check passes. |

The working tree contains uncommitted source/test changes in `learning_routes.py`, `learning_service.py`, `test_api.py`, `test_learning_foundation.py`, and untracked `test_learning_intelligence.py`. Matrix rows describing this integration refer to current working-tree code, not a clean committed baseline.
