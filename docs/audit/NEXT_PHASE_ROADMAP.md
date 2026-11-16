# Recommended next-phase roadmap

This roadmap is based on current verified gaps. It does not authorize or begin implementation.

## Phase A — Stabilize and verify current Studio integration

- **Objective:** Make current answer → evidence → behavioral-state → next-activity behavior reviewable and reproducible across backend, contract, and UI.
- **Required modules:** `api/learning_*`, `api/persistence.py`, evidence normalizer/state bridge, learner-state accumulator, frontend Studio client/service/types, shared OpenAPI contract.
- **Likely files:** `src/mcp_ri/api/learning_routes.py`, `learning_service.py`, `learning_schemas.py`, `persistence.py`; `migrations/versions/0003_f10_learning_intelligence.py`; `frontend/lib/services/learning.service.ts`, `frontend/components/studio/student-studio-client.tsx`, `shared/api-contracts/openapi.json`, API tests.
- **Dependencies:** Resolve and review existing uncommitted work; install documented API test environment; decide exact response contract. No cognitive mapping required for this bounded functionality.
- **Acceptance criteria:** OpenAPI matches routes/schemas; frontend renders processing outcome and recommendation with limitations; unknown/unavailable states are explicit; replay, failure rollback, profile isolation assumptions and concurrency semantics are covered; existing EdNet files remain untouched.
- **Tests:** API tests with temporary SQLite; migration upgrade on a temporary DB; frontend service/component tests; full frontend lint/type/build; complete browser smoke journey against disposable local API/database.
- **Deliverables:** Versioned contract, verified Studio workflow report, test output and implementation notes.
- **Risks:** Singleton identity may be mistaken for authentication; retry semantics can create duplicate submissions if IDs change; keep recommendation claims behavioral.

## Phase B — Identity, privacy, and persistence design

- **Objective:** Define and implement learner authentication/authorization, per-account data scope, retention and concurrency before real users.
- **Required modules:** API middleware/dependencies, persistence schemas, Studio services, deployment/configuration, frontend session handling.
- **Likely files:** `src/mcp_ri/api/{main,dependencies,persistence,settings}.py`, new migrations, learning/research routes, frontend API client and shell, docs.
- **Dependencies:** Security/privacy requirements, user/session provider choice, deployment threat model.
- **Acceptance criteria:** Every learner-scoped request derives authorized identity from verified credentials; cross-account access tests fail safely; no global demo profile in production configuration; retention/export/deletion behavior documented; multi-process ordering/transaction strategy defined.
- **Tests:** AuthN/AuthZ API matrix, cross-learner isolation, concurrent submissions, migration and recovery, configuration secret checks.
- **Deliverables:** Threat model, identity design, production boundary checklist, tested data-scoping behavior.
- **Risks:** Schema migrations affect existing local learning records; plan backup/upgrade before deployment.

## Phase C — Concept grounding and content provenance

- **Objective:** Establish a reviewed ontology connecting authored topics, objectives, questions and evidence to stable concept IDs.
- **Required modules:** Curriculum catalog, question bank, content metadata, representation/trajectory grounding registries, evidence provenance.
- **Likely files:** `src/mcp_ri/learning/curriculum.json`, `learning_schemas.py`, new mapping/schema/validation tools, representation grounding and dependency registry.
- **Dependencies:** Subject matter expert review; do not infer mappings from EdNet skill IDs or labels alone.
- **Acceptance criteria:** Every mapped topic/objective/question has provenance, reviewer/version, explicit confidence/status; unresolved mappings remain unmapped; dependency graph has reviewed sources and cycle validation.
- **Tests:** Schema validation, referential integrity, version compatibility, unsupported-mapping tests, review workflow.
- **Deliverables:** Versioned concept map, content catalog audit and approved mapping evidence.
- **Risks:** False mappings create unsupported cognitive interpretations or prerequisite claims; preserve unmapped states.

## Phase D — Research validation for cognitive and adaptive claims

- **Objective:** Define and validate constructs before using cognitive estimates to choose instruction.
- **Required modules:** Research protocol, annotation pipeline, cognitive estimator evaluation, representation provider/outcome logging, analysis scripts.
- **Likely files:** `docs/COGNITIVE_STATE_METHODOLOGY.md`, `src/mcp_ri/cognitive_state/`, evaluation scripts/reports, new study artifacts.
- **Dependencies:** Validated labels or expert/self-report protocol, ethics/privacy approvals as applicable, representative data and preregistered estimands.
- **Acceptance criteria:** Construct definitions and label reliability reported; held-out evaluation designed without test leakage; hypothesis-vs-diagnosis boundaries explicit; intervention exposure and outcomes measured; no effectiveness claim without appropriate comparison.
- **Tests:** Reproducibility checks and synthetic unit coverage plus statistical validation on approved data; locked partition remains untouched until protocol freeze.
- **Deliverables:** Protocol, annotation guide, validation report and go/no-go decision for adaptive use.
- **Risks:** Correctness/retry labels are invalid proxies for cognition; selection and intervention confounding can invalidate outcome claims.

## Phase E — Representation delivery and trajectory integration (conditional)

- **Objective:** Only after C and D pass, connect supported estimates to actual reviewed activities and trace exposure/outcomes.
- **Required modules:** Representation availability registry/provider, Studio activity delivery, dependency graph, trajectory persistence, event/evidence provenance.
- **Likely files:** `src/mcp_ri/representation/`, `trajectory/`, `api/learning_service.py`, persistence migrations, Studio UI and evaluation reports.
- **Dependencies:** Approved concept map, available content provider, validated rules/evaluators, identity isolation from Phase B.
- **Acceptance criteria:** The recommended content actually exists and is delivered; plan, evidence, content version and learner response link end-to-end; unavailable paths defer honestly; trajectory states are learner-authorized and reconstructible; outcomes are evaluated against preregistered measures.
- **Tests:** API/UI integration, delivery/replay/recovery, provenance checks, decision tests and controlled learning-effectiveness evaluation.
- **Deliverables:** Auditable adaptive activity pipeline and bounded evaluation report.
- **Risks:** A plan is not exposure; exposure is not mastery; uncontrolled outcomes cannot establish treatment benefit.
