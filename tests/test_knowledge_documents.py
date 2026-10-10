import asyncio
import io
import json
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import db, knowledge, knowledge_jobs, knowledge_service, main, tasks, workspace


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", tmp_path / "workspace")
    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "false")
    monkeypatch.delenv("CODEZZN_ADMIN_KEY", raising=False)
    monkeypatch.delenv("CODEZZN_LEGACY_OWNER_GITHUB_ID", raising=False)
    monkeypatch.setattr(tasks, "_active_tenants", lambda: [None])
    db.init_db()
    provider = db.resource_save("providers", {"name": "Embedding", "api_key": "test", "base_url": "http://invalid"})
    kb = db.resource_save("knowledge", {"name": "本地测试", "backend": "local", "embedding_provider_id": provider["id"],
                                           "embedding_dimension": 2, "rerank_enabled": False})
    class VectorStore:
        def upsert(self, **kwargs):
            assert kwargs["data"]
        def flush(self, **kwargs):
            pass
    monkeypatch.setattr(knowledge, "_ensure_collection", lambda *args: (VectorStore(), "test_collection"))
    async def embed(provider, texts, model, dimension):
        return [[1.0, 0.0] for _ in texts]
    async def vector_unavailable(*args):
        raise knowledge.KnowledgeError("vectors unavailable")
    monkeypatch.setattr(knowledge, "_embed", embed)
    monkeypatch.setattr(knowledge, "_vector_search", vector_unavailable)
    return kb


def submit(client, kb, name="manual.txt", text="部署口令是 local-workflow-2026。"):
    response = client.post(f"/api/knowledge/{kb['id']}/documents?background=true", files={"file": (name, text.encode(), "text/plain")})
    assert response.status_code == 202, response.text
    return response.json()


def run_one(task_id):
    queue = tasks.PersistentTaskQueue()
    queue.handler = main.execute_persistent_task
    with db.connect() as connection:
        connection.execute("UPDATE tasks SET status='running',attempts=attempts+1 WHERE id=? AND status='queued'", (task_id,))
    asyncio.run(queue._execute(tasks.get_task(task_id), None))


def test_background_import_progress_preview_and_real_lexical_retrieval(store, monkeypatch):
    client = TestClient(main.app)
    def forbidden(*args):
        pytest.fail("Local ingestion must not call RAGFlow")
    monkeypatch.setattr(knowledge_service, "RAGFlowClient", forbidden)
    result = submit(client, store)
    status_url = f"/api/knowledge/{store['id']}/documents/status"
    status = client.get(status_url).json()
    assert status["uploads"][0]["status"] == "queued"
    assert not status["documents"]
    run_one(result["task_id"])
    status = client.get(status_url).json()
    assert status["uploads"][0]["status"] == "completed"
    document = status["documents"][0]
    assert document["status"] == "completed" and document["chunks"] == status["chunk_count"] > 0
    events = tasks.task_events(result["task_id"])
    stages = [item["data"]["stage"] for item in events if item["type"] == "document_progress"]
    assert stages == ["reading", "splitting", "embedding", "embedding", "indexing", "completed"]
    preview = client.get(f"/api/knowledge/{store['id']}/documents/{document['id']}/chunks").json()
    assert preview["total"] == document["chunks"]
    assert "local-workflow-2026" in preview["data"][0]["content"]
    search = client.post("/api/knowledge/search", json={"query": "部署口令", "knowledge_ids": [store["id"]]}).json()
    assert "local-workflow-2026" in search["data"][0]["content"]
    assert "upload_id" not in json.dumps(status) and "api_key" not in json.dumps(status)


def test_failed_embedding_preserves_previous_document_and_retry_replaces_it(store, monkeypatch):
    client = TestClient(main.app)
    first = submit(client, store, text="原始资料旧口令")
    run_one(first["task_id"])
    good_embed = knowledge._embed
    async def fail(*args):
        raise knowledge.KnowledgeError("Embedding 模型不可用，请检查模型名称")
    monkeypatch.setattr(knowledge, "_embed", fail)
    replacement = submit(client, store, text="更新资料新口令")
    run_one(replacement["task_id"])
    status_url = f"/api/knowledge/{store['id']}/documents/status"
    status = client.get(status_url).json()
    assert status["uploads"][0]["status"] == "failed"
    assert "Embedding" in status["uploads"][0]["error"]
    assert status["documents"][0]["revision"] == 1
    document_id = status["documents"][0]["id"]
    preview_url = f"/api/knowledge/{store['id']}/documents/{document_id}/chunks"
    assert client.get(preview_url).json()["data"][0]["content"] == "原始资料旧口令"
    monkeypatch.setattr(knowledge, "_embed", good_embed)
    retry_url = f"/api/knowledge/{store['id']}/uploads/{replacement['task_id']}/retry"
    assert client.post(retry_url).status_code == 200
    assert client.post(retry_url).status_code == 409
    run_one(replacement["task_id"])
    assert client.get(status_url).json()["documents"][0]["revision"] == 2
    assert client.get(preview_url).json()["data"][0]["content"] == "更新资料新口令"


def test_background_upload_is_processed_by_live_queue(store, monkeypatch):
    async def scenario():
        queue = tasks.PersistentTaskQueue()
        monkeypatch.setattr(main, "task_queue", queue)
        await queue.start(main.execute_persistent_task, concurrency=1)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                response = await client.post(f"/api/knowledge/{store['id']}/documents?background=true", files={"file": ("queue.txt", b"queue import test", "text/plain")})
                assert response.status_code == 202
                task_id = response.json()["task_id"]
                for _ in range(100):
                    task = tasks.get_task(task_id)
                    if task["status"] in {"completed", "failed"}:
                        break
                    await asyncio.sleep(.03)
                assert task["status"] == "completed", task["error"]
                status = (await client.get(f"/api/knowledge/{store['id']}/documents/status")).json()
                assert status["documents"][0]["chunks"] > 0
        finally:
            await queue.close()
    asyncio.run(scenario())


def test_upload_limits_and_missing_provider_are_actionable(store, monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(knowledge, "MAX_UPLOAD_BYTES", 32)
    assert client.post(f"/api/knowledge/{store['id']}/documents?background=true", files={"file": ("x.txt", b"x" * 33, "text/plain")}).status_code == 400
    assert client.post(f"/api/knowledge/{store['id']}/documents?background=true", files={"file": ("x.exe", b"x", "application/octet-stream")}).status_code == 400
    assert client.post(f"/api/knowledge/{store['id']}/documents?background=true", files={"file": ("x.txt", b"", "text/plain")}).status_code == 400
    config = client.get(f"/api/knowledge/{store['id']}/upload-config").json()
    assert config["max_upload_bytes"] == 32 and ".docx" in config["extensions"]
    provider_id = store["embedding_provider_id"]
    db.resource_save("providers", {"enabled": False}, provider_id)
    result = submit(client, store, text="valid document")
    run_one(result["task_id"])
    assert "Embedding 提供方" in tasks.get_task(result["task_id"])["error"]


def test_document_preview_and_retry_scope_to_knowledge_base(store):
    client = TestClient(main.app)
    result = submit(client, store)
    run_one(result["task_id"])
    document = knowledge.document_status(store["id"])["documents"][0]
    other = db.resource_save("knowledge", {"name": "other", "backend": "local"})
    assert client.get(f"/api/knowledge/{other['id']}/documents/{document['id']}/chunks").status_code == 404
    assert client.post(f"/api/knowledge/{other['id']}/uploads/{result['task_id']}/retry").status_code == 404
    assert client.get(f"/api/knowledge/{store['id']}/documents/{document['id']}/chunks?offset=-1").status_code == 400
    assert client.get(f"/api/knowledge/{store['id']}/documents/{document['id']}/chunks?limit=101").status_code == 400


def test_upload_source_and_task_are_tenant_scoped(store):
    tenant = "usr_1111111111111111"
    db.ensure_tenant(tenant)
    token = db.use_tenant(tenant)
    try:
        base = db.resource_save("knowledge", {"name": "Tenant", "backend": "local"})
        result = knowledge_jobs.submit(base, "tenant.txt", b"tenant private document", "text/plain")
        task = tasks.get_task(result["task_id"])
        path = knowledge_jobs._file_path(task["payload"]["upload_id"])
        assert tenant in str(path) and path.read_bytes() == b"tenant private document"
        assert len(knowledge_jobs.list_uploads(base["id"])) == 1
    finally:
        db.reset_tenant(token)
    assert tasks.get_task(result["task_id"]) is None
    assert knowledge_jobs.list_uploads(base["id"]) == []
    with pytest.raises(KeyError):
        knowledge_jobs.retry(base["id"], result["task_id"])


def test_docx_and_scanned_pdf_have_explicit_results():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>测试文档</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格资料</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    _, text, metadata = knowledge.decode_upload("manual.docx", raw.getvalue(), knowledge.MIME_TYPES[".docx"])
    assert text == "测试文档\n\n表格资料"
    assert metadata["mime_type"] == knowledge.MIME_TYPES[".docx"]
    with pytest.raises(knowledge.KnowledgeValidationError, match="无法解析"):
        knowledge.decode_upload("bad.docx", b"not a zip")
    from pypdf import PdfWriter
    pdf = PdfWriter()
    pdf.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    pdf.write(output)
    with pytest.raises(knowledge.KnowledgeValidationError, match="OCR"):
        knowledge.decode_upload("scan.pdf", output.getvalue(), "application/pdf")


@pytest.mark.parametrize("status,expected", [(401, "API Key"), (404, "模型名称"), (429, "额度")])
def test_embedding_error_exposes_advice_without_raw_provider_message(monkeypatch, status, expected):
    original = httpx.AsyncClient
    def client(**kwargs):
        return original(transport=httpx.MockTransport(lambda request: httpx.Response(status, json={"error": "sensitive-server-detail"}, request=request)))
    monkeypatch.setattr(knowledge.httpx, "AsyncClient", client)
    with pytest.raises(knowledge.KnowledgeError, match=expected) as failure:
        asyncio.run(knowledge._embed({"base_url": "http://provider", "api_key": "private-key"}, ["text"], "embedding-model", 2))
    assert "private-key" not in str(failure.value) and "sensitive-server-detail" not in str(failure.value)
