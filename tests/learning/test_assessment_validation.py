from __future__ import annotations

from copy import deepcopy
import sqlite3

from mcp_ri.api.learning_service import curriculum
from mcp_ri.learning.assessment_validation import (
    analyze_student_studio_attempts,
    audit_question_quality,
    read_student_studio_attempts_read_only,
)


def _question_quality():
    return audit_question_quality(curriculum().model_dump(mode="json"))


def _attempt(question_id: str, correct: bool, *, topic="introduction-to-probability", profile="local", timestamp="2026-11-20T00:00:00+00:00", source="mcp-ri-student-studio", evidence_status="missing"):
    return {
        "profile_id": profile,
        "topic_id": topic,
        "question_id": question_id,
        "is_correct": correct,
        "event_timestamp": timestamp,
        "source_dataset": source,
        "evidence_status": evidence_status,
    }


def test_current_catalog_structural_audit_finds_supported_metadata_and_coverage():
    report = _question_quality()
    assert report["question_count"] == 15
    assert report["topic_count"] == 7
    assert report["duplicate_question_ids"] == []
    assert report["structurally_complete_question_count"] == 15
    assert report["questions_with_structural_issues"] == []
    assert report["difficulty_distribution"] == {"introductory": 15}
    assert report["question_type_distribution"] == {
        "multiple_choice": 7, "numeric": 1, "single_choice": 7,
    }
    expected_value = next(item for item in report["topics"] if item["topic_id"] == "expected-value")
    assert expected_value["question_count"] == 3
    assert expected_value["distinct_objective_count"] == 2
    assert expected_value["coverage_status"] == "repeated_objective_coverage"
    assert "expected-value-objective-1" in expected_value["objectives_with_multiple_questions"]
    assert report["questions_requiring_manual_review"] == [item["question_id"] for item in report["questions"]]


def test_question_audit_finds_missing_metadata_bad_association_and_duplicate_ids():
    catalog = deepcopy(curriculum().model_dump(mode="json"))
    question = catalog["questions"][0]
    question["difficulty"] = None
    question["objective_id"] = "not-an-objective"
    question["topic_id"] = "conditional-probability"
    catalog["questions"].append(deepcopy(question))
    report = audit_question_quality(catalog)
    assert question["question_id"] in report["duplicate_question_ids"]
    duplicate_records = [item for item in report["questions"] if item["question_id"] == question["question_id"]]
    assert all("duplicate_question_id" in item["findings"] for item in duplicate_records)
    assert all("missing_difficulty_metadata" in item["findings"] for item in duplicate_records)
    assert all("unknown_objective_association" in item["findings"] for item in duplicate_records)
    assert all("lesson_topic_mismatch" in item["findings"] for item in duplicate_records)
    assert question["question_id"] not in next(
        item for item in report["topics"] if item["topic_id"] == question["topic_id"]
    )["structurally_usable_question_ids"]


def test_question_audit_reports_topic_with_insufficient_question_coverage():
    catalog = deepcopy(curriculum().model_dump(mode="json"))
    catalog["questions"] = [q for q in catalog["questions"] if q["topic_id"] != "bayes-theorem"]
    report = audit_question_quality(catalog)
    topic = next(item for item in report["topics"] if item["topic_id"] == "bayes-theorem")
    assert topic["coverage_status"] == "no_linked_questions"
    assert topic["question_count"] == 0


def test_threshold_sensitivity_counts_distinct_questions_not_repeats():
    attempts = [
        _attempt("introduction-to-probability-q1", True),
        _attempt("introduction-to-probability-q1", True, timestamp="2026-11-20T00:01:00+00:00"),
    ]
    report = analyze_student_studio_attempts(question_quality=_question_quality(), attempts=attempts, thresholds=(1, 2, 3))
    topic = report["topic_statistics"][0]
    assert topic["attempt_count"] == 2
    assert topic["distinct_question_count"] == 1
    assert topic["repeat_attempt_count"] == 1
    by_threshold = {item["minimum_distinct_questions"]: item for item in report["threshold_sensitivity"]}
    assert by_threshold[1]["classification_counts"]["supported_response_pattern"] == 1
    assert by_threshold[2]["classification_counts"]["insufficient_evidence"] == 7
    assert by_threshold[3]["classification_counts"]["insufficient_evidence"] == 7


def test_repeated_question_conflict_is_separated_from_distinct_question_coverage():
    attempts = [
        _attempt("expected-value-q1", True, topic="expected-value"),
        _attempt("expected-value-q1", False, topic="expected-value", timestamp="2026-11-20T00:01:00+00:00"),
        _attempt("expected-value-q2", True, topic="expected-value", timestamp="2026-11-20T00:02:00+00:00"),
        _attempt("expected-value-q3", True, topic="expected-value", timestamp="2026-11-20T00:03:00+00:00"),
    ]
    report = analyze_student_studio_attempts(question_quality=_question_quality(), attempts=attempts)
    topic = next(item for item in report["topic_statistics"] if item["topic_id"] == "expected-value")
    assert topic["attempt_count"] == 4
    assert topic["distinct_question_count"] == 3
    assert topic["repeat_attempt_count"] == 1
    assert topic["questions_with_outcome_changes"] == 1
    assert topic["event_time_span_seconds"] == 180
    assert report["threshold_sensitivity"][1]["classification_counts"]["conflicting_evidence"] == 1
    assert report["recency_analysis"]["time_decay_or_expiration_applied"] is False


def test_one_two_three_and_five_question_threshold_scenarios():
    attempts = [
        _attempt("expected-value-q1", True, topic="expected-value"),
        _attempt("expected-value-q2", True, topic="expected-value"),
        _attempt("expected-value-q3", True, topic="expected-value"),
    ]
    report = analyze_student_studio_attempts(question_quality=_question_quality(), attempts=attempts)
    threshold = {item["minimum_distinct_questions"]: item for item in report["threshold_sensitivity"]}
    for value in (1, 2, 3):
        assert threshold[value]["classification_counts"]["supported_response_pattern"] == 1
    assert threshold[5]["classification_counts"]["insufficient_evidence"] == 7


def test_threshold_analysis_separates_profiles_and_excludes_research_dataset():
    attempts = [
        _attempt("introduction-to-probability-q1", True, profile="learner-a"),
        _attempt("introduction-to-probability-q2", True, profile="learner-b"),
        _attempt("introduction-to-probability-q1", False, profile="ednet-learner", source="ednet"),
    ]
    report = analyze_student_studio_attempts(question_quality=_question_quality(), attempts=attempts)
    assert report["data_source"] == "student_studio_tables_only"
    assert report["population"]["unique_profile_count"] == 2
    assert report["population"]["excluded_non_student_studio_count"] == 1
    assert report["population"]["correct_response_count"] == 2


def test_invalid_canonical_provenance_is_excluded_from_sensitivity_analysis():
    report = analyze_student_studio_attempts(
        question_quality=_question_quality(),
        attempts=[_attempt("introduction-to-probability-q1", True, evidence_status="invalid")],
    )
    assert report["population"]["excluded_invalid_provenance_count"] == 1
    assert report["population"]["catalog_mapped_attempt_count"] == 0
    assert report["evidence_provenance"]["canonical_evidence_invalid_count"] == 1


def test_empty_data_reports_missingness_without_claiming_reliability():
    report = analyze_student_studio_attempts(question_quality=_question_quality(), attempts=[])
    assert report["status"] == "no_observations"
    assert all(topic["unobserved"] for topic in report["topic_statistics"])
    assert report["validation_claims"]["internal_consistency_or_reliability"] == "not_established"
    assert report["validation_claims"]["predictive_performance"] == "not_evaluated_no_independent_targets"


def test_validation_output_is_reproducible_and_contains_no_identifiers():
    quality = _question_quality()
    data = [_attempt("introduction-to-probability-q1", True)]
    first = analyze_student_studio_attempts(question_quality=quality, attempts=data)
    second = analyze_student_studio_attempts(question_quality=quality, attempts=data)
    assert first == second
    assert "learner-a" not in repr(first)
    assert "question_id" in repr(first["topic_statistics"][0]["question_statistics"])
    assert "attempt_id" not in repr(first)


def test_sqlite_reader_uses_student_studio_tables_read_only_and_ignores_ednet(tmp_path):
    path = tmp_path / "validation.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE studio_learning_attempts (attempt_id TEXT, profile_id TEXT, topic_id TEXT, question_id TEXT, is_correct INTEGER, event_timestamp TEXT, event_sequence INTEGER);"
        "CREATE TABLE studio_evidence_records (evidence_id TEXT, profile_id TEXT, source_event_id TEXT, evidence_record TEXT);"
        "CREATE TABLE ednet_interactions (learner_id TEXT, question_id TEXT);"
        "INSERT INTO studio_learning_attempts VALUES ('attempt-1', 'demo', 'introduction-to-probability', 'introduction-to-probability-q1', 1, '2026-11-20T00:00:00+00:00', 1);"
        "INSERT INTO studio_evidence_records VALUES ('evidence-1', 'demo', 'attempt-1', '{\"provenance\":{\"source_dataset\":\"mcp-ri-student-studio\",\"source_record_id\":\"attempt-1\"},\"content\":{\"topic_id\":\"introduction-to-probability\",\"question_id\":\"introduction-to-probability-q1\"}}');"
        "INSERT INTO ednet_interactions VALUES ('research-user', 'q1');"
    )
    connection.close()
    modified_before = path.stat().st_mtime_ns
    loaded = read_student_studio_attempts_read_only(path)
    modified_after = path.stat().st_mtime_ns
    assert loaded["available"] is True
    assert len(loaded["attempts"]) == 1
    assert loaded["attempts"][0]["source_dataset"] == "mcp-ri-student-studio"
    assert loaded["attempts"][0]["evidence_status"] == "valid"
    assert modified_before == modified_after
