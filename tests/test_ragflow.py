import asyncio
import os

os.environ["CODEZZN_DATA_DIR"] = "/tmp/codezzn-ragflow-test"

import httpx

from backend.app import knowledge_service
from backend.app.knowledge_eval import evaluate
from backend.app.ragflow import RAGFlowClient, normalize_chunk


def test_ragflow_client_normalizes_url_and_retrieval_payload(monkeypatch):
    monkeypatch.setenv("CODEZZN_RAGFLOW_URL", "http://ragflow:9380")
    monkeypatch.setenv("CODEZZN_RAGFLOW_API_KEY", "secret")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["payload"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"code": 0, "data": {"chunks": [{"id": "c1", "content": "answer", "document_keyword": "guide.md", "similarity": 0.9}]}})

    client = RAGFlowClient(transport=httpx.MockTransport(handler))
    chunks = asyncio.run(client.retrieve(["dataset-1"], "hello", page_size=4))
    assert seen["url"] == "http://ragflow:9380/api/v1/retrieval"
    assert seen["authorization"] == "Bearer secret"
    assert seen["payload"]["knn_top_k"] == 1024
    assert seen["payload"]["rerank_candidates_count"] == 64
    assert chunks[0]["document_keyword"] == "guide.md"


def test_ragflow_business_error_is_rejected(monkeypatch):
    monkeypatch.setenv("CODEZZN_RAGFLOW_URL", "http://ragflow")
    monkeypatch.setenv("CODEZZN_RAGFLOW_API_KEY", "secret")
    client = RAGFlowClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 102, "message": "bad dataset"})))
    try:
        asyncio.run(client.retrieve(["missing"], "hello"))
        assert False, "business errors must fail"
    except Exception as exc:
        assert "bad dataset" in str(exc)


def test_normalize_chunk_preserves_scores_and_source():
    item = normalize_chunk({
        "id": "chunk",
        "document_id": "document",
        "document_keyword": "manual.pdf",
        "content": "evidence",
        "similarity": 0.8,
        "term_similarity": 0.7,
        "vector_similarity": 0.9,
        "positions": [2],
    }, "knowledge")
    assert item["source"] == "manual.pdf"
    assert item["position"] == 2
    assert item["score"] == 0.8
    assert item["lexical_score"] == 0.7
    assert item["vector_score"] == 0.9
    assert item["retrieval"] == "ragflow-hybrid"


def test_existing_knowledge_defaults_to_local(monkeypatch):
    monkeypatch.setenv("CODEZZN_KNOWLEDGE_BACKEND", "ragflow")
    assert knowledge_service.backend_for({"id": "legacy"}) == "local"
    assert knowledge_service.backend_for({"backend": "ragflow"}) == "ragflow"


def test_upload_to_ragflow_accepts_ragflow_document_types():
    class Client:
        async def upload_document(self, dataset_id, filename, raw, mime_type):
            return {"id": "doc-1", "run": "UNSTART", "chunk_count": 0}

        async def start_parse(self, dataset_id, document_ids):
            return None

    result = asyncio.run(knowledge_service.upload(
        {"id": "kb", "backend": "ragflow", "ragflow_dataset_id": "dataset-1"},
        "manual.docx",
        b"not-decoded-by-codezzn",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        client=Client(),
    ))
    assert result["source"] == "manual.docx"


def test_upload_to_ragflow_starts_async_parse():
    calls = []

    class Client:
        async def upload_document(self, dataset_id, filename, raw, mime_type):
            calls.append(("upload", dataset_id, filename, raw, mime_type))
            return {"id": "doc-1", "run": "UNSTART", "chunk_count": 0}

        async def start_parse(self, dataset_id, document_ids):
            calls.append(("parse", dataset_id, document_ids))

    result = asyncio.run(knowledge_service.upload(
        {"id": "kb", "backend": "ragflow", "ragflow_dataset_id": "dataset-1"},
        "guide.md",
        b"# Guide",
        "text/markdown",
        client=Client(),
    ))
    assert result["status"] == "processing"
    assert calls[0][0] == "upload"
    assert calls[1] == ("parse", "dataset-1", ["doc-1"])


def test_mixed_backend_search_merges_results(monkeypatch):
    resources = {
        "local-kb": {"id": "local-kb", "backend": "local", "enabled": True},
        "remote-kb": {"id": "remote-kb", "backend": "ragflow", "ragflow_dataset_id": "dataset", "enabled": True},
    }

    async def local_search(*args, **kwargs):
        kwargs["diagnostics"].update(status="ok")
        return [{"id": "l", "source": "local.md", "content": "local", "score": 0.4}]

    class Client:
        async def retrieve(self, *args, **kwargs):
            return [{"id": "r", "document_keyword": "remote.md", "content": "remote", "similarity": 0.9}]

    monkeypatch.setattr(knowledge_service, "resource_get", lambda kind, item_id: resources.get(item_id))
    monkeypatch.setattr(knowledge_service.local, "search", local_search)
    diagnostics = {}
    results = asyncio.run(knowledge_service.search(
        "query",
        ["local-kb", "remote-kb"],
        2,
        diagnostics=diagnostics,
        clients={"remote-kb": Client()},
    ))
    assert [item["source"] for item in results] == ["remote.md", "local.md"]
    assert set(diagnostics["backends"]) == {"local", "ragflow"}


def test_evaluation_computes_hit_mrr_and_recall(monkeypatch):
    async def fake_search(query, ids, top_k, diagnostics=None):
        diagnostics.update(status="ok")
        source = "expected.md" if ids == ["local"] else "other.md"
        return [{"source": source, "score": 0.8}]

    monkeypatch.setattr("backend.app.knowledge_eval.search", fake_search)
    result = asyncio.run(evaluate({
        "local_knowledge_ids": ["local"],
        "ragflow_knowledge_ids": ["remote"],
        "top_k": 3,
        "cases": [{"query": "q", "expected_sources": ["expected.md"]}],
    }))
    assert result["summary"]["local"]["hit_at_k"] == 1
    assert result["summary"]["local"]["mrr"] == 1
    assert result["summary"]["ragflow"]["hit_at_k"] == 0
