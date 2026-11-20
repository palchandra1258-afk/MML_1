# Student Studio Question Blueprint

**Status:** catalog-grounded draft; every human-review field is pending. This is not an expert-approved blueprint.

Machine-readable inventory: [`question_blueprint.json`](question_blueprint.json). It is generated from the existing Student Studio curriculum by `build_question_blueprint` in `src/mcp_ri/learning/assessment_validation.py`. The JSON preserves question IDs, authored topic/objective links, prompt, options, grading definition, expected answer, explanation, and catalog difficulty. Do not regenerate it after reviewers add annotations without first merging those annotations.

## Coverage represented

| Topic | Questions |
| --- | ---: |
| Introduction to Probability | 2 |
| Conditional Probability | 2 |
| Bayes' Theorem | 2 |
| Random Variables | 2 |
| Expected Value | 3 |
| Descriptive Statistics | 2 |
| Introduction to Algorithms | 2 |

Question IDs and exact objective text are in the JSON, copied from the source catalog. The catalog has 7 single-choice, 7 multiple-choice, and 1 numeric item. All 15 are labeled `introductory`; the label is uncalibrated. The catalog includes answer keys and explanations for all items. None has a validated cognitive-demand label or an expert review record.

## Blueprint field rules

- `question_id`, curriculum IDs, wording, options, answer definition, and explanation are copied as authored facts.
- `catalog_objective_text` records the linked objective; alignment remains provisional pending review.
- `intended_cognitive_demand.value` remains `unknown` until a reviewer assigns recall, conceptual understanding, application, analysis, or problem solving with a rationale.
- `difficulty.catalog_label` is descriptive metadata only. It is not a calibrated difficulty estimate.
- `potential_ambiguity`, diagnostic suitability, conceptual validity, and psychometric quality remain pending/unknown.
- `conceptual_overlap` flags same-objective and same-topic items for reviewer inspection; it does not assert equivalence.
- `human_review.status` starts at `pending_review`. No reviewer, approval, or review date is fabricated.

## Item review unit

Review each item against its target objective, answer key, explanation, reading burden, ambiguity, distractor plausibility, cognitive demand, accessibility, and intended use. Reviewers must record evidence and suggested edits in the rubric template in [`EXPERT_REVIEW_RUBRIC.md`](EXPERT_REVIEW_RUBRIC.md). An item may be suitable for practice and unsuitable for diagnostic classification; record those decisions separately.

## Current inventory

The JSON is the row-level inventory. The source audit finds 15/15 structurally complete catalog records, 0 duplicate question IDs, and 0 structural association/grading findings. Structural completeness does not establish content correctness or assessment quality. `expected-value-q1` and `expected-value-q3` share objective `expected-value-objective-1`; their scenario overlap is flagged for human review.
