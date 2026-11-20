# Learner Knowledge Assessment: Validation and Calibration Foundation

**Status:** Offline descriptive validation framework implemented. Statistical reliability, predictive performance, external validity, and learner-knowledge calibration are not established.

## 1. Objectives and evidence boundary

This stage audits authored Student Studio questions and examines whether the current response thresholds, repeat handling, recency policy, and qualitative confidence are supported by available data. It does not manufacture ground truth or claim a measure of actual mastery.

The validator reads only `studio_learning_attempts` and, when present, linked `studio_evidence_records` from the explicitly supplied SQLite file. It opens the file with SQLite `mode=ro` and enables `PRAGMA query_only=ON`. It does not query EdNet artifact tables, phase research JSONL, or Azure. Reports contain aggregate counts and catalog identifiers; they omit profile, attempt, and evidence IDs.

Run a catalog-only audit:

```bash
PYTHONPATH=src .venv-api/bin/python scripts/learning/validate_student_assessment.py
```

Run against a specific local Student Studio database in read-only mode:

```bash
PYTHONPATH=src .venv-api/bin/python scripts/learning/validate_student_assessment.py \
  --database data/application/mcp_ri.sqlite3
```

The validator does not use environment database settings. Supplying a path is explicit. It does not write a report file; JSON is printed to standard output for review or redirection by the operator.

## 2. Question-quality methodology

`audit_question_quality()` checks information represented in the current curriculum: question ID uniqueness, topic/lesson/objective references, prompt and explanation presence, expected answer, question type, grading definition, option identifiers, correct-option mappings, and difficulty metadata. A structurally incomplete item is excluded from the assessment question set. Structurally complete means the catalog relationships and grading fields are internally present; it is not a pedagogical suitability judgment.

The audit marks every question as pending human content review. The catalog has no authored cognitive-demand label, item-review state, difficulty calibration, discrimination statistic, distractor analysis, or validated concept coverage. Wording ambiguity and conceptual validity therefore remain human-review questions. The following demand descriptions are a desk categorization from the prompt wording; they are not stored item metadata or expert validation.

| Topic | Question IDs | Wording-supported task description | Coverage observation |
|---|---|---|---|
| Introduction to Probability | `introduction-to-probability-q1`, `introduction-to-probability-q2` | Calculate an even outcome probability; recognize probability statements | Two objective IDs; one calculation and one selected-response concept check. |
| Conditional Probability | `conditional-probability-q1`, `conditional-probability-q2` | Calculate a conditional proportion; identify denominator/formula properties | Two objective IDs; one calculation and one selected-response concept check. |
| Bayes’ Theorem | `bayes-theorem-q1`, `bayes-theorem-q2` | Calculate a posterior from prevalence and test rates; identify sensitivity and base-rate statements | Two objective IDs; one worked numerical scenario and one selected-response concept check. |
| Random Variables | `random-variables-q1`, `random-variables-q2` | Calculate a two-coin outcome probability; identify mappings and distribution properties | Two objective IDs; one calculation and one selected-response concept check. |
| Expected Value | `expected-value-q1`, `expected-value-q2`, `expected-value-q3` | Calculate a fair-coin payout; recognize expected-value properties; enter a numeric payout | Three items map to two objective IDs. Q1 and Q3 use the same fair-coin payout scenario and share objective 1, with different response formats. They do not establish three distinct concept samples. |
| Descriptive Statistics | `descriptive-statistics-q1`, `descriptive-statistics-q2` | Calculate mean and median; identify effects of outliers and the median definition | Two objective IDs; one calculation and one selected-response concept check. |
| Introduction to Algorithms | `introduction-to-algorithms-q1`, `introduction-to-algorithms-q2` | Trace linear search comparisons; identify finite-procedure and worst-case statements | Two objective IDs; one trace/calculation and one selected-response concept check. |

The audit results are **15/15 structurally complete questions**, **0 duplicate question IDs**, **0 structural association/grading issues**, and **15/15 pending human review**. All seven topics have linked questions. Six topics have two question IDs mapped to two objective IDs; this does not prove content diversity. Expected Value has three questions and two objective IDs, with objective 1 used twice. Question types are 7 single-choice, 7 multiple-choice, and 1 numeric. Difficulty metadata is present and says introductory for all 15 questions. Cognitive-demand labels and ambiguity outcomes are not encoded.

Manual desk review found that prompts, answer keys, and explanations are present and no obvious wording defect stood out in this pass. The current schemas and audit support structural option/key/lesson/topic/objective checks. This pass is not an independent subject-matter review and does not validate pedagogical quality. No catalog content was changed.

## 3. Evidence sufficiency and threshold sensitivity

`analyze_student_studio_attempts()` groups responses by profile, topic, and question. A repeat on the same question increases the attempt count, but it does not increase distinct-question coverage. The report includes per-question response counts, repeat counts, distinct profile counts, topics with no observations, and sensitivity scenarios for minimum distinct-question thresholds 1, 2, 3, and 5.

The local database inspection on 20 November 2026 found:

- One Student Studio profile in the attempt table; it is the unauthenticated local demo identity, not a multi-learner sample.
- Two catalog-mapped answer attempts, both on Introduction to Probability, across two distinct questions.
- `introduction-to-probability-q1`: one correct response; `introduction-to-probability-q2`: one incorrect response. Each has one profile and zero repeats.
- One correct and one incorrect response; no repeated attempts and no within-question outcome change.
- Both canonical evidence links passed source dataset, source event, topic, and question checks.
- Six of seven catalog topics have no saved response observations.
- The event timestamps span 14.06 seconds on 18 November 2026; there are no missing timestamps in this sample.

At thresholds 1, 2, 3, and 5, the observed profile/topic summaries were the same: one conflicting response pattern and six insufficient-evidence topics. The one observed topic is conflicting at every threshold; the six other topics remain unassessed. This sample cannot compare the behavior of the threshold for consistent positive or negative patterns. The existing two-distinct-question rule remains provisional; there is no evidence here to select or calibrate it.

There are not enough learners, item responses, or independent targets to calculate or interpret internal consistency, item discrimination, predictive performance, or external validity. The reported response distribution is descriptive only.

## 4. Recency and repeated attempts

The current assessment does not expire or down-weight historical responses. It exposes timestamp ranges. The offline report computes event-time spans and flags same-question outcome changes, without assigning a recent/historical boundary. There are no repeated attempts or older-vs-newer conflicts in the inspected local sample, so forgetting, recency weighting, and long-gap effects cannot be evaluated.

Conflicting outcomes remain conflicting even when timestamps differ. The assessment does not select the newest response as the truth. Repeated answers to one item do not satisfy a distinct-question threshold; a changed outcome on that item is explicitly surfaced. Any future decay or recency weighting requires a justified and versioned rule, suitable data, tests, and validation.

## 5. Confidence methodology

Assessment confidence is separate from estimated knowledge. It describes confidence in assigning the provisional response-pattern category; it is not a probability that a learner knows a topic.

- No matching observation produces `insufficient` confidence.
- Any observed pattern currently receives `low` confidence. The response includes a `confidence_basis` describing response count, distinct-question coverage, evidence provenance, question-review status, exact topic mapping, and the descriptive-only recency policy.
- The system no longer emits `moderate` or `high` confidence. Two consistent answers on different, introductory, uncalibrated questions do not justify those levels.
- Exact catalog identifiers make evidence traceable to a topic and question. They do not validate the item's content or establish transfer to a broader topic.
- A structurally incomplete item is excluded from assessment; the topic response is marked `structurally_incomplete` when one or more linked catalog questions fail structural checks.

Confidence values remain qualitative. No numeric confidence or mastery estimate is calculated.

## 6. Validation framework architecture and actual output

New reusable functions live in `src/mcp_ri/learning/assessment_validation.py`:

- `audit_question_quality(curriculum)` returns question-level structural findings and topic coverage.
- `read_student_studio_attempts_read_only(path)` reads only the Student Studio attempt and evidence tables, validates canonical provenance, and never opens the database for writes.
- `analyze_student_studio_attempts(...)` computes aggregate response distributions, repeats, threshold sensitivity, confidence-category counts under the current rule, missingness, provenance counts, and timestamp descriptions.
- `scripts/learning/validate_student_assessment.py` produces deterministic JSON and permits catalog-only operation.

The actual aggregate run reported `descriptive_only`, one profile, two mapped attempts, one correct and one incorrect, two valid canonical evidence records, zero unmapped or provenance-invalid attempts, one conflicting topic, and six insufficient-evidence topics. It reported `internal_consistency_or_reliability: not_established`, `predictive_performance: not_evaluated_no_independent_targets`, and `external_validity: not_evaluated_no_independent_knowledge_measure`.

These are descriptive results from the current local demo history. Test fixtures are used only to test code paths; they are not included in those actual findings.

## 7. Assessment implementation changes

`studio-binary-evidence-1.1` adds explicit question-quality status, confidence basis, repeat-attempt count, same-question outcome changes, and provenance notes. Repeated responses do not increase distinct-question coverage. Mixed outcomes—including a changed response to the same item—remain conflicting. The method continues to preserve all attempt/evidence identifiers, timestamps, and outcomes. It keeps descriptive Phase 9 aggregates separate from computed topic interpretations.

The API remains `POST /api/v1/studio/learning-plans/preview`. Validation adds no endpoint, database table, or provider call. Assessment remains additional context; it does not skip lessons, change prerequisites, increase difficulty, or reorder the curriculum.

No frontend change was justified: the current Student Studio interface does not present learning-plan previews. A future minimal assessment panel should show the topic status, low/insufficient confidence, reason, observation count, evidence references, timestamp range, and available catalog diagnostic. It must not render a mastery percentage or hide conflicting/unknown evidence.

## 8. Validation status and limits

| Claim type | Status |
|---|---|
| Implemented | Catalog structural audit, read-only Student Studio aggregation, threshold scenarios, timestamp/repeat reporting, confidence rationale, and typed response fields. |
| Tested | Structural errors, objective/lesson mismatches, duplicate IDs, missing coverage, threshold 1/2/3 behavior, repeated attempts, contradictory outcomes, learner/source separation, SQLite read-only behavior, missing data, and deterministic aggregate output. |
| Descriptively evaluated | Current 15-question catalog and the local one-profile, two-attempt history summarized above. |
| Statistically validated | No. |
| Predictively validated | No independent target is available. |
| Externally validated | No independent measure of learner knowledge is available. |

The database contains only one local demo profile, not a real multi-user cohort. No independent knowledge assessment, delayed retention measure, transfer task, or learning outcome is linked. The current item set is small and mostly introductory selected response. It cannot establish item reliability or topic mastery. No validation result should be interpreted as a claim of scientific validity.

## 9. Tests

Focused tests are in:

- `tests/learning/test_assessment_validation.py`
- `tests/api/test_learning_plans.py`
- Existing canonical evidence tests in `tests/api/test_learning_evidence_persistence.py`

Test-created databases are disposable and are not part of the descriptive local-data findings. The validation CLI itself is read-only.

## 10. Future research requirements

Before calibration or automatic adaptation, MCP-RI needs an expert-reviewed item blueprint, broader and authenticated participant samples, enough responses per item and topic, item-level response analysis, independent knowledge criteria, repeated or delayed assessments, transfer measures, and preregistered evaluation of thresholds and recency rules. Any confidence calibration needs held-out outcomes and subgroup analysis. Until then, retain the current provisional threshold, low confidence, visible uncertainty, and manual review requirement.
