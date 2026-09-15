import os
import unicodedata
from collections import defaultdict
from pathlib import PurePosixPath

from . import knowledge as local
from .db import resource_get
from .ragflow import RAGFlowClient, RAGFlowConfigurationError, normalize_chunk


BACKENDS = {"local", "ragflow"}
DEFAULT_BACKEND = os.getenv("CODEZZN_KNOWLEDGE_BACKEND", "local").strip().lower() or "local"


def backend_for(knowledge):
    # Existing knowledge resources without an explicit backend always remain local.
    # CODEZZN_KNOWLEDGE_BACKEND controls newly created resources only.
    backend = str((knowledge or {}).get("backend") or "local").strip().lower()
    if backend not in BACKENDS:
        raise local.KnowledgeValidationError(f"Unsupported knowledge backend: {backend}")
    return backend


def ragflow_dataset_id(knowledge):
    return str((knowledge or {}).get("ragflow_dataset_id") or "").strip()


async def ensure_remote_dataset(knowledge, *, client=None):
    if backend_for(knowledge) != "ragflow":
        return None
    dataset_id = ragflow_dataset_id(knowledge)
    if dataset_id:
        return dataset_id
    client = client or RAGFlowClient(knowledge)
    dataset = await client.create_dataset(
        knowledge.get("name") or "Codezzn Knowledge",
        knowledge.get("description") or "",
        chunk_method=knowledge.get("chunk_method") or "naive",
        parser_config=knowledge.get("parser_config") or {},
        embedding_model=knowledge.get("ragflow_embedding_model") or None,
    )
    dataset_id = str(dataset.get("id") or "")
    if not dataset_id:
        raise local.KnowledgeError("RAGFlow did not return a dataset ID")
    return dataset_id


async def upload(knowledge, filename, raw, mime_type=None, *, client=None):
    backend = backend_for(knowledge)
    if backend == "local":
        source, text, upload_meta = local.decode_upload(filename, raw, mime_type)
        result = await local.ingest(knowledge, source, text, upload_meta)
        return {"backend": backend, "status": "done", "source": source, "characters": len(text), **result}
    source = unicodedata.normalize("NFC", str(filename or "").replace("\\", "/")).strip()
    path = PurePosixPath(source)
    if not source or path.is_absolute() or ".." in path.parts or len(source.encode("utf-8")) > 1024:
        raise local.KnowledgeValidationError("Invalid RAGFlow filename")
    if any(ord(char) < 32 for char in source):
        raise local.KnowledgeValidationError("Invalid RAGFlow filename")
    if not raw:
        raise local.KnowledgeValidationError("Document is empty")
    if len(raw) > local.MAX_UPLOAD_BYTES:
        raise local.KnowledgeValidationError("Upload exceeds the configured size limit")
    client = client or RAGFlowClient(knowledge)
    dataset_id = ragflow_dataset_id(knowledge)
    if not dataset_id:
        raise RAGFlowConfigurationError("RAGFlow dataset is not bound; save or provision the knowledge base first")
    document = await client.upload_document(dataset_id, source, raw, mime_type)
    document_id = str(document.get("id") or "")
    if not document_id:
        raise local.KnowledgeError("RAGFlow did not return a document ID")
    await client.start_parse(dataset_id, [document_id])
    return {
        "backend": backend,
        "status": "processing",
        "source": source,
        "document_id": document_id,
        "ragflow_dataset_id": dataset_id,
        "run": document.get("run", "UNSTART"),
        "chunks": int(document.get("chunk_count") or 0),
    }


async def status(knowledge, document_id=None, *, client=None):
    if backend_for(knowledge) == "local":
        return {"backend": "local", **local.document_status(knowledge["id"])}
    client = client or RAGFlowClient(knowledge)
    dataset_id = ragflow_dataset_id(knowledge)
    if not dataset_id:
        raise RAGFlowConfigurationError("RAGFlow dataset is not configured")
    documents = await client.list_documents(dataset_id, document_id)
    return {
        "backend": "ragflow",
        "ragflow_dataset_id": dataset_id,
        "documents": documents,
        "document_count": len(documents),
        "processing": sum(str(item.get("run", "")).upper() in {"1", "RUNNING", "5", "SCHEDULE"} for item in documents),
        "failed": sum(str(item.get("run", "")).upper() in {"4", "FAIL"} for item in documents),
    }


async def search(query, knowledge_ids, limit=5, *, filters=None, candidate_k=None, top_k=None, source_cap=None, diagnostics=None, clients=None):
    diag = diagnostics if diagnostics is not None else {}
    if not knowledge_ids:
        diag.update(status="no_knowledge_scope", backends={})
        return []
    knowledge_bases = [resource_get("knowledge", item) for item in dict.fromkeys(knowledge_ids)]
    knowledge_bases = [item for item in knowledge_bases if item and item.get("enabled")]
    groups = defaultdict(list)
    for item in knowledge_bases:
        groups[backend_for(item)].append(item)
    results = []
    backend_diag = {}
    if groups.get("local"):
        local_diag = {}
        local_ids = [item["id"] for item in groups["local"]]
        local_results = await local.search(
            query,
            local_ids,
            limit,
            filters=filters,
            candidate_k=candidate_k,
            top_k=top_k,
            source_cap=source_cap,
            diagnostics=local_diag,
        )
        results.extend(local_results)
        backend_diag["local"] = local_diag
    if groups.get("ragflow"):
        remote_results = []
        remote_errors = []
        for item in groups["ragflow"]:
            dataset_id = ragflow_dataset_id(item)
            if not dataset_id:
                remote_errors.append({"knowledge_id": item["id"], "error": "dataset_not_configured"})
                continue
            try:
                client = (clients or {}).get(item["id"]) if clients else None
                client = client or RAGFlowClient(item)
                chunks = await client.retrieve(
                    [dataset_id],
                    query,
                    page_size=max(int(limit), 1),
                    config=item.get("retrieval_config") or item,
                )
                remote_results.extend(normalize_chunk(chunk, item["id"]) for chunk in chunks)
            except Exception as exc:
                remote_errors.append({"knowledge_id": item["id"], "error": type(exc).__name__})
        results.extend(remote_results)
        backend_diag["ragflow"] = {"status": "degraded" if remote_errors else "ok", "hits": len(remote_results), "errors": remote_errors}
    results.sort(key=lambda item: (-float(item.get("score") or 0), str(item.get("id") or "")))
    diag.update(status="degraded" if any(value.get("status") == "degraded" for value in backend_diag.values()) else "ok", backends=backend_diag, returned=min(len(results), int(limit)))
    return results[: int(limit)]


async def reindex(knowledge, document_id=None, *, client=None):
    if backend_for(knowledge) == "local":
        return await local.reindex(knowledge, document_id)
    if not document_id:
        raise local.KnowledgeValidationError("RAGFlow reindex requires document_id")
    client = client or RAGFlowClient(knowledge)
    dataset_id = ragflow_dataset_id(knowledge)
    await client.start_parse(dataset_id, [document_id])
    return {"ok": True, "backend": "ragflow", "status": "processing", "document_id": document_id}


async def delete_document(knowledge, document_id, *, client=None):
    if backend_for(knowledge) == "local":
        raise local.KnowledgeValidationError("Local document deletion is not exposed by this endpoint")
    client = client or RAGFlowClient(knowledge)
    await client.delete_documents(ragflow_dataset_id(knowledge), [document_id])
    return {"deleted": True, "backend": "ragflow", "document_id": document_id}


async def health(knowledge, *, client=None):
    if backend_for(knowledge) == "local":
        return local.rag_status()
    client = client or RAGFlowClient(knowledge)
    result = await client.health()
    return {"ok": True, "backend": "ragflow", "data": result.get("data") if isinstance(result, dict) else result}
