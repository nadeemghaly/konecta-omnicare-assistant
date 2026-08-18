"""Retrieval behaviour: does the right sentence come back, with provenance."""

from app.config import Settings
from app.rag.embeddings import LexicalEmbedder
from app.rag.store import PolicyIndex


def test_ingest_is_idempotent(settings: Settings):
    index = PolicyIndex(settings)
    first = index.ingest()
    assert index.ingest() == first
    assert index.size == first


def test_ingest_rebuilds_when_the_document_changes(settings: Settings):
    index = PolicyIndex(settings)
    index.ingest()
    index.ingest(markdown="## Section 9: New\n\nOne sentence. Two sentences.\n")
    assert index.size == 2


def test_retrieval_finds_the_relevant_sentence(index: PolicyIndex):
    hits = index.search("sudden burst pipe water damage")
    assert hits
    assert "pipe bursts" in hits[0].source.quote


def test_retrieval_finds_the_exclusion(index: PolicyIndex):
    hits = index.search("gradual leak slow drip excluded")
    assert "Gradual leaks" in hits[0].source.quote


def test_every_hit_carries_a_section(index: PolicyIndex):
    for hit in index.search("jewelry appraisal receipts"):
        assert hit.source.section.startswith("Section")


def test_irrelevant_chunks_are_filtered_out(index: PolicyIndex):
    """Chroma returns k neighbours whether or not they are relevant. Without the
    relevance filter a burst-pipe question cites Personal Property, which makes
    the citation worthless."""
    hits = index.search("sudden burst pipe water damage")
    assert all("Water Damage" in hit.source.section for hit in hits)


def test_search_returns_something_even_for_an_off_topic_question(index: PolicyIndex):
    """The model needs to see the best candidate to say the policy is silent."""
    assert index.search("does my policy cover a trip to Mars") != []


def test_empty_index_returns_no_hits(settings: Settings):
    assert PolicyIndex(settings).search("anything") == []


def test_collection_name_is_stamped_with_the_embedder_fingerprint(settings: Settings):
    """Switching embedder must not query an index built in another vector space --
    that returns plausible garbage rather than an error."""
    index = PolicyIndex(settings, embedder=LexicalEmbedder(dims=256))
    other = PolicyIndex(settings, embedder=LexicalEmbedder(dims=128))
    assert index._collection.name != other._collection.name  # noqa: SLF001
    assert "256" in index._collection.name  # noqa: SLF001


def test_source_renders_as_heading_plus_quote(index: PolicyIndex):
    rendered = index.search("burst pipe")[0].source.render()
    assert "Section 1: Home Water Damage Coverage" in rendered
    assert "pipe bursts" in rendered
