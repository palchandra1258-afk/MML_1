# Learner Knowledge Assessment

## Purpose and scope

The Student Studio learning-plan preview now includes a computed, evidence-linked interpretation of saved responses for the exact catalog topics included in a plan. It is a bounded assessment layer over existing data. It is not a new persistent learner model, an adaptive mastery model, or a scientifically validated measure.

The endpoint remains `POST /api/v1/studio/learning-plans/preview`. Assessment is read-only, computed for each request, and works without an AI provider. No assessment rows, plans, or new tables are created.

## Architecture and source systems

| Component | Use in this assessment | Boundary |
|---|---|---|
| F9 Student Studio | Server-graded answer attempts, exact profile/topic/question IDs, timestamps | Attempts describe responses to particular catalog questions. |
| F10.1 evidence foundation | Canonical evidence IDs and provenance linked to source attempts | An evidence record is trusted only when its source dataset, source attempt, topic, and question agree with the persisted attempt. |
| Phase 9 behavioral state | Latest state version bounds retrieval; existing response aggregates remain visible in the legacy `knowledge_assessment` response field | Aggregates are descriptive summaries, not verified current knowledge. |
| Phase 11 cognitive state | No Studio topic estimate is consumed | Existing research snapshots are not mapped to Studio's local profile and topics. |
| Phase 12 representation planning | Not consumed | No supported Studio concept link or executable delivery capability is established. |
| Phase 13 trajectory | Not consumed | Its dependency registry does not provide a validated Studio curriculum graph. |
| Learning planner | Supplies mapped topics, lesson IDs, and curated question IDs | Only exact catalog mappings are eligible; no semantic topic mapping is inferred. |
| Provider interface | Reports provider availability | Retrieval, assessment, and plan preview do not invoke a provider. Azure is not used. |

Student Studio evidence is stored separately from the EdNet research artifact index. Retrieval queries only `studio_learning_attempts` and the linked `studio_evidence_records` for `studio-local-demo`. It does not read or combine research artifacts.

## Evidence retrieval and provenance

`StudentStudioEvidenceRetrieval` accepts the topic and curated question IDs already selected by the planner. It then:

1. Selects attempts for the local Student Studio profile and those exact topic/question IDs.
2. Bounds the query to the latest committed Phase 9 source event sequence when a snapshot exists.
3. Joins canonical F10.1 evidence by source attempt ID and profile.
4. Requires canonical evidence provenance to name `mcp-ri-student-studio`, the same source attempt, topic, and question. Inconsistent evidence rows are excluded.
5. Preserves attempt ID, evidence ID where present, question ID, binary outcome, event timestamp, source dataset, and source record ID in each returned observation.

An attempt without a linked canonical evidence row remains a source attempt observation with no fabricated evidence ID or provenance. `evidence_count` in this response means the count of relevant persisted response observations. A response observation is not interpreted as a direct measure of knowledge.

## Qualitative assessment methodology

No numerical mastery score is calculated. Outcomes use `correct` or `incorrect` only as recorded by the existing server-side evaluator. The current method version is `studio-binary-evidence-1.1`.

| Condition | Status | Confidence | Interpretation |
|---|---|---|---|
| No relevant response observations | `insufficient_evidence` | `insufficient` | Current understanding is unknown. This is not a knowledge gap. |
| At least one response, but fewer than two distinct questions, with no mixed outcomes | `needs_further_assessment` | `low` | The sample is too small for a topic-level interpretation. |
| At least two distinct questions, all responses correct | `supported_understanding` | `low` | Performance supports understanding on those items only, not general mastery. |
| At least two distinct questions, all responses incorrect | `developing_understanding` | `low` | The observations support offering review, but do not prove the learner lacks knowledge. |
| Both correct and incorrect outcomes | `conflicting_evidence` | `low` | Evidence is inconsistent; more evidence is needed. |

The two-distinct-question threshold is a conservative engineering heuristic, not an empirically calibrated or scientifically validated rule. Repeated attempts on one question do not satisfy it; different outcomes on repeated attempts are explicitly reported as conflict. Confidence is qualitative and reflects sample coverage, consistency, exact-ID provenance, and the absence of recorded human question review or psychometric validation. Assessed response patterns currently receive `low` confidence even when outcomes are consistent. No response pattern receives `moderate` or `high` confidence. The system does not apply recency decay; timestamps and their range are exposed so historical evidence is visible without presenting it as current verification. Old and new conflicting responses remain conflicting.

Supporting and contradictory attempt/evidence identifiers are included alongside an observation list that preserves the attempt-to-evidence pairing. For conflicting results, no response is treated as the sole supporting outcome; all observed identifiers are marked as part of the conflict.

## Unknowns, learning needs, and next activities

- `insufficient_evidence` means no matching response was found. It is not a gap or deficiency.
- `needs_further_assessment` means a small sample exists. It is not a negative knowledge judgment.
- `conflicting_evidence` means saved outcomes disagree; no stable estimate is made.
- `developing_understanding` is a provisional interpretation of multiple distinct incorrect responses and can suggest review of an existing linked lesson.
- `supported_understanding` is limited to observed performance on the curated questions.

For unknown, small-sample, or conflicting topics, the response may recommend the first unattempted curated question already linked to that topic. If no such question exists, it reports no diagnostic activity available. It does not generate questions or invent lessons. The current learning sequence is not reordered or skipped based on this assessment; guidance is shown separately from the sequence.

## API response

The existing response shape remains intact. `knowledge_assessment` continues to carry the earlier Phase 9 descriptive summary for compatibility. New per-topic interpretations are under `evidence_based_assessment`, and `assessment_guidance` provides catalog-grounded next actions.

Representative excerpt for an unassessed probability topic:

```json
{
  "evidence_based_assessment": {
    "schema_version": "1.0",
    "method_version": "studio-binary-evidence-1.1",
    "status": "insufficient_evidence",
    "source": "student_studio_attempts",
    "learner_profile_id": "studio-local-demo",
    "topics": [{
      "topic_id": "introduction-to-probability",
      "topic_title": "Introduction to Probability",
      "status": "insufficient_evidence",
      "confidence": "insufficient",
      "confidence_basis": ["No matching observations are available; confidence is insufficient."],
      "question_quality_status": "unreviewed",
      "evidence_count": 0,
      "distinct_question_count": 0,
      "repeat_attempt_count": 0,
      "questions_with_outcome_changes": [],
      "supporting_attempt_ids": [],
      "supporting_evidence_ids": [],
      "contradictory_attempt_ids": [],
      "contradictory_evidence_ids": [],
      "retrieval_notes": [],
      "observations": [],
      "observed_time_range": null,
      "recommended_activity": {
        "action": "diagnostic_question",
        "topic_id": "introduction-to-probability",
        "lesson_id": null,
        "question_id": "introduction-to-probability-q1",
        "title": "Try a diagnostic question for introduction-to-probability",
        "reason": "This topic has no saved response evidence; an existing curated question can serve as a diagnostic."
      }
    }]
  },
  "assessment_guidance": [{
    "topic_id": "introduction-to-probability",
    "interpretation": "insufficient_evidence",
    "action": "diagnostic_question",
    "question_id": "introduction-to-probability-q1",
    "lesson_id": null
  }]
}
```

## Limitations and assumptions

- The only current learner identity is the fixed unauthenticated local demo profile.
- Evidence only applies to topics/questions with exact current Student Studio catalog IDs. Generated lessons, EdNet skills, and semantically similar topics are not inferred into this map.
- Binary correctness does not account for guessing, question difficulty, item validity, accommodations, answer changes, or transfer to new problems.
- The threshold and qualitative categories have not been calibrated against learner outcomes or validated by educational research.
- Phase 9 snapshots and Phase 11 cognitive estimates remain distinct from these computed assessment results.
- The assessment is an additional planning context; it does not alter, persist, or claim an optimized plan.
- Assessment is computed from the latest event prefix and is not a durable historical snapshot. A later preview can differ after new responses.
- Confidence describes the provisional response-pattern interpretation, not a probability that the learner knows the topic.

## Tests and validation

Focused coverage is in `tests/api/test_learning_plans.py` and includes exact evidence retrieval, learner/topic/question filtering, source provenance, no evidence, positive and negative response patterns, conflicting observations, small and repeated-question samples, historical timestamps, missing question mappings, diagnostic unavailability, provider independence, plan-sequence compatibility, and route schema exposure.

Relevant existing F10.1 persistence tests use disposable SQLite databases and verify canonical attempt/evidence linkage. No configured database is used by these tests.

## Future validation work

Before using these categories for automated adaptation, evaluate question quality, sample-size thresholds, temporal decay, calibration, subgroup performance, and learning outcomes. Any validated concept or skill mapping, learner identity change, persisted assessment history, or research-data integration requires a separately reviewed design. Persistence would require a migration proposal and review before application.
