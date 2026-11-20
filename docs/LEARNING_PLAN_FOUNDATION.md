# Learning Plan Foundation

## Scope

`POST /api/v1/studio/learning-plans/preview` returns a non-persisted plan preview for the local Student Studio profile. The preview uses the authored catalog and does not call an AI provider. Its response labels `generation_mode` as `rule_based`, sets `persisted` to `false`, and reports provider availability and whether a provider was invoked.

The service maps goal words against existing subject, course, unit, topic, objective, and description text. It includes only existing lessons and curated questions. A topic's prerequisite edges are used only when the catalog marks them `validated`; missing referenced lessons and cycles are surfaced as missing information. Topics without established prerequisites retain catalog order, which is not presented as a prerequisite claim.

## Provider boundary

`mcp_ri.learning.providers` defines the structured provider protocol and an unavailable implementation. The existing Azure client remains separate and unchanged for this feature. The `gpt-realtime` deployment is not treated as a text-generation model, and learning-plan previews never invoke it. Provider integration can later implement the protocol without coupling curriculum planning to Azure.

## Evidence and limits

The service reads the latest committed Phase 9 Student Studio behavioral snapshot and links its response summaries to saved Phase 10 evidence IDs, bounded to the snapshot's source event sequence. It performs no state reconstruction or writes. Summaries are explicitly descriptive response history, not validated knowledge, diagnosis, or mastery. Phase 11 cognitive state, Phase 12 representation planning, and Phase 13 trajectories are not assumed to be validated Student Studio evidence and are not merged into a duplicate learner model.

Current keyword matching is a transparent baseline and can return partial or unsupported mappings. Empty catalog areas are reported as gaps. The plan preview is not persisted and there is no student-facing plan management or adaptive decision loop in this slice. No database schema change or migration is required.

The preview also returns an evidence-grounded topic assessment computed from exact Student Studio attempt and canonical evidence links. Its qualitative categories and provisional two-distinct-question rule are documented in [`LEARNER_KNOWLEDGE_ASSESSMENT.md`](LEARNER_KNOWLEDGE_ASSESSMENT.md). Assessment guidance is surfaced beside the curriculum sequence and does not skip or reorder lessons.

## Local verification

Run the focused tests from the repository root:

```bash
PYTHONPATH=src .venv-api/bin/pytest tests/api/test_learning_plans.py -q
```

Regenerate the checked-in API contract after changing routes or response schemas:

```bash
PYTHONPATH=src .venv-api/bin/python scripts/api/export_openapi.py
```
