"""Small Azure OpenAI REST client with bounded retries and safe diagnostics."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import APIError
from .settings import APISettings


@dataclass(frozen=True)
class AzureResult:
    content: str
    usage: dict[str, int] | None
    model: str | None
    status_code: int = 200


class AzureOpenAIClient:
    def __init__(self, settings: APISettings, *, opener: Callable[..., Any] = urlopen,
                 sleeper: Callable[[float], None] = time.sleep):
        self.settings = settings
        self._opener = opener
        self._sleep = sleeper

    def missing_configuration(self) -> list[str]:
        values = {
            "AZURE_OPENAI_ENDPOINT": self.settings.azure_openai_endpoint,
            "AZURE_OPENAI_API_KEY": self.settings.azure_openai_api_key,
            "AZURE_OPENAI_DEPLOYMENT_NAME": self.settings.azure_openai_deployment_name,
            "AZURE_OPENAI_API_VERSION": self.settings.azure_openai_api_version,
        }
        return [name for name, value in values.items() if not value]

    def diagnostics(self) -> dict[str, Any]:
        missing = self.missing_configuration()
        realtime_deployment = self.settings.azure_openai_deployment_name.casefold() == "gpt-realtime"
        availability_reason = None
        if missing:
            availability_reason = "Required Azure OpenAI settings are missing: " + ", ".join(missing)
        elif realtime_deployment:
            availability_reason = "The configured realtime deployment does not support lesson text generation."
        return {
            "provider": "azure_openai",
            "configured": not missing,
            "generation_available": not missing and not realtime_deployment,
            "availability_reason": availability_reason,
            "missing_configuration": missing,
            "deployment_name": self.settings.azure_openai_deployment_name or None,
            "model": self.settings.azure_openai_deployment_name or None,
            "timeout_seconds": min(120.0, max(1.0, self.settings.azure_openai_timeout_seconds)),
            "max_retries": min(5, max(0, self.settings.azure_openai_max_retries)),
            "voice_deployment_used": False,
        }

    def chat_json(self, *, system: str, user: str, max_tokens: int = 7000) -> AzureResult:
        missing = self.missing_configuration()
        if missing:
            raise APIError(503, "AI_NOT_CONFIGURED", "Azure OpenAI is not configured. Set: " + ", ".join(missing))
        endpoint = self.settings.azure_openai_endpoint.rstrip("/")
        if not endpoint.startswith("https://"):
            raise APIError(503, "AI_CONFIGURATION_INVALID", "AZURE_OPENAI_ENDPOINT must use HTTPS.")
        deployment = self.settings.azure_openai_deployment_name
        if deployment.casefold() == "gpt-realtime":
            raise APIError(503, "AI_CONFIGURATION_INVALID", "AZURE_OPENAI_DEPLOYMENT_NAME must identify a text-generation deployment.")
        url = (f"{endpoint}/openai/deployments/{deployment}/chat/completions"
               f"?api-version={self.settings.azure_openai_api_version}")
        body = json.dumps({
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.35,
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        request = Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json",
            "api-key": self.settings.azure_openai_api_key,
        })
        max_retries = min(5, max(0, self.settings.azure_openai_max_retries))
        timeout = min(120.0, max(1.0, self.settings.azure_openai_timeout_seconds))
        for attempt in range(max_retries + 1):
            try:
                with self._opener(request, timeout=timeout) as response:
                    status_code = getattr(response, "status", None)
                    if status_code is None:
                        getcode = getattr(response, "getcode", None)
                        status_code = getcode() if callable(getcode) else 200
                    raw = response.read(2_000_001)
                    if len(raw) > 2_000_000:
                        raise APIError(502, "AI_RESPONSE_TOO_LARGE", "Azure OpenAI returned an oversized response.")
                document = json.loads(raw)
                content = document["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("empty model response")
                usage_raw = document.get("usage")
                usage = None
                if isinstance(usage_raw, dict):
                    usage = {key: int(usage_raw[key]) for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                             if isinstance(usage_raw.get(key), int)}
                return AzureResult(
                    content=content,
                    usage=usage,
                    model=document.get("model"),
                    status_code=int(status_code),
                )
            except HTTPError as exc:
                if exc.code == 429 and attempt < max_retries:
                    retry_after = exc.headers.get("Retry-After", "1") if exc.headers else "1"
                    try:
                        delay = min(5.0, max(0.0, float(retry_after)))
                    except ValueError:
                        delay = 1.0
                    self._sleep(delay)
                    continue
                if exc.code == 429:
                    raise APIError(429, "AI_RATE_LIMITED", "Azure OpenAI is rate limiting requests. Please try again shortly.") from None
                if exc.code in {401, 403}:
                    raise APIError(502, "AI_AUTHENTICATION_FAILED", "Azure OpenAI rejected the configured credentials or deployment access.") from None
                if exc.code in {408, 504}:
                    raise APIError(504, "AI_TIMEOUT", "Azure OpenAI did not respond before the configured timeout.") from None
                if exc.code >= 500 and attempt < max_retries:
                    self._sleep(min(0.5 * (2 ** attempt), 3.0))
                    continue
                raise APIError(502, "AI_PROVIDER_ERROR", "Azure OpenAI could not complete the request.") from None
            except (TimeoutError, URLError):
                if attempt < max_retries:
                    self._sleep(min(0.5 * (2 ** attempt), 3.0))
                    continue
                raise APIError(504, "AI_TIMEOUT", "Azure OpenAI did not respond before the configured timeout.") from None
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
                raise APIError(502, "AI_INVALID_RESPONSE", "Azure OpenAI returned an invalid structured response.") from None
        raise APIError(502, "AI_PROVIDER_ERROR", "Azure OpenAI could not complete the request.")
