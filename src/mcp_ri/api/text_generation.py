"""Backend-only provider selection for structured Student Studio generation."""

from __future__ import annotations

import json
from importlib import metadata
from dataclasses import dataclass
from typing import Any, Protocol

from .azure_openai import AzureOpenAIClient
from .errors import APIError
from .settings import APISettings


def _load_gemini_sdk():
    try:
        version = metadata.version("google-genai")
    except metadata.PackageNotFoundError:
        raise APIError(503, "AI_DEPENDENCY_MISSING", "Install the Gemini SDK with .venv-api/bin/python -m pip install -r requirements-api.txt.") from None
    try:
        major = int(version.split(".", 1)[0])
    except ValueError:
        major = 0
    if not 1 <= major < 3:
        raise APIError(503, "AI_DEPENDENCY_INCOMPATIBLE", "The installed google-genai version is outside the supported range; install requirements-api.txt in .venv-api.")
    try:
        from google import genai
        from google.genai import types
    except ModuleNotFoundError as exc:
        missing_module = exc.name or "an SDK module"
        if missing_module in {"google", "google.genai"}:
            raise APIError(503, "AI_DEPENDENCY_MISSING", "The google-genai package is declared but its SDK module is unavailable; reinstall requirements-api.txt in .venv-api.") from None
        raise APIError(503, "AI_DEPENDENCY_ERROR", f"The Gemini SDK could not import a required dependency ({missing_module}). Reinstall requirements-api.txt in .venv-api.") from None
    except ImportError:
        raise APIError(503, "AI_DEPENDENCY_ERROR", "The Gemini SDK could not be imported; reinstall requirements-api.txt in .venv-api.") from None
    return genai, types


@dataclass(frozen=True)
class TextGenerationResult:
    content: str
    usage: dict[str, int] | None
    model: str | None
    status_code: int = 200


class JSONTextGenerator(Protocol):
    def chat_json(self, *, system: str, user: str, max_tokens: int = 7000) -> TextGenerationResult: ...
    def diagnostics(self) -> dict[str, Any]: ...


class GeminiClient:
    """Google Gen AI adapter. SDK import is lazy to keep Azure/mock installations usable."""

    def __init__(self, settings: APISettings):
        self.settings = settings
        self._client = None

    def diagnostics(self) -> dict[str, Any]:
        missing = [name for name, value in (
            ("GEMINI_API_KEY", self.settings.gemini_api_key),
            ("GEMINI_MODEL", self.settings.gemini_model),
        ) if not value]
        dependency_error = None
        if not missing:
            try:
                _load_gemini_sdk()
            except APIError as exc:
                dependency_error = exc.message
        available = not missing and dependency_error is None
        return {
            "provider": "gemini", "configured": not missing,
            "generation_available": available,
            "availability_reason": ("Required Gemini settings are missing: " + ", ".join(missing)) if missing else dependency_error,
            "missing_configuration": missing, "deployment_name": None, "model": self.settings.gemini_model or None,
            "timeout_seconds": min(120.0, max(1.0, self.settings.gemini_timeout_seconds)),
            "max_retries": 0, "voice_deployment_used": False,
        }

    def chat_json(self, *, system: str, user: str, max_tokens: int = 7000) -> TextGenerationResult:
        missing = [name for name, value in (
            ("GEMINI_API_KEY", self.settings.gemini_api_key), ("GEMINI_MODEL", self.settings.gemini_model),
        ) if not value]
        if missing:
            raise APIError(503, "AI_NOT_CONFIGURED", "Gemini is not configured. Set: " + ", ".join(missing))
        genai, types = _load_gemini_sdk()
        try:
            if self._client is None:
                timeout_ms = int(min(120.0, max(1.0, self.settings.gemini_timeout_seconds)) * 1000)
                self._client = genai.Client(
                    api_key=self.settings.gemini_api_key,
                    http_options=types.HttpOptions(
                        timeout=timeout_ms,
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                )
            response = self._client.models.generate_content(
                model=self.settings.gemini_model,
                contents=f"{system}\n\n{user}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", max_output_tokens=max_tokens,
                ),
            )
            content = response.text
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty generated response")
            meta = getattr(response, "usage_metadata", None)
            usage = None
            if meta is not None:
                fields = {
                    "prompt_tokens": getattr(meta, "prompt_token_count", None),
                    "completion_tokens": getattr(meta, "candidates_token_count", None),
                    "total_tokens": getattr(meta, "total_token_count", None),
                }
                usage = {key: int(value) for key, value in fields.items() if isinstance(value, int)} or None
            return TextGenerationResult(content=content, usage=usage, model=self.settings.gemini_model)
        except TimeoutError:
            raise APIError(504, "AI_TIMEOUT", "Gemini did not respond before the configured timeout.") from None
        except ValueError:
            raise APIError(502, "AI_INVALID_RESPONSE", "Gemini returned an invalid structured response.") from None
        except Exception as exc:
            # Provider exception details can contain request metadata. Only map safe status codes.
            exception_name = type(exc).__name__
            if exception_name in {"TimeoutException", "ReadTimeout", "ConnectTimeout", "WriteTimeout", "PoolTimeout"}:
                raise APIError(504, "AI_TIMEOUT", "Gemini did not respond before the configured timeout.") from None
            if exception_name in {"ConnectError", "NetworkError", "RemoteProtocolError", "ConnectionError"}:
                raise APIError(502, "AI_NETWORK_ERROR", "The backend could not connect to Gemini.") from None
            code = getattr(exc, "code", None)
            if code in (401, 403):
                raise APIError(502, "AI_AUTHENTICATION_FAILED", "Gemini rejected the configured credentials.") from None
            if code == 429:
                raise APIError(429, "AI_RATE_LIMITED", "Gemini is rate limiting requests. Please try again shortly.") from None
            if code in (408, 504):
                raise APIError(504, "AI_TIMEOUT", "Gemini did not respond before the configured timeout.") from None
            if code == 404:
                raise APIError(503, "AI_MODEL_UNAVAILABLE", f"The configured Gemini model '{self.settings.gemini_model}' is unavailable to this project. Check model access and the model identifier.") from None
            if code == 503:
                raise APIError(503, "AI_PROVIDER_UNAVAILABLE", "Gemini is temporarily unavailable.") from None
            if code == 400:
                raise APIError(503, "AI_CONFIGURATION_INVALID", "Gemini rejected the configured model or request format.") from None
            raise APIError(502, "AI_PROVIDER_ERROR", "Gemini could not complete the request.") from None


class MockTextGenerator:
    """Explicit test-only content; never represents output as AI generated."""

    def diagnostics(self) -> dict[str, Any]:
        return {"provider": "mock", "configured": True, "generation_available": True,
                "availability_reason": "Mock provider returns test content only.", "missing_configuration": [],
                "deployment_name": None, "model": "mock", "timeout_seconds": 1.0,
                "max_retries": 0, "voice_deployment_used": False}

    def chat_json(self, *, system: str, user: str, max_tokens: int = 7000) -> TextGenerationResult:
        if '"answer"' in system:
            content = {"answer": "Mock tutor response for local testing; this is not AI-generated."}
        else:
            content = {
                "title": "Mock lesson for local testing", "introduction": "Test content; not AI generated.",
                "estimated_minutes": 10,
                "learning_objectives": [{"objective_id": "mock-objective-1", "text": "Review the test objective."}],
                "sections": [
                    {"section_id": f"mock-section-{i}", "title": f"Test section {i}", "required": True,
                     "blocks": [{"type": "paragraph", "text": "Mock provider test content."}]}
                    for i in range(1, 4)
                ],
                "questions": [{"question_type": "single_choice", "prompt": f"Test question {index}: which provider produced this?",
                    "options": [{"option_id": "a", "text": "Mock"}, {"option_id": "b", "text": "AI"}],
                    "grading": {"kind": "choice", "correct_option_ids": ["a"]},
                    "expected_answer": "Mock", "explanation": "This is explicitly test content.",
                    "difficulty": "introductory"} for index in range(1, 4)],
            }
        return TextGenerationResult(content=json.dumps(content), usage=None, model="mock")


@dataclass(frozen=True)
class ProviderSelection:
    name: str
    client: JSONTextGenerator


def select_text_generator(settings: APISettings) -> ProviderSelection:
    provider = settings.ai_provider.casefold()
    if provider == "azure":
        client = AzureOpenAIClient(settings)
    elif provider == "gemini":
        client = GeminiClient(settings)
    elif provider == "mock":
        client = MockTextGenerator()
    else:
        raise APIError(503, "AI_CONFIGURATION_INVALID", "AI_PROVIDER must be azure, gemini, or mock.")
    return ProviderSelection(provider, client)
