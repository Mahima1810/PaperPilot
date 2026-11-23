from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path):
    return TestClient(create_app(data_dir=tmp_path))


def test_upload_ask_delete_flow(tmp_path, sample_pdf_bytes):
    client = make_client(tmp_path)
    assert client.get("/api/health").json()["status"] == "ok"

    resp = client.post("/api/documents", files={"file": ("paper.pdf", sample_pdf_bytes, "application/pdf")})
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["created"] is True and doc["num_pages"] == 2

    again = client.post("/api/documents", files={"file": ("copy.pdf", sample_pdf_bytes, "application/pdf")})
    assert again.json()["created"] is False  # de-duplicated by content hash

    ans = client.post(f"/api/documents/{doc['id']}/ask", json={"question": "What batch size was used?"})
    assert ans.status_code == 200
    body = ans.json()
    assert "32" in body["answer"]
    assert body["citations"][0]["page_start"] >= 1

    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get("/api/documents").json() == []


def test_documents_persist_across_restarts(tmp_path, sample_pdf_bytes):
    make_client(tmp_path).post("/api/documents", files={"file": ("p.pdf", sample_pdf_bytes, "application/pdf")})
    assert len(make_client(tmp_path).get("/api/documents").json()) == 1


def test_rejects_non_pdf(tmp_path):
    resp = make_client(tmp_path).post("/api/documents", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 415


def test_rejects_fake_pdf_extension(tmp_path):
    resp = make_client(tmp_path).post("/api/documents", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert resp.status_code == 415


def test_ask_unknown_document(tmp_path):
    resp = make_client(tmp_path).post("/api/documents/nope/ask", json={"question": "anything here?"})
    assert resp.status_code == 404
