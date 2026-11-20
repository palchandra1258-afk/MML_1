import pytest

from mcp_ri.learning.independent_evaluation import cohen_kappa, evaluate_independent_predictions


def row(pid, prediction, reference, **kwargs):
    return {
        "pseudonymous_learner_id": pid,
        "partition": "evaluation",
        "prediction": prediction,
        "reference_label": reference,
        "reference_is_independent": True,
        **kwargs,
    }


def test_no_independent_labels_means_no_predictive_metrics():
    result = evaluate_independent_predictions([
        row("p_learner01", "known", "known", reference_is_independent=False),
        row("p_learner02", "known", None),
    ])
    assert result["status"] == "not_computable_no_independent_reference_labels"
    assert result["classification_metrics"] is None
    assert result["excluded_non_independent_reference_count"] == 1


def test_classification_metrics_abstention_and_privacy_safe_aggregates():
    records = [
        row("p_learner01", "known", "known"),
        row("p_learner02", "known", "not_yet_demonstrated"),
        row("p_learner03", "abstain", "known"),
    ]
    result = evaluate_independent_predictions(records)
    assert result["status"] == "computed"
    assert result["classification_metrics"]["sample_count"] == 2
    assert result["classification_metrics"]["accuracy"] == 0.5
    assert result["abstention_count"] == 1
    assert result["evaluation_coverage"] == pytest.approx(2 / 3)
    assert "p_learner01" not in repr(result)


def test_cross_partition_learner_leakage_is_rejected():
    records = [row("p_learner01", "known", "known")]
    second = row("p_learner01", "known", "known")
    second["partition"] = "development"
    with pytest.raises(ValueError, match="more than one partition"):
        evaluate_independent_predictions(records + [second])


def test_calibration_requires_valid_probability_estimates():
    records = [
        row("p_learner01", "known", "known", probabilities={"known": 0.8, "not_yet_demonstrated": 0.2}),
        row("p_learner02", "not_yet_demonstrated", "not_yet_demonstrated", probabilities={"known": 0.1, "not_yet_demonstrated": 0.9}),
    ]
    result = evaluate_independent_predictions(records, calibration_bin_edges=[0, 0.5, 1])
    assert result["calibration"]["status"] == "computed_from_independent_reference_labels"
    assert result["calibration"]["multiclass_brier_score"] == pytest.approx(0.05)
    assert [item["count"] for item in result["calibration"]["bins"]] == [0, 2]
    records[0]["probabilities"] = {"known": 0.8, "not_yet_demonstrated": 0.3}
    with pytest.raises(ValueError, match="sum to 1"):
        evaluate_independent_predictions(records)


def test_cohen_kappa_reports_agreement_and_missing_pairs():
    result = cohen_kappa(["yes", "no", None, "yes"], ["yes", "no", "yes", "no"])
    assert result["paired_count"] == 3
    assert result["excluded_incomplete_pairs"] == 1
    assert result["observed_agreement"] == pytest.approx(2 / 3)
