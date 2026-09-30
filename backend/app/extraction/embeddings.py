"""Local embeddings are deterministic. Bedrock can replace this provider later."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.constants import EMBEDDING_DIMENSIONS


class EmbeddingUnavailable(Exception):
    code = "embedding_unavailable"


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalFeatureEmbedder:
    """Hash tokens into a fixed vector. Shared words raise cosine similarity."""

    model_name = "local-feature-hash"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_one(text) for text in texts]


class BedrockEmbedder:
    model_name = "bedrock"

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingUnavailable()


def _embed_one(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:2], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _tokens(text: str) -> list[str]:
    cleaned = "".join(character.lower() if character.isalnum() else " " for character in text)
    return [token for token in cleaned.split() if len(token) > 1]
