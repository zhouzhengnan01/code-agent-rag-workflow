"""Tenant-scoped durable document uploads using the existing task queue."""

import asyncio
import json
import re
from pathlib import Path

from . import db, knowledge
from .knowledge_service import backend_for, upload
from .tasks import append_task_event, enqueue_task, get_task


def _file_path(upload_id):
    if not re.fullmatch(r"upl_[0-9a-f]{16}", upload_id or ""):
        raise knowledge.KnowledgeValidationError("无效的上传记录")
    database = db.tenant_db_path(db.current_tenant()) if db.current_tenant() else Path(db.DB_PATH)
    return database.parent / "knowledge_uploads" / upload_id


def submit(knowledge_base, filename, raw, mime_type):
    if not raw or len(raw) > knowledge.MAX_UPLOAD_BYTES:
        raise knowledge.KnowledgeValidationError(f"文件不能为空，且不能超过 {knowledge.MAX_UPLOAD_BYTES // 1024 // 1024} MB")
    if backend_for(knowledge_base) == "local":
        filename = knowledge.validate_source(filename)
    elif not filename or Path(filename).name != filename or len(filename) > 255:
        raise knowledge.KnowledgeValidationError("无效的文件名")
    upload_id = db.new_id("upl")
    path = _file_path(upload_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    try:
        task = enqueue_task("knowledge_ingest", f"导入 {filename}", {
            "knowledge_id": knowledge_base["id"], "backend": backend_for(knowledge_base),
            "upload_id": upload_id, "source": filename, "mime_type": mime_type,
            "upload_bytes": len(raw),
        }, max_attempts=1)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {"backend": backend_for(knowledge_base), "status": "queued", "task_id": task["id"], "source": filename}


async def execute(task):
    payload = task["payload"]
    def progress(stage, percent, detail):
        append_task_event(task["id"], "document_progress", {"stage": stage, "percent": percent, **detail})
    try:
        base = db.resource_get("knowledge", payload["knowledge_id"])
        if not base or not base.get("enabled", True):
            raise knowledge.KnowledgeValidationError("知识库不存在或已禁用")
        if backend_for(base) != payload["backend"]:
            raise knowledge.KnowledgeValidationError("知识库后端已变更，请重新上传文档")
        progress("reading", 10, {})
        path = _file_path(payload["upload_id"])
        raw = await asyncio.to_thread(path.read_bytes)
        if payload["backend"] == "local":
            source, text, metadata = await asyncio.to_thread(knowledge.decode_upload, payload["source"], raw, payload.get("mime_type"))
            result = await knowledge.ingest(base, source, text, metadata, progress=progress)
            result.update(backend="local", status="done", source=source)
        else:
            progress("submitting", 30, {})
            result = await upload(base, payload["source"], raw, payload.get("mime_type"))
        progress("submitted" if result.get("status") == "processing" else "completed", 100, {"chunks": result.get("chunks", 0)})
        return result
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Retain expected actionable errors, not arbitrary network messages which
        # might include credentials. The queue persists this safe message too.
        message = str(exc) if isinstance(exc, knowledge.KnowledgeError) else f"文档处理失败（{type(exc).__name__}），请检查文件及模型 / 索引配置"
        progress("failed", 0, {"error": message})
        raise knowledge.KnowledgeError(message) from exc


def list_uploads(knowledge_id):
    with db.connect() as connection:
        rows = connection.execute("SELECT t.id,t.status,t.payload,t.result,t.error,t.created_at,t.updated_at,"
                                  "(SELECT e.data FROM task_events e WHERE e.task_id=t.id AND e.type='document_progress' ORDER BY sequence DESC LIMIT 1) AS progress "
                                  "FROM tasks t WHERE t.kind='knowledge_ingest' AND json_extract(t.payload,'$.knowledge_id')=? ORDER BY t.created_at DESC,t.rowid DESC LIMIT 100", (knowledge_id,)).fetchall()
    items = []
    for row in rows:
        payload = json.loads(row["payload"])
        result, progress = json.loads(row["result"] or "{}"), json.loads(row["progress"] or "{}")
        items.append({"task_id": row["id"], "source": payload["source"], "status": row["status"],
                      "stage": progress.get("stage", "queued"), "percent": progress.get("percent", 0),
                      "chunks": result.get("chunks", progress.get("chunks", 0)), "completed_chunks": progress.get("completed_chunks", 0),
                      "error": row["error"] or progress.get("error"), "upload_bytes": payload.get("upload_bytes", 0),
                      "document_id": result.get("document_id"), "result_status": result.get("status"),
                      "created_at": row["created_at"], "updated_at": row["updated_at"]})
    return items


def retry(knowledge_id, task_id):
    task = get_task(task_id)
    if not task or task["kind"] != "knowledge_ingest" or task["payload"].get("knowledge_id") != knowledge_id:
        raise KeyError("上传记录不存在")
    if not _file_path(task["payload"]["upload_id"]).is_file():
        raise knowledge.KnowledgeValidationError("原始文件已丢失，请重新上传")
    with db.connect() as connection:
        changed = connection.execute("UPDATE tasks SET status='queued',attempts=0,error=NULL,result=NULL,available_at=?,updated_at=? WHERE id=? AND status IN ('failed','cancelled')", (db.now(), db.now(), task_id)).rowcount
    if not changed:
        raise knowledge.KnowledgeConflictError("只能重试失败或已取消的上传任务")
    append_task_event(task_id, "document_progress", {"stage": "queued", "percent": 0})
    append_task_event(task_id, "queued", {"retry": True})
    return {"task_id": task_id, "status": "queued"}
