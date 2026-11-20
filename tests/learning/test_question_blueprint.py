from copy import deepcopy

import pytest

from mcp_ri.api.learning_service import curriculum
from mcp_ri.learning.assessment_validation import build_question_blueprint, validate_question_blueprint


def _catalog():
    return curriculum().model_dump(mode="json")


def test_blueprint_covers_catalog_exactly_and_marks_unreviewed_fields():
    catalog = _catalog()
    blueprint = build_question_blueprint(catalog)
    assert [row["question_id"] for row in blueprint["questions"]] == [
        row["question_id"] for row in catalog["questions"]
    ]
    assert len({row["question_id"] for row in blueprint["questions"]}) == 15
    assert all(row["human_review"]["status"] == "pending_review" for row in blueprint["questions"])
    assert all(row["human_review"]["reviewer_id"] is None for row in blueprint["questions"])
    assert all(row["intended_cognitive_demand"]["value"] == "unknown" for row in blueprint["questions"])
    assert all(row["difficulty"]["calibration_status"] == "unvalidated_catalog_label" for row in blueprint["questions"])
    assert build_question_blueprint(catalog) == blueprint


def test_missing_catalog_difficulty_remains_explicitly_unknown():
    catalog = _catalog()
    catalog["questions"][0]["difficulty"] = None
    item = build_question_blueprint(catalog)["questions"][0]
    assert item["difficulty"] == {"catalog_label": "unknown", "calibration_status": "unknown"}


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "review_status", "demand", "objective"])
def test_blueprint_validation_rejects_unsupported_or_tampered_inventory(mutation):
    catalog = _catalog()
    blueprint = build_question_blueprint(catalog)
    if mutation == "duplicate":
        blueprint["questions"].append(deepcopy(blueprint["questions"][0]))
    elif mutation == "missing":
        blueprint["questions"].pop()
    elif mutation == "review_status":
        blueprint["questions"][0]["human_review"]["status"] = "approved_by_ai"
    elif mutation == "demand":
        blueprint["questions"][0]["intended_cognitive_demand"]["value"] = "expert_level"
    else:
        blueprint["questions"][0]["learning_objective_id"] = "invented-objective"
    with pytest.raises(ValueError):
        validate_question_blueprint(blueprint, catalog)
