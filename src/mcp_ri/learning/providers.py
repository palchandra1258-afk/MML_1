"""Provider boundary for structured learning tasks.

The current Student Studio plan path is intentionally local and rule-based.
This interface makes future provider adapters replaceable without coupling
curriculum mapping or sequencing to Azure-specific request details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderAvailability:
    capability: str
    available: bool
    provider_id: str | None
    reason: str


class StructuredLearningProvider(Protocol):
    def availability(self, capability: str) -> ProviderAvailability: ...

    def generate_json(self, *, capability: str, context: dict[str, Any]) -> dict[str, Any]: ...


class LearningProviderUnavailable(RuntimeError):
    """Raised when a requested AI capability has no suitable provider."""


class UnavailableStructuredLearningProvider:
    """Explicit default until a compatible text provider is integrated."""

    def availability(self, capability: str) -> ProviderAvailability:
        return ProviderAvailability(
            capability=capability,
            available=False,
            provider_id=None,
            reason=(
                "No AI provider is integrated for learning-plan generation. "
                "The current Azure realtime deployment is not used for text planning."
            ),
        )

    def generate_json(self, *, capability: str, context: dict[str, Any]) -> dict[str, Any]:
        raise LearningProviderUnavailable(
            f"No structured provider is available for capability {capability!r}."
        )
