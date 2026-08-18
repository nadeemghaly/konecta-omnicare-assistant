"""Embedding providers.

Unlike the chat model, embedders are *not* hot-swappable: two providers produce
different dimensions and, worse, different vector spaces. Querying an index built
by provider A with vectors from provider B returns plausible-looking garbage
rather than an error. Each embedder therefore exposes a `fingerprint`, which the
store bakes into the collection name so a provider change forces a clean rebuild.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

from ..config import Settings, get_settings


@runtime_checkable
class Embedder(Protocol):
    @property
    def fingerprint(self) -> str:
        """Identifies the vector space. Changing it invalidates the index."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class GeminiEmbedder:
    """Gemini embeddings, using asymmetric task types.

    Documents and queries are embedded with different task types on purpose:
    `RETRIEVAL_DOCUMENT` and `RETRIEVAL_QUERY` place a passage and a question
    that *seeks* that passage nearer each other than naive symmetric embedding
    would.
    """

    def __init__(self, settings: Settings | None = None):
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        self._settings = settings or get_settings()
        self._dims = self._settings.embedding_dimensions
        self._model = self._settings.gemini_embedding_model
        self._client = GoogleGenerativeAIEmbeddings(
            model=self._model,
            google_api_key=self._settings.gemini_api_key,
        )

    @property
    def fingerprint(self) -> str:
        return f"gemini-{self._model}-{self._dims}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed_documents(
            texts, task_type="RETRIEVAL_DOCUMENT", output_dimensionality=self._dims
        )

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(
            text, task_type="RETRIEVAL_QUERY", output_dimensionality=self._dims
        )


class LexicalEmbedder:
    """Deterministic, offline embedder used by the hermetic test suite.

    Hashed bag-of-words with L2 normalisation. This is not a semantic model, but
    it produces *genuine lexical similarity*, so retrieval tests assert real
    behaviour -- "burst pipe" ranks the water-damage sentence first -- rather
    than merely asserting that some vector came back.
    """

    def __init__(self, dims: int = 256):
        self._dims = dims

    @property
    def fingerprint(self) -> str:
        return f"lexical-{self._dims}"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self._dims
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            vec[int.from_bytes(digest, "big") % self._dims] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def build_embedder(settings: Settings | None = None) -> Embedder:
    settings = settings or get_settings()
    if settings.llm_provider == "fake":
        return LexicalEmbedder()
    # The backup chat provider still uses Gemini embeddings: Groq serves no
    # embedding models, and swapping embedders is the one change that silently
    # breaks retrieval. Keeping one vector space is the safer default.
    return GeminiEmbedder(settings)
