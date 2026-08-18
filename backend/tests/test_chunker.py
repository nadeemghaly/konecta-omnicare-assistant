"""Chunking is what makes a citation verifiable, so it gets tested directly."""

from app.rag.chunker import chunk_policy_document

POLICY = """\
# OmniCare General Insurance Policy 2026

## Section 1: Home Water Damage Coverage

Water damage caused by sudden pipe bursts is covered up to $25,000 with a $500 deductible. Gradual leaks or flood damage are strictly excluded.

## Section 2: Personal Property Protection

Electronics, furniture, and jewelry are covered up to $10,000 total. Single items exceeding $2,500 require individual appraisal receipts.
"""


def test_splits_into_one_chunk_per_sentence():
    chunks = chunk_policy_document(POLICY)
    assert len(chunks) == 4


def test_each_chunk_carries_its_section_heading():
    chunks = chunk_policy_document(POLICY)
    sections = [c.section for c in chunks]
    assert sections == [
        "Section 1: Home Water Damage Coverage",
        "Section 1: Home Water Damage Coverage",
        "Section 2: Personal Property Protection",
        "Section 2: Personal Property Protection",
    ]


def test_document_title_is_not_treated_as_a_section():
    assert all("OmniCare General Insurance Policy" not in c.section for c in chunk_policy_document(POLICY))


def test_currency_amounts_are_not_split_on():
    """"$25,000" and "$2,500" must survive sentence splitting intact."""
    texts = [c.text for c in chunk_policy_document(POLICY)]
    assert any("$25,000" in t and "$500" in t for t in texts)
    assert any("$2,500" in t for t in texts)


def test_exclusion_is_its_own_chunk():
    """The exclusion must be retrievable separately, or a question about gradual
    leaks can only ever match the sentence saying water damage IS covered."""
    chunks = chunk_policy_document(POLICY)
    exclusions = [c for c in chunks if "strictly excluded" in c.text]
    assert len(exclusions) == 1
    assert exclusions[0].text.startswith("Gradual leaks")


def test_text_before_any_section_is_kept_as_preamble():
    chunks = chunk_policy_document("# Title\n\nSome preamble sentence here.\n")
    assert [c.section for c in chunks] == ["Preamble"]


def test_empty_document_yields_no_chunks():
    assert chunk_policy_document("") == []
