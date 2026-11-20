"""Evaluation helpers that require independent learner-reference labels."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence


_PSEUDONYM = re.compile(r"^p_[A-Za-z0-9_-]{6,96}$")
_ABSTENTION_PREDICTIONS = {"insufficient_evidence", "conflicting_evidence", "abstain", "unknown"}


def _validate_learner_partitions(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    learner_partition: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for row in records:
        learner = row.get("pseudonymous_learner_id")
        partition = row.get("partition")
        if not isinstance(learner, str) or not _PSEUDONYM.fullmatch(learner):
            raise ValueError("each record requires a pseudonymous learner ID in p_<opaque-token> form")
        if partition not in {"development", "evaluation"}:
            raise ValueError("partition must be 'development' or 'evaluation'")
        previous = learner_partition.get(learner)
        if previous is not None and previous != partition:
            raise ValueError("a learner appears in more than one partition")
        learner_partition[learner] = partition
        counts[partition] += 1
    return dict(sorted(counts.items()))


def _classification_metrics(
    references: Sequence[str], predictions: Sequence[str],
) -> dict[str, Any]:
    labels = sorted(set(references) | set(predictions))
    matrix = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for actual, predicted in zip(references, predictions):
        matrix[actual][predicted] += 1
    per_class = {}
    precision_values: list[float] = []
    recall_values: list[float] = []
    f1_values: list[float] = []
    supported_recalls: list[float] = []
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[actual][label] for actual in labels if actual != label)
        fn = sum(matrix[label][predicted] for predicted in labels if predicted != label)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (2 * precision * recall / (precision + recall)) if precision is not None and recall is not None and precision + recall else (0.0 if precision is not None and recall is not None else None)
        support = sum(matrix[label].values())
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}
        if precision is not None:
            precision_values.append(precision)
        if recall is not None:
            recall_values.append(recall)
        if f1 is not None:
            f1_values.append(f1)
        if support:
            supported_recalls.append(recall or 0.0)
    total = len(references)
    accuracy = sum(actual == predicted for actual, predicted in zip(references, predictions)) / total if total else None
    return {
        "sample_count": total,
        "labels": labels,
        "accuracy": accuracy,
        "balanced_accuracy": sum(supported_recalls) / len(supported_recalls) if supported_recalls else None,
        "macro_precision": sum(precision_values) / len(precision_values) if precision_values else None,
        "macro_recall": sum(recall_values) / len(recall_values) if recall_values else None,
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else None,
        "per_class": per_class,
        "confusion_matrix": matrix,
        "undefined_precision_classes_excluded_from_macro": [label for label, stats in per_class.items() if stats["precision"] is None],
    }


def _calibration_report(
    rows: Sequence[Mapping[str, Any]],
    labels: Sequence[str],
    bin_edges: Sequence[float] | None,
) -> dict[str, Any]:
    if not rows or not any(row.get("probabilities") is not None for row in rows):
        return {"status": "not_available_no_probability_estimates", "multiclass_brier_score": None, "bins": None}
    if any(row.get("probabilities") is None for row in rows):
        return {"status": "not_computable_incomplete_probability_estimates", "multiclass_brier_score": None, "bins": None}

    brier_values: list[float] = []
    top_confidences: list[float] = []
    top_correct: list[float] = []
    for row in rows:
        probabilities = row["probabilities"]
        if set(probabilities) != set(labels):
            raise ValueError("each probability map must contain exactly the evaluation labels")
        values = [float(probabilities[label]) for label in labels]
        if any(not math.isfinite(value) or value < 0 or value > 1 for value in values) or not math.isclose(sum(values), 1.0, abs_tol=1e-6):
            raise ValueError("class probabilities must be finite, between 0 and 1, and sum to 1")
        brier_values.append(sum((probabilities[label] - float(row["reference_label"] == label)) ** 2 for label in labels))
        top_label = max(labels, key=lambda label: probabilities[label])
        top_confidences.append(float(probabilities[top_label]))
        top_correct.append(float(top_label == row["reference_label"]))

    bins = None
    if bin_edges is not None:
        edges = list(bin_edges)
        if len(edges) < 2 or edges[0] != 0 or edges[-1] != 1 or any(a >= b for a, b in zip(edges, edges[1:])):
            raise ValueError("calibration bin edges must strictly increase from 0 to 1")
        bins = []
        for index, (lower, upper) in enumerate(zip(edges, edges[1:])):
            members = [
                i for i, confidence in enumerate(top_confidences)
                if (lower <= confidence <= upper if index == len(edges) - 2 else lower <= confidence < upper)
            ]
            bins.append({
                "lower": lower,
                "upper": upper,
                "count": len(members),
                "mean_confidence": sum(top_confidences[i] for i in members) / len(members) if members else None,
                "observed_accuracy": sum(top_correct[i] for i in members) / len(members) if members else None,
            })
    return {
        "status": "computed_from_independent_reference_labels",
        "multiclass_brier_score": sum(brier_values) / len(brier_values),
        "bins": bins,
        "note": "Calibration is evaluated only when caller supplies probability estimates and independent references; current MCP-RI outputs qualitative confidence only.",
    }


def evaluate_independent_predictions(
    records: Iterable[Mapping[str, Any]],
    *,
    prediction_to_reference_label: Mapping[str, str] | None = None,
    calibration_bin_edges: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Evaluate only rows carrying an explicitly independent reference label.

    `prediction_to_reference_label` must be specified by the study protocol if
    model categories and independent assessment categories differ. No mapping
    is invented here. Abstentions are reported separately from classification
    metrics, and never silently counted as a negative knowledge label.
    """
    rows = list(records)
    partition_counts = _validate_learner_partitions(rows)
    independently_labeled = [
        row for row in rows
        if row.get("reference_label") is not None and row.get("reference_is_independent") is True
    ]
    excluded_non_independent = sum(
        row.get("reference_label") is not None and row.get("reference_is_independent") is not True
        for row in rows
    )
    if not independently_labeled:
        return {
            "status": "not_computable_no_independent_reference_labels",
            "partition_record_counts": partition_counts,
            "independent_reference_count": 0,
            "unlabeled_record_count": sum(row.get("reference_label") is None for row in rows),
            "excluded_non_independent_reference_count": excluded_non_independent,
            "classification_metrics": None,
            "evaluation_coverage": None,
            "abstention_count": None,
            "calibration": {"status": "not_available_no_independent_reference_labels", "multiclass_brier_score": None, "bins": None},
            "claim_boundary": "No predictive or calibration metric is emitted without an independent reference measure.",
        }

    label_map = dict(prediction_to_reference_label or {})
    scored_rows: list[dict[str, Any]] = []
    abstentions = 0
    for row in independently_labeled:
        prediction = row.get("prediction")
        if prediction in _ABSTENTION_PREDICTIONS or prediction is None:
            abstentions += 1
            continue
        if label_map and prediction not in label_map:
            raise ValueError(f"prediction {prediction!r} has no protocol-defined reference-label mapping")
        scored_rows.append({
            "prediction_label": label_map.get(prediction, prediction),
            "reference_label": str(row["reference_label"]),
            "probabilities": row.get("probabilities"),
        })
    references = [row["reference_label"] for row in scored_rows]
    predictions = [row["prediction_label"] for row in scored_rows]
    metrics = _classification_metrics(references, predictions) if scored_rows else None
    evaluation_labels = sorted({
        label
        for row in scored_rows
        for label in (row["probabilities"].keys() if row["probabilities"] is not None else references)
    })
    calibration_rows = [
        {"reference_label": row["reference_label"], "probabilities": row["probabilities"]}
        for row in scored_rows
    ]
    return {
        "status": "computed" if scored_rows else "no_scored_predictions",
        "partition_record_counts": partition_counts,
        "independent_reference_count": len(independently_labeled),
        "unlabeled_record_count": sum(row.get("reference_label") is None for row in rows),
        "excluded_non_independent_reference_count": excluded_non_independent,
        "classification_metrics": metrics,
        "evaluation_coverage": len(scored_rows) / len(independently_labeled),
        "abstention_count": abstentions,
        "calibration": _calibration_report(calibration_rows, evaluation_labels, calibration_bin_edges) if scored_rows else {
            "status": "not_computable_no_scored_predictions", "multiclass_brier_score": None, "bins": None,
        },
        "claim_boundary": "Metrics describe agreement with the specified independent reference measure; they do not alone establish external validity or mastery.",
    }


def cohen_kappa(rater_a: Sequence[str | None], rater_b: Sequence[str | None]) -> dict[str, Any]:
    """Compute unweighted Cohen's kappa for paired categorical ratings."""
    if len(rater_a) != len(rater_b):
        raise ValueError("paired rater inputs must have equal lengths")
    pairs = [(left, right) for left, right in zip(rater_a, rater_b) if left is not None and right is not None]
    labels = sorted({label for pair in pairs for label in pair})
    count = len(pairs)
    if not count:
        return {"status": "not_computable_no_complete_pairs", "paired_count": 0, "observed_agreement": None, "expected_agreement": None, "kappa": None}
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    observed = sum(left == right for left, right in pairs) / count
    expected = sum(left_counts[label] * right_counts[label] for label in labels) / (count * count)
    return {
        "status": "computed" if expected < 1 else "undefined_perfect_marginal_agreement",
        "paired_count": count,
        "excluded_incomplete_pairs": len(rater_a) - count,
        "observed_agreement": observed,
        "expected_agreement": expected,
        "kappa": (observed - expected) / (1 - expected) if expected < 1 else None,
        "labels": labels,
    }
