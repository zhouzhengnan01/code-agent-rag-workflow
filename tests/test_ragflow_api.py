import os

os.environ["CODEZZN_DATA_DIR"] = "/tmp/codezzn-ragflow-api-test"

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.db import init_db, resource_save


def test_ragflow_provision_upload_status_search_flow(monkeypatch):
    init_db()
    knowledge = resource_save("knowledge", {
        "name": "Remote test",
        "backend": "ragflow",
        "enabled": True,
    })

    async def provision(item):
        return "dataset-1"

    async def upload(item, filename, raw, mime_type):
        assert item["ragflow_dataset_id"] == "dataset-1"
        return {"backend": "ragflow", "status": "processing", "source": filename, "document_id": "doc-1", "run": "UNSTART", "chunks": 0}

    async def status(item, document_id=None):
        return {"backend": "ragflow", "documents": [{"id": "doc-1", "name": "guide.md", "run": "DONE", "chunk_count": 1}]}

    async def search(query, ids, limit, **kwargs):
        kwargs["diagnostics"].update(status="ok", backends={"ragflow": {"status": "ok"}})
        return [{"id": "c1", "source": "guide.md", "position": 0, "content": "answer", "score": 0.9, "retrieval": "ragflow-hybrid"}]

    monkeypatch.setattr(main, "ensure_remote_dataset", provision)
    monkeypatch.setattr(main, "upload_knowledge_document", upload)
    monkeypatch.setattr(main, "knowledge_status", status)
    monkeypatch.setattr(main, "search_knowledge_service", search)

    with TestClient(main.app) as client:
        response = client.post(f"/api/knowledge/{knowledge['id']}/ragflow/provision")
        assert response.status_code == 200
        assert response.json()["ragflow_dataset_id"] == "dataset-1"

        response = client.post(
            f"/api/knowledge/{knowledge['id']}/documents",
            files={"file": ("guide.md", b"# Guide", "text/markdown")},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "processing"

        response = client.get(f"/api/knowledge/{knowledge['id']}/documents/status")
        assert response.json()["documents"][0]["run"] == "DONE"

        response = client.post("/api/knowledge/search", json={"query": "guide", "knowledge_ids": [knowledge["id"]], "limit": 5})
        assert response.status_code == 200
        assert response.json()["data"][0]["retrieval"] == "ragflow-hybrid"


def test_evaluation_endpoint_rejects_missing_backend_ids():
    with TestClient(main.app) as client:
        response = client.post("/api/knowledge/evaluate", json={"cases": [{"query": "q"}]})
        assert response.status_code == 400
