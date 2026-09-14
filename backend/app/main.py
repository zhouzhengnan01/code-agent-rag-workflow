import json
import os
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from datetime import datetime
import asyncio
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader

from .agent import persist_event, run_agent
from .db import connect, init_db, migrate_bailian_providers, new_id, now, resource_delete, resource_get, resource_list, resource_save, seed_defaults
from .knowledge import KnowledgeConflictError, KnowledgeError, KnowledgeValidationError, decode_upload, document_status, drop_knowledge_index, ingest, rag_status, reindex, search
from .mcp import mcp_manager
from .model import BAILIAN_PRESETS, normalize_provider, public_provider, test_provider
from .sandbox import sandbox_status
from .workflows import create_run


THREAD_LOCKS = {}
THREAD_LOCKS_GUARD = asyncio.Lock()


async def thread_lock(thread_id):
    async with THREAD_LOCKS_GUARD:
        return THREAD_LOCKS.setdefault(thread_id, asyncio.Lock())


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
RESOURCE_KINDS = {"agents", "skills", "providers", "mcp_servers", "knowledge", "workflows"}
app = FastAPI(title="Codezzn", version="0.1.0", description="可部署的智能体开发与运行平台")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/assets", StaticFiles(directory=WEB), name="assets")


@app.on_event("startup")
def startup():
    init_db()
    seed_defaults()
    migrate_bailian_providers()


@app.on_event("shutdown")
async def shutdown():
    await mcp_manager.close()


@app.middleware("http")
async def auth(request: Request, call_next):
    key = os.getenv("CODEZZN_ADMIN_KEY")
    if key and request.url.path not in ("/healthz", "/", "/workbench.html") and not request.url.path.startswith("/assets/"):
        supplied = request.headers.get("X-Codezzn-Key") or request.query_params.get("api_key")
        if supplied != key:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/")
@app.get("/workbench.html")
def workbench():
    return FileResponse(WEB / "workbench.html")


@app.get("/healthz")
def health():
    return {"status": "ok", "name": "codezzn", "version": app.version}


def valid_kind(kind):
    if kind not in RESOURCE_KINDS:
        raise HTTPException(404, "未知资源类型")


@app.get("/api/resources/{kind}")
def list_resources(kind: str):
    valid_kind(kind)
    data = resource_list(kind)
    if kind == "providers":
        data = [public_provider(item) for item in data]
    return {"data": data}


@app.post("/api/resources/{kind}")
def create_resource(kind: str, payload: dict = Body(...)):
    valid_kind(kind)
    if kind == "providers":
        return public_provider(resource_save(kind, normalize_provider(payload)))
    return resource_save(kind, payload)


@app.get("/api/resources/{kind}/{item_id}")
def get_resource(kind: str, item_id: str):
    valid_kind(kind)
    result = resource_get(kind, item_id)
    if not result:
        raise HTTPException(404, "资源不存在")
    return public_provider(result) if kind == "providers" else result


@app.put("/api/resources/{kind}/{item_id}")
def update_resource(kind: str, item_id: str, payload: dict = Body(...)):
    valid_kind(kind)
    existing = resource_get(kind, item_id)
    if not existing:
        raise HTTPException(404, "资源不存在")
    if kind == "providers":
        supplied_key = str(payload.get("api_key") or "")
        if not supplied_key or supplied_key.startswith("••••"):
            payload["api_key"] = existing.get("api_key", "")
        return public_provider(resource_save(kind, normalize_provider(payload), item_id))
    return resource_save(kind, payload, item_id)


@app.delete("/api/resources/{kind}/{item_id}")
def delete_resource(kind: str, item_id: str):
    valid_kind(kind)
    if kind == "knowledge":
        drop_knowledge_index(item_id)
    return {"deleted": resource_delete(kind, item_id)}


@app.get("/api/rag/status")
def get_rag_status():
    return rag_status()


@app.get("/api/sandbox/status")
async def get_sandbox_status():
    if not os.getenv("CODEZZN_ADMIN_KEY"):
        raise HTTPException(503, "Set CODEZZN_ADMIN_KEY to enable authenticated sandbox status")
    try:
        return await sandbox_status()
    except RuntimeError as exc:
        raise HTTPException(503, "Sandbox backend unavailable") from exc


@app.get("/api/provider-presets")
def provider_presets():
    return {"data": BAILIAN_PRESETS}


@app.post("/api/providers/{provider_id}/test")
async def test_provider_endpoint(provider_id: str, payload: dict = Body(default={})):
    provider = resource_get("providers", provider_id)
    if not provider:
        raise HTTPException(404, "模型提供方不存在")
    try:
        return await test_provider(provider, payload.get("model"))
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/skills/import")
async def import_skill(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8", errors="replace")
    name = Path(file.filename or "skill").stem
    if file.filename and file.filename.upper() == "SKILL.MD":
        for line in content.splitlines():
            if line.startswith("# "):
                name = line[2:].strip()
                break
    return resource_save("skills", {"name": name, "description": "Imported SKILL.md", "content": content, "enabled": True})


@app.post("/api/knowledge/{knowledge_id}/documents")
async def upload_document(knowledge_id: str, file: UploadFile = File(...)):
    if not resource_get("knowledge", knowledge_id):
        raise HTTPException(404, "知识库不存在")
    raw = await file.read()
    filename = file.filename or "document.txt"
    try:
        filename, text, upload_meta = decode_upload(filename, raw, file.content_type)
        knowledge = resource_get("knowledge", knowledge_id)
        result = await ingest(knowledge, filename, text, upload_meta)
    except KnowledgeValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KnowledgeConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except KnowledgeError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Document indexing failed") from exc
    return {"source": filename, "characters": len(text), **result}


@app.get("/api/knowledge/{knowledge_id}/documents/status")
def knowledge_document_status(knowledge_id: str):
    if not resource_get("knowledge", knowledge_id):
        raise HTTPException(404, "知识库不存在")
    return document_status(knowledge_id)


@app.post("/api/knowledge/{knowledge_id}/reindex")
async def reindex_knowledge(knowledge_id: str, payload: dict = Body(default={} )):
    knowledge = resource_get("knowledge", knowledge_id)
    if not knowledge:
        raise HTTPException(404, "知识库不存在")
    try:
        return await reindex(knowledge, payload.get("document_id"))
    except KnowledgeValidationError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/knowledge/search")
async def search_knowledge(payload: dict = Body(...)):
    knowledge_ids = payload.get("knowledge_ids") or []
    if not knowledge_ids:
        raise HTTPException(400, "必须明确指定至少一个知识库")
    diagnostics = {}
    try:
        data = await search(payload.get("query", ""), knowledge_ids, min(int(payload.get("limit", 5)), 20),
                             filters=payload.get("filters"), candidate_k=payload.get("candidate_k"), top_k=payload.get("top_k"),
                             source_cap=payload.get("source_cap"), diagnostics=diagnostics)
    except KnowledgeValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"data": data, "diagnostics": diagnostics}


@app.post("/api/mcp_servers/{server_id}/test")
async def test_mcp(server_id: str):
    server = resource_get("mcp_servers", server_id)
    if not server:
        raise HTTPException(404, "MCP 服务不存在")
    try:
        tools = await mcp_manager.list_tools(server)
        return {"ok": True, "tools": tools}
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/threads/{thread_id}/events")
def list_turn_events(thread_id: str, turn_id: str = "", since: int = 0):
    with connect() as db:
        query = "SELECT * FROM turn_events WHERE thread_id=? AND sequence>?"
        params = [thread_id, since]
        if turn_id:
            query += " AND turn_id=?"
            params.append(turn_id)
        rows = db.execute(query + " ORDER BY created_at, sequence", params).fetchall()
    return {"data": [{**dict(row), "data": json.loads(row["data"])} for row in rows]}


@app.post("/api/workflows/{workflow_id}/run")
async def run_workflow_endpoint(workflow_id: str, payload: dict = Body(...)):
    workflow = resource_get("workflows", workflow_id)
    if not workflow:
        raise HTTPException(404, "工作流不存在")
    return await create_run(workflow, payload.get("input", ""))


@app.get("/api/workflow-runs")
def workflow_runs():
    with connect() as db:
        rows = db.execute("SELECT * FROM workflow_runs ORDER BY created_at DESC LIMIT 100").fetchall()
    data = []
    for row in rows:
        item = dict(row)
        for key in ("input", "output", "trace"):
            item[key] = json.loads(item[key]) if item[key] is not None else None
        data.append(item)
    return {"data": data}


@app.post("/api/threads")
def create_thread(payload: dict = Body(default={})):
    thread_id, timestamp = new_id("thr"), now()
    with connect() as db:
        db.execute("INSERT INTO threads(id,name,agent_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", (thread_id, payload.get("name", "新对话"), payload.get("agent_id"), "idle", timestamp, timestamp))
    return {"id": thread_id, "name": payload.get("name", "新对话"), "agent_id": payload.get("agent_id"), "status": "idle", "created_at": timestamp, "updated_at": timestamp}


@app.get("/api/threads")
def list_threads(archived: bool = False):
    with connect() as db:
        rows = db.execute("SELECT * FROM threads WHERE archived=? ORDER BY updated_at DESC", (1 if archived else 0,)).fetchall()
    return {"data": [dict(row) for row in rows]}


@app.post("/api/threads/{thread_id}/fork")
def fork_thread(thread_id: str, payload: dict = Body(default={} )):
    with connect() as db:
        source = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        messages = db.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY created_at", (thread_id,)).fetchall()
    if not source:
        raise HTTPException(404, "对话不存在")
    new_thread, timestamp = new_id("thr"), now()
    with connect() as db:
        db.execute("INSERT INTO threads(id,name,agent_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", (new_thread, payload.get("name") or f"{source['name']} (fork)", source["agent_id"], "idle", timestamp, timestamp))
        for message in messages:
            db.execute("INSERT INTO messages(id,thread_id,turn_id,role,type,content,meta,created_at) VALUES(?,?,?,?,?,?,?,?)", (new_id("msg"), new_thread, message["turn_id"], message["role"], message["type"], message["content"], message["meta"], message["created_at"]))
    return {"id": new_thread, "name": payload.get("name") or f"{source['name']} (fork)", "agent_id": source["agent_id"], "status": "idle"}


@app.get("/api/threads/{thread_id}")
def read_thread(thread_id: str):
    with connect() as db:
        thread = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        messages = db.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY created_at", (thread_id,)).fetchall()
    if not thread:
        raise HTTPException(404, "对话不存在")
    result = dict(thread)
    result["messages"] = [{**dict(row), "meta": json.loads(row["meta"])} for row in messages]
    return result


@app.patch("/api/threads/{thread_id}")
def update_thread(thread_id: str, payload: dict = Body(...)):
    updates, values = [], []
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "会话名称不能为空")
        if len(name) > 80:
            raise HTTPException(400, "会话名称不能超过 80 个字符")
        updates.append("name=?")
        values.append(name)
    if "archived" in payload:
        if not isinstance(payload["archived"], bool):
            raise HTTPException(400, "archived 必须是布尔值")
        updates.append("archived=?")
        values.append(1 if payload["archived"] else 0)
    if not updates:
        raise HTTPException(400, "没有可更新的会话字段")
    updates.append("updated_at=?")
    values.append(now())
    values.append(thread_id)
    with connect() as db:
        cur = db.execute(f"UPDATE threads SET {', '.join(updates)} WHERE id=?", values)
        thread = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
    if not cur.rowcount or not thread:
        raise HTTPException(404, "会话不存在")
    return dict(thread)


@app.get("/api/threads/{thread_id}/approvals")
def list_approvals(thread_id: str, status: str = "pending"):
    with connect() as db:
        rows = db.execute("SELECT * FROM approvals WHERE thread_id=? AND status=? ORDER BY created_at", (thread_id, status)).fetchall()
    return {"data": [{**dict(row), "arguments": json.loads(row["arguments"])} for row in rows]}


@app.get("/api/threads/{thread_id}/approvals/inbox")
def approval_inbox(thread_id: str):
    return list_approvals(thread_id, "pending")


@app.post("/api/approvals/{approval_id}")
def resolve_approval(approval_id: str, payload: dict = Body(...)):
    decision = payload.get("decision")
    if decision not in ("approved", "denied"):
        raise HTTPException(400, "decision 必须是 approved 或 denied")
    with connect() as db:
        cur = db.execute("UPDATE approvals SET status=?,resolution=?,resolved_at=? WHERE id=? AND status='pending'", (decision, payload.get("reason", decision), now(), approval_id))
        row = db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    if not row:
        raise HTTPException(404, "审批不存在")
    if not cur.rowcount:
        raise HTTPException(409, "审批已处理")
    return {**dict(row), "arguments": json.loads(row["arguments"])}


@app.post("/api/threads/{thread_id}/resume")
async def resume_thread(thread_id: str, payload: dict = Body(...)):
    return await start_turn(thread_id, payload)


@app.delete("/api/threads/{thread_id}")
def delete_thread(thread_id: str):
    with connect() as db:
        cur = db.execute("DELETE FROM threads WHERE id=?", (thread_id,))
    if not cur.rowcount:
        raise HTTPException(404, "会话不存在")
    return {"deleted": True}


@app.post("/api/threads/{thread_id}/turns/stream")
async def stream_turn(request: Request, thread_id: str, payload: dict = Body(...)):
    last_event_id = request.headers.get("Last-Event-ID")
    with connect() as db:
        thread = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        history = db.execute("SELECT role,content FROM messages WHERE thread_id=? ORDER BY created_at", (thread_id,)).fetchall()
    if not thread: raise HTTPException(404, "对话不存在")
    agent_id, content = payload.get("agent_id") or thread["agent_id"], payload.get("content", "").strip()
    agent = resource_get("agents", agent_id)
    if not agent or not content: raise HTTPException(400, "请选择有效的智能体并提供消息")
    lock = await thread_lock(thread_id)
    if lock.locked():
        raise HTTPException(409, "该会话已有任务正在运行")
    await lock.acquire()
    turn_id, timestamp = new_id("turn"), now()
    with connect() as db:
        db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,created_at) VALUES(?,?,?,?,?,?)", (new_id("msg"), thread_id, turn_id, "user", content, timestamp))
        db.execute("UPDATE threads SET agent_id=?,status='running',updated_at=? WHERE id=?", (agent_id, timestamp, thread_id))
    queue = asyncio.Queue()
    event_sequence = 0
    async def emit(event):
        nonlocal event_sequence
        event_sequence += 1
        persist_event(event, thread_id, turn_id, event_sequence)
        await queue.put({**event, "sequence": event_sequence})
    async def produce():
        try:
            result = await run_agent(agent, [dict(item) for item in history], content, emit, streaming=True, thread_id=thread_id, turn_id=turn_id)
            with connect() as db:
                db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?,?)", (new_id("msg"), thread_id, turn_id, "assistant", result["content"], json.dumps({"events": result["events"], "usage": result["usage"], "runtime": result["runtime"], "sources": result["sources"]}, ensure_ascii=False), now()))
                db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?", (now(), thread_id))
            await queue.put({"type": "turn_result", "turn_id": turn_id, **{key: result[key] for key in ("content", "usage", "runtime", "sources")}})
        except Exception as exc:
            with connect() as db: db.execute("UPDATE threads SET status='error',updated_at=? WHERE id=?", (now(), thread_id))
            await queue.put({"type": "turn_error", "reason": type(exc).__name__})
        finally:
            with connect() as db:
                db.execute("UPDATE threads SET status=CASE WHEN status='running' THEN 'error' ELSE status END,updated_at=? WHERE id=?", (now(), thread_id))
            lock.release()
            await queue.put(None)
    async def body():
        task = asyncio.create_task(produce())
        try:
            while True:
                if await request.is_disconnected():
                    if not task.done():
                        task.cancel()
                    break
                event = await queue.get()
                if event is None: break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            if not task.done(): task.cancel()
    return StreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@app.post("/api/threads/{thread_id}/turns")
async def start_turn(thread_id: str, payload: dict = Body(...)):
    with connect() as db:
        thread = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        history = db.execute("SELECT role,content FROM messages WHERE thread_id=? ORDER BY created_at", (thread_id,)).fetchall()
    if not thread:
        raise HTTPException(404, "对话不存在")
    agent_id = payload.get("agent_id") or thread["agent_id"]
    agent = resource_get("agents", agent_id)
    if not agent:
        raise HTTPException(400, "请选择有效的智能体")
    content = payload.get("content", "").strip()
    if not content:
        raise HTTPException(400, "消息不能为空")
    lock = await thread_lock(thread_id)
    if lock.locked():
        raise HTTPException(409, "该会话已有任务正在运行")
    await lock.acquire()
    turn_id, timestamp = new_id("turn"), now()
    with connect() as db:
        db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,created_at) VALUES(?,?,?,?,?,?)", (new_id("msg"), thread_id, turn_id, "user", content, timestamp))
        db.execute("UPDATE threads SET agent_id=?,status='running',updated_at=? WHERE id=?", (agent_id, timestamp, thread_id))
    try:
        result = await run_agent(agent, [dict(item) for item in history], content, thread_id=thread_id, turn_id=turn_id)
        with connect() as db:
            db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?,?)", (new_id("msg"), thread_id, turn_id, "assistant", result["content"], json.dumps({"events": result["events"], "usage": result["usage"], "runtime": result["runtime"], "sources": result["sources"]}, ensure_ascii=False), now()))
            db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?", (now(), thread_id))
        return {"turn_id": turn_id, **result}
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE threads SET status='error',updated_at=? WHERE id=?", (now(), thread_id))
        raise HTTPException(502, str(exc))
    finally:
        lock.release()
