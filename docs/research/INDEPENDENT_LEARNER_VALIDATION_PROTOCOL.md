# Independent Learner Validation Protocol

**Status:** protocol draft. No recruitment, independent assessment, or validation study has been conducted. No sample size or outcome is claimed.

## Purpose and estimand

Evaluate how well a frozen MCP-RI learner-knowledge prediction agrees with an independently obtained reference for a prespecified topic/skill and learner population. This is agreement with the chosen reference procedure, not proof of an unobservable ground truth. Freeze code, thresholds, curriculum, and item versions before evaluation; record hashes and protocol version.

## Participants, consent, and privacy

- Obtain institutional/organizational review and informed consent before recruitment. Explain data use, retention, withdrawal, risks, and whether participation affects grades or access.
- Assign opaque pseudonyms (`p_<opaque-token>`). Keep the re-identification key separately under restricted access; never put names, email, or student numbers in analysis exports.
- Collect only necessary age/cohort/context fields, with consent and a retention schedule. Report aggregates and suppress small cells under the study's approved policy.
- Do not use production student data as a reference label without the required consent/authorization and governance.

## Independent reference measure

Use an assessment that is not the same question set or response history used by MCP-RI. Map both instruments to the same prespecified skill definitions. Use expert-reviewed parallel items or an appropriately justified external measure; obtain independent scoring, preferably blind to MCP-RI output. Define scoring, cut points, handling of partial credit, uncertainty, and adjudication before collecting data. If reference raters are used, double-score a prespecified subset and report agreement with uncertainty.

The reference is an operational comparison standard, not automatically ground truth. Document its own evidence, limitations, and possible measurement error. Do not derive a reference label from the same Student Studio answers that generated the prediction.

## Procedure and leakage controls

1. Consent and assign pseudonym; record eligibility and cohort using approved minimum fields.
2. Administer the independent measure in a controlled session. Record item version, scoring, accommodations, and timestamp.
3. Freeze/export the MCP-RI prediction and provenance without revealing the reference score to the prediction process or assessor.
4. Score the independent measure blind to MCP-RI output; adjudicate disagreements according to the prespecified rule.
5. Join records by pseudonym only inside the restricted analysis environment.
6. Assign each learner wholly to `development` or `evaluation`; no learner may appear in both. Freeze the evaluation partition before tuning. Repeated attempts by one learner stay in one partition.
7. Report recruitment, exclusions, missingness, attrition, protocol deviations, and confidence intervals; retain an audit trail.

## Sample-size planning

Choose the primary endpoint and smallest practically important performance before recruitment. Plan with a statistician using expected prevalence, target confidence-interval width or power, clustering/repeated measures, subgroup analyses, reference-measure reliability, and expected attrition. For a simple independent binomial proportion only, a rough precision calculation is `n = z² p(1-p) / d²`; it is not a selected sample size and does not cover paired comparisons, class imbalance, clustering, or multilevel data. Inflate for design effect and attrition only under justified assumptions. Do not select a sample size from the current small local Student Studio history.

## Data contract for offline evaluator

The optional `evaluate_independent_predictions` helper accepts rows with pseudonymous learner ID, a development/evaluation partition, prediction, independent reference label, and `reference_is_independent: true`. Optional probability maps require a prespecified class set. It outputs aggregate counts/metrics and does not output learner IDs. It rejects malformed pseudonyms and cross-partition learner leakage. This helper is an offline research utility, not an endpoint or a deployed adaptive decision.

No study data are currently present in this format. The helper must return “not computable” when independent references are absent; catalog correctness or Student Studio attempt history is not a substitute.
