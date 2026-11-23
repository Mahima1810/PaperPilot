"""Turn a PDF into pages and sections.

Research papers rarely carry reliable structure metadata, so sections are
detected from the text itself: numbered headings ("3 Method", "4.2 Results")
and well-known unnumbered headings ("Abstract", "References").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO

from pypdf import PdfReader

KNOWN_HEADINGS = {
    "abstract",
    "introduction",
    "background",
    "related work",
    "preliminaries",
    "methods",
    "methodology",
    "experiments",
    "experimental setup",
    "evaluation",
    "results",
    "discussion",
    "limitations",
    "conclusion",
    "conclusions",
    "future work",
    "acknowledgements",
    "acknowledgments",
    "references",
    "appendix",
}

# "3 Method", "4.2 Ablation study", "IV. RESULTS"
NUMBERED_HEADING = re.compile(
    r"^(?P<num>(\d{1,2}(\.\d{1,2}){0,2})|([IVX]{1,5}))\.?\s+(?P<title>[A-Z][A-Za-z0-9 ,:&()/'?-]{2,80})$"
)


@dataclass
class Section:
    title: str
    page_start: int
    lines: list[tuple[int, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line for _, line in self.lines)


@dataclass
class ParsedDocument:
    title: str
    num_pages: int
    sections: list[Section]


class PDFParseError(ValueError):
    """Raised when a file can't be read or contains no extractable text."""


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # ligatures like "ﬁ" -> "fi"
    text = text.replace("­", "")  # soft hyphen
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join hyphenated line breaks
    text = re.sub(r"[ \t]+", " ", text)
    return text


TITLE_BOILERPLATE = re.compile(
    r"permission|copyright|licen[cs]e|arxiv|preprint|proceedings|conference|journal|"
    r"submitted|accepted|published|doi|https?://|@|university|institute",
    re.IGNORECASE,
)


def _fix_small_caps(text: str) -> str:
    """pypdf renders small caps as "I NTRODUCTION"; glue the split capital back on."""
    return re.sub(r"\b([A-Z]) (?=[A-Z]{2,}\b)", r"\1", text)


def _pretty(title: str) -> str:
    letters = [c for c in title if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        small = {"and", "of", "the", "for", "in", "on", "to", "a", "an", "with"}
        words = title.lower().split()
        return " ".join(
            w if i and w in small else (w.upper() if w in {"lora", "gpt-2", "bert", "llm"} else w.capitalize())
            for i, w in enumerate(words)
        )
    return title


def _heading_title(line: str) -> str | None:
    """Return a normalised heading title if `line` looks like a section heading."""
    stripped = _fix_small_caps(line.strip())
    if not stripped or len(stripped) > 90:
        return None
    lowered = stripped.lower().rstrip(":. ")
    if lowered in KNOWN_HEADINGS:
        return stripped.rstrip(":. ").title()  # e.g. "ABSTRACT" -> "Abstract"
    match = NUMBERED_HEADING.match(stripped)
    if match:
        title = match.group("title").strip()
        # Ignore lines that look like sentences or table rows.
        words = title.split()
        if len(words) <= 8 and not title.endswith(".") and not re.search(r"\d{3,}", title):
            return f"{match.group('num')} {_pretty(title)}"
    return None


def _guess_title(first_page: str, metadata_title: str | None) -> str:
    if metadata_title and len(metadata_title.strip()) > 3 and not TITLE_BOILERPLATE.search(metadata_title):
        return _pretty(_fix_small_caps(metadata_title.strip()))
    for line in first_page.splitlines()[:25]:
        line = _fix_small_caps(line.strip())
        looks_like_sentence = line.endswith(".") or line[:1].islower()
        if (
            10 <= len(line) <= 150
            and not looks_like_sentence
            and not _heading_title(line)
            and not TITLE_BOILERPLATE.search(line)
        ):
            return _pretty(line)
    return "Untitled document"


def parse_pdf(data: bytes) -> ParsedDocument:
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")
        pages = [_clean(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # pypdf raises many different error types
        raise PDFParseError(f"Could not read this PDF: {exc}") from exc

    if not any(p.strip() for p in pages):
        raise PDFParseError(
            "No text found in this PDF. It may be a scanned image; OCR is not supported yet."
        )

    meta_title = None
    try:
        meta_title = reader.metadata.title if reader.metadata else None
    except Exception:
        meta_title = None

    sections: list[Section] = []
    current = Section(title="Front matter", page_start=1)
    for page_no, page_text in enumerate(pages, start=1):
        for line in page_text.splitlines():
            heading = _heading_title(line)
            if heading:
                if current.lines:
                    sections.append(current)
                current = Section(title=heading, page_start=page_no)
                continue
            if line.strip():
                current.lines.append((page_no, line.strip()))
    if current.lines:
        sections.append(current)

    return ParsedDocument(
        title=_guess_title(pages[0], meta_title),
        num_pages=len(pages),
        sections=sections,
    )
