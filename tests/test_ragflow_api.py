import asyncio
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


def test_thread_capabilities_can_override_and_reset_with_agent_change():
    skill = resource_save("skills", {"name": "Thread skill", "content": "instructions", "enabled": True})
    mcp = resource_save("mcp_servers", {"name": "Thread MCP", "transport": "http", "url": "https://example.invalid/mcp", "enabled": True})
    provider = resource_save("providers", {"name": "Thread provider", "api_key": "test", "default_model": "test"})
    first_agent = resource_save("agents", {
        "name": "First thread agent", "provider_id": provider["id"], "model": "test",
        "skill_ids": [skill["id"]], "mcp_server_ids": [mcp["id"]],
    })
    second_agent = resource_save("agents", {
        "name": "Second thread agent", "provider_id": provider["id"], "model": "test",
        "skill_ids": [], "mcp_server_ids": [],
    })

    with TestClient(main.app) as client:
        thread = client.post("/api/threads", json={"agent_id": first_agent["id"]}).json()
        response = client.patch(f"/api/threads/{thread['id']}", json={
            "capability_overrides": {"skill_ids": [], "mcp_server_ids": [mcp["id"]]},
        })
        assert response.status_code == 200
        assert response.json()["capability_overrides"] == {"skill_ids": [], "mcp_server_ids": [mcp["id"]]}

        response = client.patch(f"/api/threads/{thread['id']}", json={"agent_id": second_agent["id"]})
        assert response.status_code == 200
        assert response.json()["capability_overrides"] == {}


def test_cancel_active_turn_cancels_registered_task():
    async def scenario():
        task = asyncio.create_task(asyncio.sleep(60))
        main.ACTIVE_TURNS["thread-cancel-test"] = {"task": task, "turn_id": "turn-cancel-test"}
        try:
            result = await main.cancel_active_turn("thread-cancel-test")
            await asyncio.sleep(0)
            assert result == {"cancelled": True, "turn_id": "turn-cancel-test"}
            assert task.cancelled()
        finally:
            main.ACTIVE_TURNS.pop("thread-cancel-test", None)

    asyncio.run(scenario())
