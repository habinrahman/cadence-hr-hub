"""Job-description readers. A proposal is checked before it becomes a requirement."""

from __future__ import annotations

from typing import Protocol

from app.domain.requirement_schema import ProposedRequirement
from app.domain.requirements import parse_job_requirements
from app.extraction.provider import ExtractorUnavailable


class RequirementReader(Protocol):
    model_name: str

    def propose(self, description: str) -> list[ProposedRequirement]: ...


class DeterministicRequirementReader:
    """Read labeled lines and a few free-form phrases. This is not a model score."""

    model_name = "deterministic-requirement-parser"

    def propose(self, description: str) -> list[ProposedRequirement]:
        return [
            ProposedRequirement(label=item.label, text=item.text, strength=item.strength, quote=item.quote)
            for item in parse_job_requirements(description)
        ]


class BedrockRequirementReader:
    """Placeholder for an approved model. It does not call AWS in this slice."""

    model_name = "bedrock"

    def propose(self, description: str) -> list[ProposedRequirement]:
        del description
        raise ExtractorUnavailable()


def get_requirement_reader(provider: str | None = None) -> RequirementReader | None:
    from app.config import get_settings

    name = provider if provider is not None else get_settings().requirement_provider
    if name == "none":
        return None
    if name == "deterministic":
        return DeterministicRequirementReader()
    if name == "bedrock":
        return BedrockRequirementReader()
    if name == "ollama":
        from app.config import get_settings as settings
        from app.extraction.llm_requirements import LlmWithFallbackReader, OllamaRequirementReader

        config = settings()
        return LlmWithFallbackReader(
            OllamaRequirementReader(
                base_url=config.ollama_base_url, model=config.ollama_model, timeout=config.ollama_timeout_seconds
            ),
            DeterministicRequirementReader(),
        )
    raise ExtractorUnavailable()
