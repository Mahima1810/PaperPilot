"""Citation-grounded answering.

Rules that keep answers checkable:
1. The model only sees retrieved passages, numbered [1]..[n].
2. Every claim must cite a passage; citations to passages that don't exist are dropped.
3. An answer with no valid citation is rejected and replaced by the extractive answer.
4. If retrieval finds nothing relevant, PaperPilot says so instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .chunker import split_sentences
from .llm import ChatClient, LLMError
from .retriever import Hit, tokenize

CITATION = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")
NOT_FOUND = "I couldn't find this in the document."

SYSTEM_PROMPT = """You answer questions about a research paper using ONLY the numbered passages provided.
Rules:
- Cite the passage number in square brackets after every claim, e.g. "The model uses LoRA [2]."
- If the passages do not contain the answer, reply exactly: "I couldn't find this in the document."
- Do not use outside knowledge. Do not invent numbers, names or results.
- Be concise: 2-5 sentences."""


@dataclass
class Citation:
    n: int
    chunk_id: str
    section: str
    page_start: int
    page_end: int
    quote: str


@dataclass
class Answer:
    answer: str
    mode: str  # "llm" | "extractive" | "not_found"
    citations: list[Citation] = field(default_factory=list)
    warning: str | None = None


def _citation_for(n: int, hit: Hit) -> Citation:
    c = hit.chunk
    return Citation(
        n=n, chunk_id=c.id, section=c.section, page_start=c.page_start,
        page_end=c.page_end, quote=c.text,
    )


PAPER_REF = re.compile(r"\[(\d{1,3}(?:\s*[,–-]\s*\d{1,3})*)\]")


def neutralize_refs(text: str) -> str:
    """Papers cite their bibliography as "[20]". Rewrite those so they can't be
    confused with PaperPilot's own passage citations."""
    return PAPER_REF.sub(r"(ref. \1)", text)


def build_context(hits: list[Hit]) -> str:
    return "\n\n".join(
        f"[{i}] (section: {h.chunk.section}, page {h.chunk.page_start})\n{neutralize_refs(h.chunk.text)}"
        for i, h in enumerate(hits, start=1)
    )


def verify_citations(text: str, n_passages: int) -> tuple[str, set[int]]:
    """Remove citations that point to non-existent passages; return the cleaned text and the valid ids."""
    valid: set[int] = set()

    def repl(match: re.Match) -> str:
        nums = [int(x) for x in re.split(r"\s*,\s*", match.group(1))]
        keep = [n for n in nums if 1 <= n <= n_passages]
        valid.update(keep)
        return f"[{', '.join(map(str, keep))}]" if keep else ""

    cleaned = CITATION.sub(repl, text)
    return re.sub(r"\s+([.,;])", r"\1", cleaned).strip(), valid


def extractive_answer(question: str, hits: list[Hit], max_sentences: int = 3) -> Answer:
    """Pick the sentences from the top passages that share the most terms with the question."""
    q_terms = set(tokenize(question))
    scored: list[tuple[float, int, str]] = []
    seen: set[str] = set()
    for n, hit in enumerate(hits, start=1):
        for sent in split_sentences(neutralize_refs(hit.chunk.text)):
            key = re.sub(r"\W+", "", sent.lower())
            # Neighbouring chunks overlap, so skip repeats (including a sentence cut short at a chunk edge).
            if not key or any(key in k or k in key for k in seen):
                continue
            seen.add(key)
            terms = set(tokenize(sent))
            if not terms:
                continue
            overlap = len(q_terms & terms)
            if overlap:
                # prefer high overlap, then higher-ranked passages, then complete sentences
                complete = 0.5 if sent.rstrip().endswith((".", "!", "?")) else 0.0
                scored.append((overlap + hit.score * 10 + complete, n, sent))
    if not scored:
        return Answer(answer=NOT_FOUND, mode="not_found")

    scored.sort(key=lambda x: -x[0])
    picked = sorted(scored[:max_sentences], key=lambda x: x[1])  # keep passage order for readability
    used = sorted({n for _, n, _ in picked})
    text = " ".join(f"{sent} [{n}]" for _, n, sent in picked)
    return Answer(
        answer=text,
        mode="extractive",
        citations=[_citation_for(n, hits[n - 1]) for n in used],
    )


def answer_question(question: str, hits: list[Hit], client: ChatClient | None) -> Answer:
    if not hits:
        return Answer(answer=NOT_FOUND, mode="not_found")

    if client is None:
        return extractive_answer(question, hits)

    try:
        raw = client.complete(
            SYSTEM_PROMPT,
            f"Passages:\n{build_context(hits)}\n\nQuestion: {question}",
        )
    except LLMError as exc:
        fallback = extractive_answer(question, hits)
        fallback.warning = f"LLM unavailable, showing extractive answer instead ({exc})."
        return fallback

    if NOT_FOUND.lower().rstrip(".") in raw.lower():
        return Answer(answer=NOT_FOUND, mode="not_found")

    cleaned, valid = verify_citations(raw, len(hits))
    if not valid:
        fallback = extractive_answer(question, hits)
        fallback.warning = "The model's answer had no valid citations, so it was discarded."
        return fallback

    return Answer(
        answer=cleaned,
        mode="llm",
        citations=[_citation_for(n, hits[n - 1]) for n in sorted(valid)],
    )
