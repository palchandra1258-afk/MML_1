from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

from sqlalchemy import select

from mcp_ri.api.azure_openai import AzureResult
from mcp_ri.api.errors import APIError
from mcp_ri.api.persistence import StudentGeneratedLesson
from mcp_ri.api.text_generation import GeminiClient, MockTextGenerator


def lesson_payload():
    return {
        "title": "Indian Mountains: An Introduction",
        "introduction": "A structured overview of major mountain systems in India.",
        "estimated_minutes": 25,
        "learning_objectives": [{"objective_id": "mountains-objective-1", "text": "Identify major mountain regions."}],
        "sections": [
            {"section_id": "section-1", "title": "The Himalaya", "required": True,
             "blocks": [{"type": "paragraph", "text": "The Himalaya is a mountain system in northern India."}]},
            {"section_id": "section-2", "title": "Other ranges", "required": True,
             "blocks": [{"type": "worked_example", "prompt": "Compare two regions.", "steps": ["Locate each region.", "Compare their extent."], "result": "They occupy distinct parts of the subcontinent."}]},
            {"section_id": "section-3", "title": "Review", "required": True,
             "blocks": [{"type": "key_point", "text": "Mountain systems vary in location and formation."}]},
        ],
        "questions": [
            {"question_type": "single_choice", "prompt": "Which system lies in northern India?",
             "options": [{"option_id": "a", "text": "The Himalaya"}, {"option_id": "b", "text": "The Western Ghats"}],
             "grading": {"kind": "choice", "correct_option_ids": ["a"]}, "expected_answer": "The Himalaya",
             "explanation": "The Himalaya form the northern mountain system.", "difficulty": "introductory"},
            {"question_type": "single_choice", "prompt": "Which region is in western India?",
             "options": [{"option_id": "a", "text": "Aravalli Range"}, {"option_id": "b", "text": "Eastern Ghats"}],
             "grading": {"kind": "choice", "correct_option_ids": ["a"]}, "expected_answer": "Aravalli Range",
             "explanation": "The Aravalli Range is in western India.", "difficulty": "introductory"},
            {"question_type": "numeric", "prompt": "How many ranges are listed in this sample?",
             "options": [], "grading": {"kind": "numeric", "expected_value": 2, "absolute_tolerance": 0, "relative_tolerance": 0},
             "expected_answer": "2", "explanation": "Two ranges are listed.", "difficulty": "introductory"},
        ],
    }


def test_curated_precedence_dynamic_lesson_persistence_grading_evidence_and_tutor(api, monkeypatch):
    service = api.app.state.learning_service
    azure_calls = []

    def fake_chat(*, system, user, max_tokens):
        azure_calls.append((system, user, max_tokens))
        if "lesson author" in system:
            return AzureResult(json.dumps(lesson_payload()), {"prompt_tokens": 100, "completion_tokens": 300, "total_tokens": 400}, "text-deployment")
        return AzureResult(json.dumps({"answer": "The Himalaya extend along northern India. Think of the range as a connected arc."}),
                           {"prompt_tokens": 40, "completion_tokens": 25, "total_tokens": 65}, "text-deployment")

    monkeypatch.setattr(service.azure, "chat_json", fake_chat)
    curated = api.client.post("/api/v1/studio/lessons/generate", json={
        "request_id": "curated-precedence", "topic": "Introduction to Probability", "subject": "Mathematics", "level": "beginner",
    })
    assert curated.status_code == 200
    assert curated.json()["data"]["lesson"]["content_source"] == "curated_static"
    assert azure_calls == []

    generated = api.client.post("/api/v1/studio/lessons/generate", json={
        "request_id": "indian-mountains-gen", "topic": "Indian Mountains", "subject": "Geography", "level": "beginner",
    })
    assert generated.status_code == 200, generated.text
    result = generated.json()["data"]
    lesson = result["lesson"]
    assert lesson["content_source"] == "azure_generated"
    assert lesson["generation_source"] == "azure_openai"
    assert result["usage"]["total_tokens"] == 400
    lesson_id = lesson["lesson_id"]
    assert api.client.get(f"/api/v1/curriculum/lessons/{lesson_id}").json()["data"] == lesson

    replay = api.client.post("/api/v1/studio/lessons/generate", json={
        "request_id": "indian-mountains-gen", "topic": "Indian Mountains", "subject": "Geography", "level": "beginner",
    })
    assert replay.status_code == 200
    assert replay.json()["data"]["lesson"]["lesson_id"] == lesson_id
    assert len(azure_calls) == 1

    practice = api.client.get(f"/api/v1/curriculum/lessons/{lesson_id}/practice").json()["data"]
    assert len(practice["questions"]) == 3
    assert all("grading" not in question and "expected_answer" not in question for question in practice["questions"])
    study = api.client.post(f"/api/v1/studio/lessons/{lesson_id}/sessions").json()["data"]
    question = practice["questions"][0]
    answer = api.client.post(f"/api/v1/studio/questions/{question['question_id']}/answer", json={
        "submission_id": "mountains-answer", "session_id": study["session_id"], "response": {"option_ids": ["a"]},
    })
    assert answer.status_code == 200, answer.text
    feedback = answer.json()["data"]
    assert feedback["is_correct"] is True
    assert feedback["content_version"] == lesson["content_version"]
    assert feedback["processing"]["evidence"] == "recorded"
    assert feedback["recommendation"]["status"] == "personalized"

    tutor = api.client.post(f"/api/v1/studio/lessons/{lesson_id}/tutor", json={
        "session_id": study["session_id"], "turn_id": "tutor-turn-1", "message": "Explain this in simpler language.",
        "level": "beginner", "section_id": "section-1",
    })
    assert tutor.status_code == 200, tutor.text
    assert tutor.json()["data"]["source"] == "azure_supplementary_explanation"
    assert len(azure_calls) == 2
    history = api.client.get(f"/api/v1/studio/lessons/{lesson_id}/tutor/history", params={"session_id": study["session_id"]})
    assert [item["role"] for item in history.json()["data"]] == ["user", "assistant"]


def test_mock_provider_generation_persists_and_retrieves_explicit_test_content(api, monkeypatch):
    service = api.app.state.learning_service
    monkeypatch.setattr(service, "generator", MockTextGenerator())
    monkeypatch.setattr(service, "provider", SimpleNamespace(name="mock"))
    response = api.client.post("/api/v1/studio/lessons/generate", json={
        "request_id": "mock-provider-generation", "topic": "A topic not in the catalog",
        "subject": "Geography", "level": "beginner",
    })
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    lesson = result["lesson"]
    assert lesson["generation_source"] == "mock"
    assert lesson["content_source"] == "mock_generated"
    assert "not AI generated" in result["notice"]
    assert api.client.get(f"/api/v1/curriculum/lessons/{lesson['lesson_id']}").json()["data"] == lesson


def test_gemini_status_is_configuration_only_and_does_not_expose_api_key(api, monkeypatch):
    configured = replace(api.settings, ai_provider="gemini", gemini_api_key="private-test-value",
                         gemini_model="configured-model")
    service = api.app.state.learning_service
    monkeypatch.setattr(service, "generator", GeminiClient(configured))
    response = api.client.get("/api/v1/studio/ai/status")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["provider"] == "gemini"
    assert data["generation_available"] is True
    assert data["model"] == "configured-model"
    assert "private-test-value" not in response.text


def test_missing_azure_configuration_returns_explicit_missing_names(api):
    def should_not_open_connection(*_args, **_kwargs):
        raise AssertionError("Unavailable provider must not be invoked")

    service = api.app.state.learning_service
    # The fixture intentionally has no Azure credentials; fail locally before any provider I/O.
    service.azure._opener = should_not_open_connection
    response = api.client.post("/api/v1/studio/lessons/generate", json={
        "request_id": "ai-missing-config", "topic": "Geography", "subject": "Geography", "level": "beginner",
    })
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "AI_NOT_CONFIGURED"
    assert "AZURE_OPENAI_ENDPOINT" in error["message"]
    assert "AZURE_OPENAI_API_KEY" in error["message"]

    status_response = api.client.get("/api/v1/studio/ai/status")
    assert status_response.status_code == 200
    status = status_response.json()["data"]
    assert status["configured"] is False
    assert status["generation_available"] is False
    assert "AZURE_OPENAI_API_KEY" in status["availability_reason"]


def test_invalid_provider_lesson_is_rejected_without_persistence(api, monkeypatch):
    service = api.app.state.learning_service
    calls = []

    def invalid_response(**_kwargs):
        calls.append(1)
        return AzureResult("not valid json", None, "text-deployment")

    monkeypatch.setattr(service.azure, "chat_json", invalid_response)
    response = api.client.post("/api/v1/studio/lessons/generate", json={
        "request_id": "invalid-geography-draft", "topic": "Geography", "subject": "Geography", "level": "beginner",
    })
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_CONTENT_INVALID"
    assert calls == [1]
    with api.app.state.database.session_factory() as session:
        assert session.scalars(select(StudentGeneratedLesson)).all() == []


def test_provider_timeout_is_returned_safely_without_persistence(api, monkeypatch):
    service = api.app.state.learning_service
    calls = []

    def timeout(**_kwargs):
        calls.append(1)
        raise APIError(504, "AI_TIMEOUT", "Azure OpenAI did not respond before the configured timeout.")

    monkeypatch.setattr(service.azure, "chat_json", timeout)
    response = api.client.post("/api/v1/studio/lessons/generate", json={
        "request_id": "timeout-geography-draft", "topic": "Geography", "subject": "Geography", "level": "beginner",
    })
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "AI_TIMEOUT"
    assert "secret" not in response.text
    assert calls == [1]
    with api.app.state.database.session_factory() as session:
        assert session.scalars(select(StudentGeneratedLesson)).all() == []


def test_generation_request_validates_topic_and_learning_level_before_provider(api, monkeypatch):
    service = api.app.state.learning_service

    def should_not_call_provider(**_kwargs):
        raise AssertionError("Invalid request must not invoke the provider")

    monkeypatch.setattr(service.azure, "chat_json", should_not_call_provider)
    too_short = api.client.post("/api/v1/studio/lessons/generate", json={
        "request_id": "short-topic", "topic": "G", "subject": "Geography", "level": "beginner",
    })
    invalid_level = api.client.post("/api/v1/studio/lessons/generate", json={
        "request_id": "invalid-level", "topic": "Geography", "subject": "Geography", "level": "expert",
    })
    assert too_short.status_code == 422
    assert invalid_level.status_code == 422
    assert too_short.json()["error"]["code"] == "INVALID_REQUEST"
    assert invalid_level.json()["error"]["code"] == "INVALID_REQUEST"

