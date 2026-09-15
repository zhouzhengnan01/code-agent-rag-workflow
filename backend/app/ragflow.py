import json
import os
from dataclasses import dataclass

import httpx


class RAGFlowError(RuntimeError):
    pass


class RAGFlowConfigurationError(RAGFlowError):
    pass


@dataclass(frozen=True)
class RAGFlowSettings:
    base_url: str
    api_key: str
    timeout: float


def settings(knowledge=None):
    knowledge = knowledge or {}
    base_url = str(os.getenv("CODEZZN_RAGFLOW_URL", "")).strip().rstrip("/")
    # Credentials are deployment secrets and must not be stored on public knowledge resources.
    api_key = str(os.getenv("CODEZZN_RAGFLOW_API_KEY", "")).strip()
    timeout = float(os.getenv("CODEZZN_RAGFLOW_TIMEOUT", "120"))
    if not base_url:
        raise RAGFlowConfigurationError("RAGFlow URL is not configured")
    if not api_key:
        raise RAGFlowConfigurationError("RAGFlow API key is not configured")
    if not base_url.endswith("/api/v1"):
        base_url += "/api/v1"
    return RAGFlowSettings(base_url, api_key, timeout)


class RAGFlowClient:
    def __init__(self, knowledge=None, transport=None):
        self.config = settings(knowledge)
        self.transport = transport

    def _headers(self):
        return {"Authorization": f"Bearer {self.config.api_key}"}

    async def _request(self, method, path, **kwargs):
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = await client.request(method, self.config.base_url + path, headers=headers, **kwargs)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise RAGFlowError(f"RAGFlow request failed ({type(exc).__name__})") from exc
        if isinstance(payload, dict) and payload.get("code") not in (None, 0):
            raise RAGFlowError(str(payload.get("message") or f"RAGFlow business error {payload.get('code')}"))
        return payload

    async def health(self):
        return await self._request("GET", "/dify/retrieval/health")

    async def create_dataset(self, name, description="", *, chunk_method="naive", parser_config=None, embedding_model=None):
        payload = {
            "name": name,
            "description": description,
            "chunk_method": chunk_method,
            "parser_config": parser_config or {},
        }
        if embedding_model:
            payload["embedding_model"] = embedding_model
        result = await self._request("POST", "/datasets", json=payload)
        return result.get("data") or {}

    async def upload_document(self, dataset_id, filename, raw, mime_type=None):
        files = {"file": (filename, raw, mime_type or "application/octet-stream")}
        result = await self._request("POST", f"/datasets/{dataset_id}/documents", files=files)
        documents = result.get("data") or []
        if isinstance(documents, dict):
            documents = [documents]
        if not documents:
            raise RAGFlowError("RAGFlow returned no uploaded document")
        return documents[0]

    async def start_parse(self, dataset_id, document_ids):
        return await self._request("POST", f"/datasets/{dataset_id}/chunks", json={"document_ids": document_ids})

    async def list_documents(self, dataset_id, document_id=None):
        params = {"id": document_id} if document_id else {"page": 1, "page_size": 100}
        result = await self._request("GET", f"/datasets/{dataset_id}/documents", params=params)
        data = result.get("data") or {}
        if isinstance(data, list):
            return data
        return data.get("docs") or []

    async def delete_documents(self, dataset_id, document_ids):
        return await self._request("DELETE", f"/datasets/{dataset_id}/documents", json={"ids": document_ids})

    async def retrieve(self, dataset_ids, question, *, page_size=5, document_ids=None, config=None):
        config = config or {}
        payload = {
            "question": question,
            "dataset_ids": dataset_ids,
            "document_ids": document_ids or [],
            "page": 1,
            "page_size": int(page_size),
            "similarity_threshold": float(config.get("similarity_threshold", 0.2)),
            "vector_similarity_weight": float(config.get("vector_similarity_weight", 0.3)),
            "knn_top_k": int(config.get("knn_top_k", 1024)),
            "knn_num_candidates": int(config.get("knn_num_candidates", 2048)),
            "rerank_candidates_count": max(int(config.get("rerank_candidates_count", 64)), int(page_size)),
            "highlight": bool(config.get("highlight", True)),
            "use_kg": bool(config.get("use_kg", False)),
            "toc_enhance": bool(config.get("toc_enhance", False)),
            "include_knowledge_compilation": True,
        }
        if config.get("rerank_id"):
            payload["rerank_id"] = config["rerank_id"]
        if config.get("metadata_condition"):
            payload["metadata_condition"] = config["metadata_condition"]
        result = await self._request("POST", "/retrieval", json=payload)
        return (result.get("data") or {}).get("chunks") or []


def normalize_chunk(chunk, knowledge_id=None):
    position = chunk.get("positions") or chunk.get("position") or 0
    if isinstance(position, list):
        position = position[0] if position else 0
    try:
        position = int(position)
    except (TypeError, ValueError):
        position = 0
    score = float(chunk.get("similarity") or chunk.get("score") or 0)
    source = chunk.get("document_keyword") or chunk.get("docnm_kwd") or chunk.get("title") or "RAGFlow document"
    return {
        "id": str(chunk.get("id") or ""),
        "knowledge_id": knowledge_id or str(chunk.get("dataset_id") or chunk.get("kb_id") or ""),
        "document_id": str(chunk.get("document_id") or chunk.get("doc_id") or ""),
        "source": str(source),
        "position": position,
        "content": str(chunk.get("content") or chunk.get("content_with_weight") or ""),
        "metadata": {
            "positions": chunk.get("positions") or [],
            "important_keywords": chunk.get("important_keywords") or chunk.get("important_kwd") or [],
            "highlight": chunk.get("highlight"),
        },
        "score": score,
        "fusion_score": score,
        "vector_score": chunk.get("vector_similarity"),
        "lexical_score": chunk.get("term_similarity"),
        "retrieval": "ragflow-hybrid",
    }
