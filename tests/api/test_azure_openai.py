from __future__ import annotations

import io
import json

import pytest
from urllib.error import HTTPError

from mcp_ri.api.azure_openai import AzureOpenAIClient, AzureResult
from mcp_ri.api.errors import APIError
from mcp_ri.api.settings import APISettings


def settings(**values):
    defaults = dict(
        database_url="sqlite:///:memory:", cors_origins=(), phase9_states_path="/tmp/p9",
        phase10_evidence_path="/tmp/p10", phase10_groups_path="/tmp/p10g",
        phase11_states_path="/tmp/p11", phase12_plans_path="/tmp/p12",
    )
    defaults.update(values)
    return APISettings(**defaults)


class Response:
    def __init__(self, document):
        self.document = document

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit):
        return json.dumps(self.document).encode()


def test_azure_client_reports_exact_missing_names_without_values():
    client = AzureOpenAIClient(settings())
    status = client.diagnostics()
    assert status["configured"] is False
    assert status["generation_available"] is False
    assert status["missing_configuration"] == [
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_API_VERSION",
    ]
    assert "never-log-this" not in json.dumps(status)
    assert "https://example" not in json.dumps(status)


def test_azure_client_uses_key_header_and_structured_json_and_returns_usage():
    seen = {}

    def opener(request, timeout):
        seen["key"] = request.get_header("Api-key")
        seen["timeout"] = timeout
        seen["body"] = json.loads(request.data)
        return Response({"model": "deployment", "choices": [{"message": {"content": json.dumps({"answer": "ok"})}}],
                         "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}})

    settings_value = settings(
        azure_openai_endpoint="https://example.openai.azure.com", azure_openai_api_key="never-log-this",
        azure_openai_deployment_name="text-model", azure_openai_api_version="2024-10-21",
        azure_openai_timeout_seconds=4.5,
    )
    result = AzureOpenAIClient(settings_value, opener=opener).chat_json(system="sys", user="user")
    assert result == AzureResult('{"answer": "ok"}', {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}, "deployment")
    assert seen["key"] == "never-log-this"
    assert seen["timeout"] == 4.5
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["max_completion_tokens"] == 7000


def test_realtime_deployment_is_rejected_before_any_provider_request():
    calls = []

    def opener(*_args, **_kwargs):
        calls.append(1)
        raise AssertionError("Realtime deployment must not receive a chat-completions request")

    client = AzureOpenAIClient(settings(
        azure_openai_endpoint="https://example.openai.azure.com", azure_openai_api_key="secret",
        azure_openai_deployment_name="gpt-realtime", azure_openai_api_version="2025-04-01-preview",
    ), opener=opener)
    status = client.diagnostics()
    assert status["configured"] is True
    assert status["generation_available"] is False
    assert "does not support lesson text generation" in status["availability_reason"]
    with pytest.raises(APIError) as exc:
        client.chat_json(system="sys", user="lesson request")
    assert exc.value.code == "AI_CONFIGURATION_INVALID"
    assert calls == []


def test_azure_client_bounds_retry_and_returns_safe_rate_limit_error():
    sleeps = []
    calls = []

    def opener(_request, **_kwargs):
        calls.append(1)
        raise HTTPError("https://redacted", 429, "rate", {"Retry-After": "0"}, io.BytesIO(b"secret body"))

    client = AzureOpenAIClient(settings(
        azure_openai_endpoint="https://example.openai.azure.com", azure_openai_api_key="secret",
        azure_openai_deployment_name="deployment", azure_openai_api_version="v1",
        azure_openai_max_retries=2,
    ), opener=opener, sleeper=sleeps.append)
    with pytest.raises(APIError) as exc:
        client.chat_json(system="sys", user="prompt")
    assert exc.value.code == "AI_RATE_LIMITED"
    assert len(calls) == 3
    assert "secret" not in str(exc.value)


@pytest.mark.parametrize(("status", "code"), [(401, "AI_AUTHENTICATION_FAILED"), (403, "AI_AUTHENTICATION_FAILED")])
def test_azure_authentication_errors_are_safe(status, code):
    def opener(_request, **_kwargs):
        raise HTTPError("https://redacted", status, "auth", {}, io.BytesIO(b"secret"))

    client = AzureOpenAIClient(settings(
        azure_openai_endpoint="https://example.openai.azure.com", azure_openai_api_key="secret",
        azure_openai_deployment_name="deployment", azure_openai_api_version="v1", azure_openai_max_retries=0,
    ), opener=opener)
    with pytest.raises(APIError) as exc:
        client.chat_json(system="sys", user="prompt")
    assert exc.value.code == code
    assert "secret" not in str(exc.value)


def test_azure_timeout_retries_are_bounded_and_return_safe_error():
    calls = []

    def opener(_request, **_kwargs):
        calls.append(1)
        raise TimeoutError("secret endpoint")

    client = AzureOpenAIClient(settings(
        azure_openai_endpoint="https://example.openai.azure.com", azure_openai_api_key="secret",
        azure_openai_deployment_name="deployment", azure_openai_api_version="v1", azure_openai_max_retries=1,
    ), opener=opener, sleeper=lambda _delay: None)
    with pytest.raises(APIError) as exc:
        client.chat_json(system="sys", user="prompt")
    assert exc.value.code == "AI_TIMEOUT"
    assert len(calls) == 2
