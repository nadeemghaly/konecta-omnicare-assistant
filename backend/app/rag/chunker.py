"""Section-aware, sentence-level chunking of the Policy Document.

Why sentence-level rather than one chunk per section: a Source is defined as a
section heading *plus the verbatim sentence relied upon* (CONTEXT.md). If a chunk
were a whole section, the citing sentence would have to be self-reported by the
model -- an unverifiable claim. Chunking at the sentence makes the citation fall
out of retrieval itself, so it is always exactly what the answer was grounded in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Split on sentence-final punctuation followed by whitespace. Currency amounts in
# this corpus use commas ("$25,000"), not periods, so they survive intact.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass(frozen=True)
class Chunk:
    """One retrievable sentence, tagged with the section it came from."""

    text: str
    section: str
    ordinal: int

    @property
    def id(self) -> str:
        return f"{self.section}#{self.ordinal}"


def chunk_policy_document(markdown: str) -> list[Chunk]:
    """Split a policy document into sentence chunks carrying their section heading.

    The document title (`#`) is not a section; only `##` and deeper are. Text
    appearing before any section heading is attributed to "Preamble" so it stays
    retrievable rather than being silently dropped.
    """
    chunks: list[Chunk] = []
    section = "Preamble"
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        body = " ".join(buffer).strip()
        buffer.clear()
        if not body:
            return
        for sentence in _SENTENCE_BOUNDARY.split(body):
            sentence = sentence.strip()
            if sentence:
                chunks.append(Chunk(text=sentence, section=section, ordinal=len(chunks)))

    for line in markdown.splitlines():
        match = _HEADING.match(line.strip())
        if match:
            level, title = match.group(1), match.group(2).strip()
            if len(level) == 1:
                # Document title: not a section, but flush anything before it.
                flush()
                continue
            flush()
            section = title
            continue
        buffer.append(line.strip())

    flush()
    return chunks
