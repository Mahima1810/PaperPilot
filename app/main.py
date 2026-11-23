"""PaperPilot API + web UI."""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .answerer import answer_question
from .llm import ChatClient, LLMConfig
from .pdf_parser import PDFParseError
from .store import DocumentStore

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "frontend"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)


def create_app(data_dir: Path | None = None, client: ChatClient | None = None) -> FastAPI:
    app = FastAPI(
        title="PaperPilot",
        description="Ask questions about research papers and get answers cited to the exact section and page.",
        version="0.1.0",
    )
    store = DocumentStore(data_dir or Path(os.getenv("PAPERPILOT_DATA", ROOT / "data")))
    if client is None:
        config = LLMConfig.from_env()
        client = ChatClient(config) if config else None

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "mode": "llm" if client else "extractive",
            "model": client.config.model if client else None,
            "documents": len(store.list()),
        }

    @app.post("/api/documents", status_code=201)
    async def upload(file: UploadFile = File(...)) -> dict:
        name = file.filename or "document.pdf"
        if not name.lower().endswith(".pdf"):
            raise HTTPException(415, "Only PDF files are supported.")
        data = await file.read()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"File is larger than {MAX_UPLOAD_MB} MB.")
        if not data.startswith(b"%PDF"):
            raise HTTPException(415, "This file is not a valid PDF.")
        try:
            doc, created = store.add(name, data)
        except PDFParseError as exc:
            raise HTTPException(422, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {**doc.summary(), "created": created}

    @app.get("/api/documents")
    def list_documents() -> list[dict]:
        return [d.summary() for d in store.list()]

    @app.delete("/api/documents/{doc_id}", status_code=204)
    def delete_document(doc_id: str) -> None:
        if not store.delete(doc_id):
            raise HTTPException(404, "Document not found.")

    @app.post("/api/documents/{doc_id}/ask")
    def ask(doc_id: str, body: AskRequest) -> dict:
        doc = store.get(doc_id)
        if doc is None:
            raise HTTPException(404, "Document not found.")
        hits = doc.retriever.search(body.question, k=body.top_k)
        result = answer_question(body.question, hits, client)
        return {
            "question": body.question,
            "answer": result.answer,
            "mode": result.mode,
            "warning": result.warning,
            "citations": [asdict(c) for c in result.citations],
        }

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
