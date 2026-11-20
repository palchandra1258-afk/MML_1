# Expert Review Rubric for Student Studio Questions

**Status:** proposed instrument; no expert reviews have been performed.

## Rating scale

Use one rating per dimension and cite the exact wording, answer, objective, or evidence supporting it.

| Rating | Meaning |
| --- | --- |
| 1 | Unacceptable: materially incorrect, misleading, misaligned, or unusable; revision/rejection required. |
| 2 | Major revision: important weakness likely to affect interpretation or response. |
| 3 | Minor revision: broadly acceptable with a specific improvement recommended. |
| 4 | Acceptable: meets the dimension for the stated use. |
| N/A | Not assessable for this item or role; explain why. |

Do not use N/A to mean “not reviewed.” Use `pending_review` until a review is complete. A rating is not an empirical validity estimate.

## Dimensions

| Dimension | Reviewer question |
| --- | --- |
| Topic relevance | Does the item meaningfully assess the stated topic, rather than incidental context or unrelated knowledge? |
| Objective alignment | Does the item elicit evidence for the linked authored learning objective? |
| Conceptual accuracy | Are the premise, expected answer, grading rule, and explanation correct? |
| Clarity and ambiguity | Is wording precise, self-contained, and unlikely to support multiple defensible readings? |
| Answer-option quality | For selected-response items, are alternatives plausible, non-overlapping, and interpretable? N/A for numeric items. |
| Difficulty appropriateness | Is the catalog label plausible for the intended learner and context? This is expert judgment, not calibration. |
| Cognitive demand | What reasoning is required, and does it fit the assigned demand? Record the category and rationale separately. |
| Recall versus understanding | Could a learner succeed through superficial recall alone, or does the item elicit conceptual understanding? Explain the evidence. |
| Ambiguity and accessibility | Are language, format, assumptions, and context clear and accessible for the intended cohort? |
| Coverage and redundancy | Does this item add useful coverage, or substantially repeat another item/scenario? |
| Explanation quality | Does the feedback explain the reasoning and address likely misconceptions? |
| Assessment suitability | Is the item suitable for learner knowledge assessment, practice, formative checks, or diagnostic use? Rate each use independently. |

## Decision statuses

Allowed item statuses: `pending_review`, `approved`, `approved_with_revision`, `requires_revision`, `rejected`. Approval applies only to the stated version and use. A change to wording, answer, options, or grading requires a new review/version. Record reviewer role, date, conflicts, dimension ratings, comments, disposition, and any required edits. Keep reviewer identity in controlled study records; do not place personal data in the public blueprint.

## Review record template

```yaml
question_id: <catalog id>
item_version: <content hash or controlled version>
reviewer_pseudonym: <study-controlled code>
reviewer_role: <subject expert | assessment specialist | accessibility reviewer>
reviewed_at: <ISO-8601>
intended_use: [practice]
ratings:
  topic_relevance: {score: null, rationale: ""}
  objective_alignment: {score: null, rationale: ""}
  conceptual_accuracy: {score: null, rationale: ""}
  clarity_and_ambiguity: {score: null, rationale: ""}
  answer_option_quality: {score: null, rationale: ""}
  difficulty_appropriateness: {score: null, rationale: ""}
  cognitive_demand: {score: null, assigned_demand: unknown, rationale: ""}
  recall_vs_understanding: {score: null, rationale: ""}
  ambiguity_and_accessibility: {score: null, rationale: ""}
  coverage_and_redundancy: {score: null, rationale: ""}
  explanation_quality: {score: null, rationale: ""}
  assessment_suitability: {score: null, use_decisions: {}, rationale: ""}
required_edits: []
status: pending_review
```

Use at least two independent subject-matter reviews for content decisions and adjudicate disagreements with a documented third reviewer or panel. Assessment-use claims also require assessment-method expertise and learner evidence; expert review alone does not establish predictive validity or diagnostic accuracy.
