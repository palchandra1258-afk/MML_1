from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from mcp_ri.api.errors import APIError
from mcp_ri.api.settings import APISettings
from mcp_ri.api.text_generation import GeminiClient, MockTextGenerator, select_text_generator


def settings(**changes):
    values = dict(database_url="sqlite://", cors_origins=(), phase9_states_path=None,
                  phase10_evidence_path=None, phase10_groups_path=None,
                  phase11_states_path=None, phase12_plans_path=None)
    values.update(changes)
    return APISettings(**values)


def test_provider_selection_keeps_azure_and_supports_gemini_and_mock():
    assert select_text_generator(settings()).name == "azure"
    assert select_text_generator(settings(ai_provider="gemini")).name == "gemini"
    assert select_text_generator(settings(ai_provider="mock")).name == "mock"
    with pytest.raises(APIError) as error:
        select_text_generator(settings(ai_provider="unknown"))
    assert error.value.code == "AI_CONFIGURATION_INVALID"


def test_gemini_requires_key_and_model_without_azure_configuration():
    client = GeminiClient(settings(ai_provider="gemini"))
    assert client.diagnostics()["missing_configuration"] == ["GEMINI_API_KEY", "GEMINI_MODEL"]
    with pytest.raises(APIError) as error:
        client.chat_json(system="sys", user="input")
    assert error.value.code == "AI_NOT_CONFIGURED"
    configured = GeminiClient(settings(ai_provider="gemini", gemini_api_key="secret-value", gemini_model="chosen-model"))
    assert configured.diagnostics()["generation_available"] is True


def test_missing_google_genai_distribution_has_specific_dependency_error(monkeypatch):
    def missing_distribution(_name):
        raise __import__("importlib.metadata").metadata.PackageNotFoundError
    monkeypatch.setattr("mcp_ri.api.text_generation.metadata.version", missing_distribution)
    client = GeminiClient(settings(gemini_api_key="test", gemini_model="model"))
    with pytest.raises(APIError) as error:
        client.chat_json(system="s", user="u")
    assert error.value.code == "AI_DEPENDENCY_MISSING"


def test_unsupported_google_genai_major_version_is_reported(monkeypatch):
    monkeypatch.setattr("mcp_ri.api.text_generation.metadata.version", lambda _name: "3.0.0")
    client = GeminiClient(settings(gemini_api_key="test", gemini_model="model"))
    with pytest.raises(APIError) as error:
        client.chat_json(system="s", user="u")
    assert error.value.code == "AI_DEPENDENCY_INCOMPATIBLE"


def test_nested_sdk_import_failure_is_not_misreported_as_missing_sdk(monkeypatch):
    import builtins
    original_import = builtins.__import__
    def broken_nested_import(name, *args, **kwargs):
        if name == "google.genai":
            raise ModuleNotFoundError("missing transitive module", name="google.auth")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", broken_nested_import)
    client = GeminiClient(settings(gemini_api_key="test", gemini_model="model"))
    with pytest.raises(APIError) as error:
        client.chat_json(system="s", user="u")
    assert error.value.code == "AI_DEPENDENCY_ERROR"
    assert "google.auth" in error.value.message


def test_gemini_adapter_uses_mocked_official_sdk_and_maps_usage(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))
            self.models = self
        def generate_content(self, **kwargs):
            calls.append(("generate", kwargs))
            return SimpleNamespace(text='{"ok":true}', usage_metadata=SimpleNamespace(
                prompt_token_count=12, candidates_token_count=7, total_token_count=19))
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    genai.Client = Client
    types = SimpleNamespace(HttpOptions=lambda **kw: kw, HttpRetryOptions=lambda **kw: kw, GenerateContentConfig=lambda **kw: kw)
    genai.types = types
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", types)
    adapter = GeminiClient(settings(gemini_api_key="test-only", gemini_model="selected-model"))
    result = adapter.chat_json(system="system", user="user", max_tokens=300)
    assert json.loads(result.content) == {"ok": True}
    assert result.usage == {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19}
    assert calls[-1][1]["model"] == "selected-model"
    assert calls[-1][1]["config"]["response_mime_type"] == "application/json"


def test_gemini_timeout_and_rate_limit_are_safe(monkeypatch):
    class Client:
        def __init__(self, **kwargs): self.models = self
        def generate_content(self, **kwargs): raise TimeoutError("secret must not leak")
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    genai.Client = Client
    types = SimpleNamespace(HttpOptions=lambda **kw: kw, HttpRetryOptions=lambda **kw: kw, GenerateContentConfig=lambda **kw: kw)
    genai.types = types
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", types)
    with pytest.raises(APIError) as error:
        GeminiClient(settings(gemini_api_key="test", gemini_model="model")).chat_json(system="s", user="u")
    assert error.value.code == "AI_TIMEOUT"
    assert "secret" not in error.value.message


@pytest.mark.parametrize(("provider_code", "expected_code"), [
    (401, "AI_AUTHENTICATION_FAILED"), (403, "AI_AUTHENTICATION_FAILED"),
    (429, "AI_RATE_LIMITED"), (404, "AI_MODEL_UNAVAILABLE"), (503, "AI_PROVIDER_UNAVAILABLE"),
])
def test_gemini_provider_errors_are_mapped_without_raw_details(monkeypatch, provider_code, expected_code):
    class ProviderFailure(Exception):
        code = provider_code
    class Client:
        def __init__(self, **kwargs): self.models = self
        def generate_content(self, **kwargs): raise ProviderFailure("private detail")
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    genai.Client = Client
    types = SimpleNamespace(HttpOptions=lambda **kw: kw, HttpRetryOptions=lambda **kw: kw, GenerateContentConfig=lambda **kw: kw)
    genai.types = types
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", types)
    adapter = GeminiClient(settings(gemini_api_key="private-test", gemini_model="model"))
    with pytest.raises(APIError) as error:
        adapter.chat_json(system="s", user="u")
    assert error.value.code == expected_code
    assert "private detail" not in error.value.message


def test_gemini_empty_response_is_rejected(monkeypatch):
    class Client:
        def __init__(self, **kwargs): self.models = self
        def generate_content(self, **kwargs): return SimpleNamespace(text=" ", usage_metadata=None)
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    genai.Client = Client
    types = SimpleNamespace(HttpOptions=lambda **kw: kw, HttpRetryOptions=lambda **kw: kw, GenerateContentConfig=lambda **kw: kw)
    genai.types = types
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", types)
    with pytest.raises(APIError) as error:
        GeminiClient(settings(gemini_api_key="test", gemini_model="model")).chat_json(system="s", user="u")
    assert error.value.code == "AI_INVALID_RESPONSE"


def test_gemini_network_failure_is_mapped_without_raw_details(monkeypatch):
    class ConnectError(Exception): pass
    class Client:
        def __init__(self, **kwargs): self.models = self
        def generate_content(self, **kwargs): raise ConnectError("private transport details")
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    genai.Client = Client
    types = SimpleNamespace(HttpOptions=lambda **kw: kw, HttpRetryOptions=lambda **kw: kw, GenerateContentConfig=lambda **kw: kw)
    genai.types = types
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", types)
    with pytest.raises(APIError) as error:
        GeminiClient(settings(gemini_api_key="test", gemini_model="model")).chat_json(system="s", user="u")
    assert error.value.code == "AI_NETWORK_ERROR"
    assert "private transport" not in error.value.message


def test_mock_output_is_marked_test_content():
    result = MockTextGenerator().chat_json(system="lesson author", user="{}")
    draft = json.loads(result.content)
    assert "Mock" in draft["title"]
    assert result.usage is None
