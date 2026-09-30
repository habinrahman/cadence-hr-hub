"""Structured extraction stays behind this protocol. Bedrock is the later provider."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.extraction.draft import ExtractionDraft


class ExtractorUnavailable(Exception):
    code = "extractor_unavailable"


class StructuredExtractor(Protocol):
    def extract(self, *, document_id: UUID, source_text: str, prompt_version: str) -> ExtractionDraft:
        """Return a draft. The caller verifies every quote before storing it."""


class BedrockExtractor:
    """Placeholder for an approved Bedrock model. It does not call AWS in this slice."""

    model_name = "bedrock"

    def extract(self, *, document_id: UUID, source_text: str, prompt_version: str) -> ExtractionDraft:
        del document_id, source_text, prompt_version
        raise ExtractorUnavailable()


def get_extractor(provider: str | None = None) -> StructuredExtractor | None:
    from app.config import get_settings
    from app.extraction.deterministic import DeterministicExtractor

    name = provider if provider is not None else get_settings().extractor_provider
    if name == "none":
        return None
    if name == "deterministic":
        return DeterministicExtractor()
    if name == "bedrock":
        return BedrockExtractor()
    raise ExtractorUnavailable()


def get_embedder(provider: str | None = None):
    from app.config import get_settings
    from app.extraction.embeddings import BedrockEmbedder, EmbeddingUnavailable, LocalFeatureEmbedder

    name = provider if provider is not None else get_settings().embedding_provider
    if name == "none":
        return None
    if name == "local":
        return LocalFeatureEmbedder()
    if name == "bedrock":
        return BedrockEmbedder()
    raise EmbeddingUnavailable()
