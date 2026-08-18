"""Chroma-backed policy index: idempotent ingest, retrieval with provenance."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings as ChromaSettings

from ..config import Settings, get_settings
from ..schemas import Source
from .chunker import Chunk, chunk_policy_document
from .embeddings import Embedder, build_embedder

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True)
class Retrieved:
    """A retrieved chunk and its distance from the query."""

    source: Source
    distance: float


class PolicyIndex:
    """The Policy Document, embedded and searchable.

    Ingest is idempotent: it is safe to call on every container start. The
    embedder's fingerprint is part of the collection name, so switching embedding
    providers or dimensions creates a *new* collection rather than querying an
    incompatible one with the wrong vector space.
    """

    def __init__(self, settings: Settings | None = None, embedder: Embedder | None = None):
        self._settings = settings or get_settings()
        self._embedder = embedder or build_embedder(self._settings)
        self._settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(self._settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name(),
            metadata={"hnsw:space": "cosine"},
        )

    def _collection_name(self) -> str:
        return f"policy__{_UNSAFE.sub('-', self._embedder.fingerprint)}"[:512]

    @property
    def size(self) -> int:
        return self._collection.count()

    def ingest(self, markdown: str | None = None, force: bool = False) -> int:
        """Embed and store the policy document. Returns the chunk count.

        Skips the work when the collection already holds exactly the chunks this
        document produces -- so `docker compose up` on an existing volume starts
        instantly instead of re-paying for embeddings.
        """
        if markdown is None:
            markdown = self._settings.policy_path.read_text(encoding="utf-8")

        chunks = chunk_policy_document(markdown)
        if not chunks:
            raise ValueError(f"No chunks produced from {self._settings.policy_path}")

        if not force and self._collection.count() == len(chunks):
            logger.info("Policy index already populated (%d chunks); skipping ingest", len(chunks))
            return len(chunks)

        if self._collection.count():
            # Stale count means the document changed: rebuild rather than
            # accumulate a mix of old and new sentences.
            logger.info("Policy index stale; rebuilding")
            self._client.delete_collection(self._collection.name)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name(), metadata={"hnsw:space": "cosine"}
            )

        self._collection.add(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[{"section": c.section, "ordinal": c.ordinal} for c in chunks],
            embeddings=self._embedder.embed_documents([c.text for c in chunks]),
        )
        logger.info("Ingested %d chunks into %s", len(chunks), self._collection.name)
        return len(chunks)

    def search(self, query: str, k: int | None = None) -> list[Retrieved]:
        k = k or self._settings.retrieval_k
        if self._collection.count() == 0:
            return []

        result = self._collection.query(
            query_embeddings=[self._embedder.embed_query(query)],
            n_results=min(k, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        hits = [
            Retrieved(
                source=Source(section=str(meta.get("section", "Unknown")), quote=doc),
                distance=float(dist),
            )
            for doc, meta, dist in zip(documents, metadatas, distances)
        ]
        return self._keep_relevant(hits)

    def _keep_relevant(self, hits: list[Retrieved]) -> list[Retrieved]:
        """Drop near-neighbours that are not actually about the question.

        Chroma returns k results regardless of relevance, so without this a
        question about burst pipes cites the personal-property clause. Filtering
        here -- rather than only when rendering citations -- keeps one invariant
        true: what the model was shown and what we cite are the same text.
        """
        if not hits:
            return []
        best = min(hit.distance for hit in hits)
        cutoff = best + self._settings.relevance_margin
        kept = [
            hit
            for hit in hits
            if hit.distance <= cutoff and hit.distance < self._settings.max_distance
        ]
        # Never return nothing when something was the closest match: let the model
        # see the best candidate and decide the policy is silent on the question.
        return kept or hits[:1]
