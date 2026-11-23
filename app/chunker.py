"""Split parsed sections into overlapping, citable chunks."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .pdf_parser import ParsedDocument

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


@dataclass
class Chunk:
    id: str
    section: str
    page_start: int
    page_end: int
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]


def chunk_document(
    doc: ParsedDocument, target_words: int = 140, overlap_words: int = 30
) -> list[Chunk]:
    """Group lines into chunks of roughly `target_words`, never crossing a section.

    Chunks overlap by about `overlap_words` so a sentence cut at a boundary is
    still retrievable in full from one of the two neighbours.
    """
    chunks: list[Chunk] = []
    for section in doc.sections:
        if section.title.lower() == "references":
            continue  # bibliography entries make noisy retrieval results
        buffer: list[tuple[int, str]] = []
        words = 0
        fresh = False  # does the buffer hold lines not yet in any chunk?
        for page, line in section.lines:
            buffer.append((page, line))
            words += len(line.split())
            fresh = True
            if words >= target_words:
                chunks.append(_make_chunk(len(chunks), section.title, buffer))
                buffer, words = _tail(buffer, overlap_words)
                fresh = False
        if buffer and fresh:
            chunks.append(_make_chunk(len(chunks), section.title, buffer))
    return chunks


def _make_chunk(index: int, section: str, lines: list[tuple[int, str]]) -> Chunk:
    text = " ".join(line for _, line in lines)
    return Chunk(
        id=f"c{index}",
        section=section,
        page_start=lines[0][0],
        page_end=lines[-1][0],
        text=re.sub(r"\s+", " ", text).strip(),
    )


def _tail(lines: list[tuple[int, str]], overlap_words: int) -> tuple[list[tuple[int, str]], int]:
    kept: list[tuple[int, str]] = []
    count = 0
    for page, line in reversed(lines):
        if count >= overlap_words:
            break
        kept.insert(0, (page, line))
        count += len(line.split())
    return kept, count
