"""Document store: parsed chunks are cached as JSON on disk and indexed in memory."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .chunker import Chunk, chunk_document
from .pdf_parser import parse_pdf
from .retriever import HybridRetriever


@dataclass
class StoredDocument:
    id: str
    filename: str
    title: str
    num_pages: int
    sections: list[str]
    chunks: list[Chunk]
    uploaded_at: str
    retriever: HybridRetriever

    def summary(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "num_pages": self.num_pages,
            "num_chunks": len(self.chunks),
            "sections": self.sections,
            "uploaded_at": self.uploaded_at,
        }


class DocumentStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._docs: dict[str, StoredDocument] = {}
        self._lock = threading.Lock()
        self._load_existing()

    def _load_existing(self) -> None:
        for path in sorted(self.data_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                chunks = [Chunk(**c) for c in raw["chunks"]]
                self._docs[raw["id"]] = self._build(raw, chunks)
            except (OSError, KeyError, TypeError, ValueError):
                continue  # skip corrupt cache files rather than failing startup

    @staticmethod
    def _build(meta: dict, chunks: list[Chunk]) -> StoredDocument:
        return StoredDocument(
            id=meta["id"], filename=meta["filename"], title=meta["title"],
            num_pages=meta["num_pages"], sections=meta["sections"], chunks=chunks,
            uploaded_at=meta["uploaded_at"], retriever=HybridRetriever(chunks),
        )

    def add(self, filename: str, data: bytes) -> tuple[StoredDocument, bool]:
        """Parse and index a PDF. Returns (document, created). Re-uploads are de-duplicated by content hash."""
        doc_id = hashlib.sha256(data).hexdigest()[:16]
        with self._lock:
            if doc_id in self._docs:
                return self._docs[doc_id], False

        parsed = parse_pdf(data)
        chunks = chunk_document(parsed)
        if not chunks:
            raise ValueError("The PDF has text, but no usable passages were found.")
        meta = {
            "id": doc_id,
            "filename": filename,
            "title": parsed.title,
            "num_pages": parsed.num_pages,
            "sections": [s.title for s in parsed.sections],
            "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        doc = self._build(meta, chunks)
        (self.data_dir / f"{doc_id}.json").write_text(
            json.dumps({**meta, "chunks": [c.to_dict() for c in chunks]}, ensure_ascii=False),
            encoding="utf-8",
        )
        with self._lock:
            self._docs[doc_id] = doc
        return doc, True

    def get(self, doc_id: str) -> StoredDocument | None:
        return self._docs.get(doc_id)

    def list(self) -> list[StoredDocument]:
        return sorted(self._docs.values(), key=lambda d: d.uploaded_at, reverse=True)

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            doc = self._docs.pop(doc_id, None)
        if doc is None:
            return False
        (self.data_dir / f"{doc_id}.json").unlink(missing_ok=True)
        return True
