# Assessment Evaluation Framework

**Status:** offline analysis specification and optional helper. No independent learner labels currently support predictive evaluation.

## Evidence tiers

1. **Catalog structure:** IDs, links, format, answer definition, explanation, and metadata completeness. Structural checks do not show item validity.
2. **Expert content review:** rubric ratings and documented adjudication. This supports content review, not learner-level predictive accuracy.
3. **Descriptive response analysis:** counts, correctness patterns, repeats, provenance, and coverage from Student Studio. These describe observed records and are not independent validation.
4. **Independent evaluation:** frozen predictions compared with a prespecified independent measure on learner-disjoint evaluation data. Only this tier supports the predictive metrics below, and claims remain bounded by reference quality and sampling.

## Metric rules

On independent evaluation labels, report confusion matrix, accuracy, per-class precision/recall/F1, macro-F1, balanced accuracy, support, evaluation coverage, and uncertainty intervals appropriate to the sampling design. Report class prevalence and missingness. Never hide unsupported/undefined class metrics. `insufficient_evidence`, `conflicting_evidence`, `abstain`, and unknown outputs are abstentions: report their count and coverage; do not recode them as “not yet demonstrated.”

For probability outputs only, report a proper score such as multiclass Brier score and calibration bins/plot with bin counts. A confidence category is not a probability. Current MCP-RI learner-state output is qualitative, so calibration metrics are unavailable. Inter-rater reliability for independent categorical ratings may include unweighted Cohen's kappa and observed agreement; report prevalence and limitations because kappa depends on marginal rates. For ordinal ratings, use a prespecified weighted method; do not substitute unweighted kappa silently.

## Implemented offline helper

`src/mcp_ri/learning/independent_evaluation.py` provides:

- `evaluate_independent_predictions(records, ...)`: refuses to emit predictive metrics without rows explicitly marked as independent references; validates opaque pseudonyms and learner-disjoint partitions; excludes non-independent labels; reports abstention and evaluation coverage; computes classification metrics; computes Brier/calibration only when complete valid class probabilities are supplied.
- `cohen_kappa(rater_a, rater_b)`: paired, unweighted categorical agreement with missing pairs excluded and counted.

No database writes, API route, third-party dependency, or Azure/provider request is involved. The caller must define a prediction-to-reference mapping in the approved protocol if label vocabularies differ. The helper is for analysis, not ground truth or automatic adaptation.

## Current reportability

The source audit found 15 structurally complete catalog records across 7 topics. Existing Student Studio practice attempts are not independent labels. Therefore no predictive accuracy, precision, recall, F1, confusion matrix, balanced accuracy, or calibration claim is currently computed. Do not treat the illustrative unit-test fixtures as learner evidence.
