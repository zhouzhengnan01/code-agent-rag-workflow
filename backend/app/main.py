import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from datetime import datetime
import asyncio
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader

from .agent import persist_event, run_agent
from .capabilities import ROLE_TEMPLATES
from .db import connect, init_db, migrate_bailian_providers, new_id, now, resource_delete, resource_get, resource_list, resource_save, seed_defaults
from .knowledge import KnowledgeConflictError, KnowledgeError, KnowledgeValidationError, drop_knowledge_index, rag_status
from .knowledge_eval import evaluate as evaluate_knowledge_backends
from .knowledge_service import delete_document as delete_knowledge_document, ensure_remote_dataset, health as knowledge_health, reindex as reindex_knowledge_service, search as search_knowledge_service, status as knowledge_status, upload as upload_knowledge_document
from .ragflow import RAGFlowError
from .mcp import mcp_manager
from .memory import delete_memory, get_memory, list_memories, save_memory, search_memories
from .model import BAILIAN_PRESETS, normalize_provider, public_provider, test_provider
from .sandbox import sandbox_status
from .tasks import cancel_task, enqueue_task, get_task, list_tasks, task_events, task_queue
from .workflows import create_run


THREAD_LOCKS = {}
THREAD_LOCKS_GUARD = asyncio.Lock()
ACTIVE_TURNS = {}


async def thread_lock(thread_id):
    async with THREAD_LOCKS_GUARD:
        return THREAD_LOCKS.setdefault(thread_id, asyncio.Lock())


def _thread_payload(row):
    value = dict(row)
    raw = value.pop("capability_overrides", "{}") or "{}"
    try:
        value["capability_overrides"] = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        value["capability_overrides"] = {}
    return value


def _capability_ids(value, kind):
    if not isinstance(value, list) or len(value) > 100 or any(not isinstance(item, str) for item in value):
        raise HTTPException(400, f"{kind} 必须是最多 100 个 ID 的数组")
    result = list(dict.fromkeys(value))
    available = {item["id"] for item in resource_list(kind) if item.get("enabled")}
    if any(item not in available for item in result):
        raise HTTPException(400, f"包含不可用的 {kind} ID")
    return result


def _agent_for_thread(agent, thread):
    scoped = dict(agent)
    raw = thread["capability_overrides"] if "capability_overrides" in thread.keys() else "{}"
    try:
        overrides = json.loads(raw or "{}") if isinstance(raw, str) else (raw or {})
    except (TypeError, json.JSONDecodeError):
        overrides = {}
    for key in ("skill_ids", "mcp_server_ids"):
        if isinstance(overrides.get(key), list):
            scoped[key] = list(dict.fromkeys(overrides[key]))
    return scoped


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
RESOURCE_KINDS = {"agents", "agent_teams", "skills", "providers", "mcp_servers", "knowledge", "workflows"}


async def execute_persistent_task(task):
    payload = task.get("payload") or {}
    if task["kind"] in {"agent", "subagent"}:
        agent = resource_get("agents", payload.get("agent_id"))
        if not agent:
            raise ValueError("后台任务引用的智能体不存在")
        subagent_run_id = payload.get("subagent_run_id")
        if subagent_run_id:
            with connect() as db:
                db.execute("UPDATE subagent_runs SET status='running',updated_at=? WHERE id=?", (now(), subagent_run_id))
        try:
            result = await run_agent(
                agent,
                payload.get("history") or [],
                str(payload.get("task") or payload.get("prompt") or ""),
                thread_id=payload.get("thread_id"),
                turn_id=payload.get("turn_id"),
                depth=int(payload.get("depth", 0)),
                current_task_id=task["id"],
            )
            if subagent_run_id:
                with connect() as db:
                    db.execute("UPDATE subagent_runs SET status='completed',result=?,error=NULL,updated_at=? WHERE id=?", (json.dumps(result, ensure_ascii=False, default=str), now(), subagent_run_id))
            return result
        except Exception as exc:
            if subagent_run_id:
                with connect() as db:
                    db.execute("UPDATE subagent_runs SET status='failed',error=?,updated_at=? WHERE id=?", (str(exc)[:4000], now(), subagent_run_id))
            raise
    if task["kind"] == "workflow":
        workflow = resource_get("workflows", payload.get("workflow_id"))
        if not workflow:
            raise ValueError("后台任务引用的工作流不存在")
        return await create_run(workflow, payload.get("input"), run_id=payload.get("run_id"), task_id=task["id"], raise_errors=True)
    raise ValueError(f"未知后台任务类型: {task['kind']}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    seed_defaults()
    migrate_bailian_providers()
    await task_queue.start(execute_persistent_task, int(os.getenv("CODEZZN_TASK_WORKERS", "4")))
    try:
        yield
    finally:
        await task_queue.close()
        await mcp_manager.close()


app = FastAPI(title="Codezzn", version="0.2.0", description="可部署的智能体开发与运行平台", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/assets", StaticFiles(directory=WEB), name="assets")


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


@app.get("/api/agent-templates")
def agent_templates():
    return {"data": [{"id": key, **value} for key, value in ROLE_TEMPLATES.items()]}


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


@app.post("/api/knowledge/{knowledge_id}/ragflow/provision")
async def provision_ragflow_dataset(knowledge_id: str):
    knowledge = resource_get("knowledge", knowledge_id)
    if not knowledge:
        raise HTTPException(404, "知识库不存在")
    if knowledge.get("backend") != "ragflow":
        raise HTTPException(400, "只有 RAGFlow 知识库可以创建远程数据集")
    if knowledge.get("ragflow_dataset_id"):
        return {"created": False, "ragflow_dataset_id": knowledge["ragflow_dataset_id"]}
    try:
        dataset_id = await ensure_remote_dataset(knowledge)
        updated = resource_save("knowledge", {**knowledge, "ragflow_dataset_id": dataset_id}, knowledge_id)
        return {"created": True, "ragflow_dataset_id": dataset_id, "knowledge": updated}
    except (KnowledgeError, RAGFlowError) as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/knowledge/{knowledge_id}/documents")
async def upload_document(knowledge_id: str, file: UploadFile = File(...)):
    knowledge = resource_get("knowledge", knowledge_id)
    if not knowledge:
        raise HTTPException(404, "知识库不存在")
    raw = await file.read()
    filename = file.filename or "document.txt"
    try:
        return await upload_knowledge_document(knowledge, filename, raw, file.content_type)
    except KnowledgeValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KnowledgeConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (KnowledgeError, RAGFlowError) as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Document indexing failed") from exc


@app.get("/api/knowledge/{knowledge_id}/documents/status")
async def knowledge_document_status(knowledge_id: str, document_id: str = ""):
    knowledge = resource_get("knowledge", knowledge_id)
    if not knowledge:
        raise HTTPException(404, "知识库不存在")
    try:
        return await knowledge_status(knowledge, document_id or None)
    except (KnowledgeError, RAGFlowError) as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/api/knowledge/{knowledge_id}/documents/{document_id}")
async def remove_knowledge_document(knowledge_id: str, document_id: str):
    knowledge = resource_get("knowledge", knowledge_id)
    if not knowledge:
        raise HTTPException(404, "知识库不存在")
    try:
        return await delete_knowledge_document(knowledge, document_id)
    except KnowledgeValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (KnowledgeError, RAGFlowError) as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/knowledge/{knowledge_id}/reindex")
async def reindex_knowledge(knowledge_id: str, payload: dict = Body(default={})):
    knowledge = resource_get("knowledge", knowledge_id)
    if not knowledge:
        raise HTTPException(404, "知识库不存在")
    try:
        return await reindex_knowledge_service(knowledge, payload.get("document_id"))
    except KnowledgeValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (KnowledgeError, RAGFlowError) as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/knowledge/{knowledge_id}/health")
async def get_knowledge_health(knowledge_id: str):
    knowledge = resource_get("knowledge", knowledge_id)
    if not knowledge:
        raise HTTPException(404, "知识库不存在")
    try:
        return await knowledge_health(knowledge)
    except (KnowledgeError, RAGFlowError) as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/knowledge/search")
async def search_knowledge(payload: dict = Body(...)):
    knowledge_ids = payload.get("knowledge_ids") or []
    if not knowledge_ids:
        raise HTTPException(400, "必须明确指定至少一个知识库")
    diagnostics = {}
    try:
        data = await search_knowledge_service(payload.get("query", ""), knowledge_ids, min(int(payload.get("limit", 5)), 20),
                                               filters=payload.get("filters"), candidate_k=payload.get("candidate_k"), top_k=payload.get("top_k"),
                                               source_cap=payload.get("source_cap"), diagnostics=diagnostics)
    except KnowledgeValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"data": data, "diagnostics": diagnostics}


@app.post("/api/knowledge/evaluate")
async def evaluate_knowledge(payload: dict = Body(...)):
    try:
        return await evaluate_knowledge_backends(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/mcp_servers/{server_id}/test")
async def test_mcp(server_id: str):
    server = resource_get("mcp_servers", server_id)
    if not server:
        raise HTTPException(404, "MCP 服务不存在")
    try:
        tools = await mcp_manager.list_tools(server)
        info = mcp_manager.initialized.get(server_id, {})
        return {"ok": True, "tools": tools, "server": info.get("serverInfo"), "protocol_version": info.get("protocolVersion"), "capabilities": info.get("capabilities", {})}
    except Exception as exc:
        raise HTTPException(400, str(exc))


def _mcp_server(server_id):
    server = resource_get("mcp_servers", server_id)
    if not server:
        raise HTTPException(404, "MCP 服务不存在")
    return server


@app.get("/api/mcp_servers/{server_id}/resources")
async def list_mcp_resources(server_id: str):
    try:
        return {"data": await mcp_manager.list_resources(_mcp_server(server_id))}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/mcp_servers/{server_id}/resource-templates")
async def list_mcp_resource_templates(server_id: str):
    try:
        return {"data": await mcp_manager.list_resource_templates(_mcp_server(server_id))}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/mcp_servers/{server_id}/resources/read")
async def read_mcp_resource(server_id: str, payload: dict = Body(...)):
    try:
        return await mcp_manager.read_resource(_mcp_server(server_id), str(payload.get("uri") or ""))
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/mcp_servers/{server_id}/resources/subscribe")
async def subscribe_mcp_resource(server_id: str, payload: dict = Body(...)):
    try:
        return await mcp_manager.subscribe_resource(_mcp_server(server_id), str(payload.get("uri") or ""))
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/mcp_servers/{server_id}/resources/unsubscribe")
async def unsubscribe_mcp_resource(server_id: str, payload: dict = Body(...)):
    try:
        return await mcp_manager.unsubscribe_resource(_mcp_server(server_id), str(payload.get("uri") or ""))
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/mcp_servers/{server_id}/prompts")
async def list_mcp_prompts(server_id: str):
    try:
        return {"data": await mcp_manager.list_prompts(_mcp_server(server_id))}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/mcp_servers/{server_id}/prompts/get")
async def get_mcp_prompt(server_id: str, payload: dict = Body(...)):
    try:
        return await mcp_manager.get_prompt(_mcp_server(server_id), str(payload.get("name") or ""), payload.get("arguments"))
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/mcp_servers/{server_id}/complete")
async def complete_mcp_argument(server_id: str, payload: dict = Body(...)):
    try:
        return await mcp_manager.complete(_mcp_server(server_id), payload.get("ref") or {}, payload.get("argument") or {})
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/mcp_servers/{server_id}/logging")
async def set_mcp_logging(server_id: str, payload: dict = Body(default={})):
    try:
        return await mcp_manager.set_log_level(_mcp_server(server_id), str(payload.get("level") or "info"))
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


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


@app.post("/api/workflows/{workflow_id}/enqueue")
def enqueue_workflow_endpoint(workflow_id: str, payload: dict = Body(default={})):
    workflow = resource_get("workflows", workflow_id)
    if not workflow:
        raise HTTPException(404, "工作流不存在")
    run_id, timestamp = new_id("run"), now()
    input_value = payload.get("input", "")
    with connect() as db:
        db.execute("INSERT INTO workflow_runs(id,workflow_id,status,input,state,created_at,updated_at) VALUES(?,?, 'queued',?,?,?,?)", (run_id, workflow_id, json.dumps(input_value, ensure_ascii=False), "{}", timestamp, timestamp))
    task = enqueue_task("workflow", payload.get("name") or workflow.get("name") or "工作流任务", {"workflow_id": workflow_id, "run_id": run_id, "input": input_value}, payload.get("max_attempts", 3))
    return {"task": task, "run_id": run_id}


@app.get("/api/workflow-runs")
def workflow_runs():
    with connect() as db:
        rows = db.execute("SELECT * FROM workflow_runs ORDER BY created_at DESC LIMIT 100").fetchall()
    data = []
    for row in rows:
        item = dict(row)
        for key in ("input", "output", "trace", "state"):
            item[key] = json.loads(item[key]) if item[key] is not None else None
        data.append(item)
    return {"data": data}


@app.post("/api/agent-tasks")
def enqueue_agent_task(payload: dict = Body(...)):
    agent = resource_get("agents", payload.get("agent_id"))
    if not agent:
        raise HTTPException(400, "请选择有效的智能体")
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "任务内容不能为空")
    return enqueue_task("agent", payload.get("name") or prompt[:80], {"agent_id": agent["id"], "prompt": prompt}, payload.get("max_attempts", 3))


@app.get("/api/tasks")
def get_tasks(status: str = "", limit: int = 100):
    return {"data": list_tasks(status or None, limit)}


@app.get("/api/tasks/{task_id}")
def read_task(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {**task, "events": task_events(task_id)}


@app.delete("/api/tasks/{task_id}")
async def stop_task(task_id: str):
    if not get_task(task_id):
        raise HTTPException(404, "任务不存在")
    return {"cancelled": await task_queue.cancel(task_id)}


@app.get("/api/subagents")
def get_subagents(thread_id: str = "", turn_id: str = ""):
    where, params = [], []
    if thread_id:
        where.append("parent_thread_id=?"); params.append(thread_id)
    if turn_id:
        where.append("parent_turn_id=?"); params.append(turn_id)
    sql = "SELECT * FROM subagent_runs" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY created_at DESC LIMIT 200"
    with connect() as db:
        rows = db.execute(sql, params).fetchall()
    data = []
    for row in rows:
        item = dict(row)
        if item.get("result"):
            item["result"] = json.loads(item["result"])
        data.append(item)
    return {"data": data}


@app.get("/api/memories")
def get_memories(scope: str = "", scope_id: str = "", limit: int = 100):
    return {"data": list_memories(scope or None, scope_id or None, limit)}


@app.post("/api/memories")
def create_memory(payload: dict = Body(...)):
    try:
        return save_memory(payload.get("scope", "project"), payload.get("scope_id", "default"), payload.get("content", ""), payload.get("kind", "experience"), payload.get("importance", 0.5), payload.get("metadata"))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/memories/search")
def find_memories(payload: dict = Body(...)):
    scopes = payload.get("scopes") or [["project", "default"], ["user", "default"]]
    return {"data": search_memories(str(payload.get("query") or ""), [(str(item[0]), str(item[1])) for item in scopes if isinstance(item, list) and len(item) == 2], payload.get("limit", 10))}


@app.delete("/api/memories/{memory_id}")
def remove_memory(memory_id: str):
    if not get_memory(memory_id):
        raise HTTPException(404, "记忆不存在")
    return {"deleted": delete_memory(memory_id)}


@app.post("/api/threads")
def create_thread(payload: dict = Body(default={})):
    thread_id, timestamp = new_id("thr"), now()
    with connect() as db:
        db.execute("INSERT INTO threads(id,name,agent_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", (thread_id, payload.get("name", "新对话"), payload.get("agent_id"), "idle", timestamp, timestamp))
    return {"id": thread_id, "name": payload.get("name", "新对话"), "agent_id": payload.get("agent_id"), "status": "idle", "capability_overrides": {}, "created_at": timestamp, "updated_at": timestamp}


@app.get("/api/threads")
def list_threads(archived: bool = False):
    with connect() as db:
        rows = db.execute("SELECT * FROM threads WHERE archived=? ORDER BY updated_at DESC", (1 if archived else 0,)).fetchall()
    return {"data": [_thread_payload(row) for row in rows]}


@app.post("/api/threads/{thread_id}/fork")
def fork_thread(thread_id: str, payload: dict = Body(default={} )):
    with connect() as db:
        source = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        messages = db.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY created_at", (thread_id,)).fetchall()
    if not source:
        raise HTTPException(404, "对话不存在")
    new_thread, timestamp = new_id("thr"), now()
    with connect() as db:
        db.execute("INSERT INTO threads(id,name,agent_id,status,capability_overrides,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (new_thread, payload.get("name") or f"{source['name']} (fork)", source["agent_id"], "idle", source["capability_overrides"], timestamp, timestamp))
        for message in messages:
            db.execute("INSERT INTO messages(id,thread_id,turn_id,role,type,content,meta,created_at) VALUES(?,?,?,?,?,?,?,?)", (new_id("msg"), new_thread, message["turn_id"], message["role"], message["type"], message["content"], message["meta"], message["created_at"]))
    return {"id": new_thread, "name": payload.get("name") or f"{source['name']} (fork)", "agent_id": source["agent_id"], "status": "idle", "capability_overrides": json.loads(source["capability_overrides"] or "{}")}


@app.get("/api/threads/{thread_id}")
def read_thread(thread_id: str):
    with connect() as db:
        thread = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        messages = db.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY created_at", (thread_id,)).fetchall()
    if not thread:
        raise HTTPException(404, "对话不存在")
    result = _thread_payload(thread)
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
    if "agent_id" in payload:
        agent_id = str(payload.get("agent_id") or "")
        if not resource_get("agents", agent_id):
            raise HTTPException(400, "智能体不存在")
        updates.append("agent_id=?")
        values.append(agent_id)
        if "capability_overrides" not in payload:
            updates.append("capability_overrides=?")
            values.append("{}")
    if "capability_overrides" in payload:
        overrides = payload.get("capability_overrides")
        if not isinstance(overrides, dict) or any(key not in ("skill_ids", "mcp_server_ids") for key in overrides):
            raise HTTPException(400, "capability_overrides 格式无效")
        cleaned = {}
        if "skill_ids" in overrides:
            cleaned["skill_ids"] = _capability_ids(overrides["skill_ids"], "skills")
        if "mcp_server_ids" in overrides:
            cleaned["mcp_server_ids"] = _capability_ids(overrides["mcp_server_ids"], "mcp_servers")
        updates.append("capability_overrides=?")
        values.append(json.dumps(cleaned, ensure_ascii=False))
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
    return _thread_payload(thread)


@app.get("/api/threads/{thread_id}/approvals")
def list_approvals(thread_id: str, status: str = "pending"):
    with connect() as db:
        rows = db.execute("SELECT * FROM approvals WHERE thread_id=? AND status=? ORDER BY created_at", (thread_id, status)).fetchall()
    return {"data": [{**dict(row), "arguments": json.loads(row["arguments"])} for row in rows]}


@app.get("/api/threads/{thread_id}/approvals/inbox")
def approval_inbox(thread_id: str):
    return list_approvals(thread_id, "pending")


async def continue_approval(approval_id: str, decision: str, reason: str):
    with connect() as db:
        approval = db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    if not approval:
        raise HTTPException(404, "审批不存在")
    if approval["status"] != "pending":
        raise HTTPException(409, "审批已处理")
    if not approval["resumable"] or not approval["tool_call_id"]:
        raise HTTPException(409, "该审批由旧版本创建，无法自动续跑")
    thread_id, turn_id = approval["thread_id"], approval["turn_id"]
    lock = await thread_lock(thread_id)
    if lock.locked():
        raise HTTPException(409, "该会话已有任务正在运行")
    await lock.acquire()
    try:
        timestamp = now()
        with connect() as db:
            cur = db.execute(
                "UPDATE approvals SET status=?,resolution=?,resolved_at=? WHERE id=? AND status='pending'",
                (decision, reason, timestamp, approval_id),
            )
            checkpoint = db.execute(
                "SELECT * FROM turn_checkpoints WHERE turn_id=? AND status='waiting'", (turn_id,)
            ).fetchone()
            if not cur.rowcount:
                raise HTTPException(409, "审批已处理")
            if not checkpoint:
                raise HTTPException(409, "审批检查点不存在或已被续跑")
            claimed = db.execute(
                "UPDATE turn_checkpoints SET status='resuming',updated_at=? WHERE id=? AND status='waiting'",
                (timestamp, checkpoint["id"]),
            )
            if not claimed.rowcount:
                raise HTTPException(409, "审批检查点已被其他请求续跑")
            db.execute("UPDATE threads SET status='running',updated_at=? WHERE id=?", (timestamp, thread_id))
        agent = resource_get("agents", checkpoint["agent_id"])
        if not agent:
            raise ValueError("审批对应的智能体不存在")
        state = json.loads(checkpoint["state"])
        with connect() as db:
            row = db.execute("SELECT COALESCE(MAX(sequence),0) AS value FROM turn_events WHERE turn_id=?", (turn_id,)).fetchone()
        event_sequence = int(row["value"])

        async def emit(event):
            nonlocal event_sequence
            event_sequence += 1
            persist_event(event, thread_id, turn_id, event_sequence)

        result = await run_agent(
            agent, [], "", emit, streaming=False, thread_id=thread_id, turn_id=turn_id,
            resume_state=state,
            approval_decision={"tool_call_id": approval["tool_call_id"], "decision": decision, "reason": reason},
        )
        if result["status"] == "waiting_for_approval":
            return {"approval": {**dict(approval), "status": decision, "resolution": reason, "arguments": json.loads(approval["arguments"])}, "turn_id": turn_id, **result}
        with connect() as db:
            db.execute(
                "INSERT INTO messages(id,thread_id,turn_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?,?)",
                (new_id("msg"), thread_id, turn_id, "assistant", result["content"], json.dumps({"events": result["events"], "usage": result["usage"], "runtime": result["runtime"], "sources": result["sources"]}, ensure_ascii=False), now()),
            )
            db.execute("UPDATE turn_checkpoints SET status='completed',updated_at=? WHERE turn_id=?", (now(), turn_id))
            db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?", (now(), thread_id))
        return {"approval": {**dict(approval), "status": decision, "resolution": reason, "arguments": json.loads(approval["arguments"])}, "turn_id": turn_id, **result}
    except HTTPException:
        raise
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE turn_checkpoints SET status='failed',updated_at=? WHERE turn_id=?", (now(), turn_id))
            db.execute("UPDATE threads SET status='error',updated_at=? WHERE id=?", (now(), thread_id))
        raise HTTPException(502, str(exc))
    finally:
        lock.release()


@app.post("/api/approvals/{approval_id}")
async def resolve_approval(approval_id: str, payload: dict = Body(...)):
    decision = payload.get("decision")
    if decision not in ("approved", "denied"):
        raise HTTPException(400, "decision 必须是 approved 或 denied")
    return await continue_approval(approval_id, decision, str(payload.get("reason") or decision))


@app.post("/api/threads/{thread_id}/resume")
async def resume_thread(thread_id: str, payload: dict = Body(...)):
    approval_id = str(payload.get("approval_id") or "")
    decision = payload.get("decision")
    if approval_id:
        with connect() as db:
            approval = db.execute("SELECT thread_id FROM approvals WHERE id=?", (approval_id,)).fetchone()
        if not approval or approval["thread_id"] != thread_id:
            raise HTTPException(404, "该会话中不存在此审批")
        if decision not in ("approved", "denied"):
            raise HTTPException(400, "decision 必须是 approved 或 denied")
        return await continue_approval(approval_id, decision, str(payload.get("reason") or decision))
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
    agent = _agent_for_thread(agent, thread)
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
        except asyncio.CancelledError:
            event = {"id": new_id("evt"), "timestamp": datetime.utcnow().isoformat() + "Z", "type": "turn_cancelled", "turn_id": turn_id}
            persist_event(event, thread_id, turn_id, event_sequence + 1)
            with connect() as db: db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?", (now(), thread_id))
            await queue.put(event)
        except Exception as exc:
            with connect() as db: db.execute("UPDATE threads SET status='error',updated_at=? WHERE id=?", (now(), thread_id))
            await queue.put({"type": "turn_error", "reason": type(exc).__name__, "message": str(exc)[:1200]})
        finally:
            with connect() as db:
                db.execute("UPDATE threads SET status=CASE WHEN status='running' THEN 'error' ELSE status END,updated_at=? WHERE id=?", (now(), thread_id))
            active = ACTIVE_TURNS.get(thread_id)
            if active and active.get("turn_id") == turn_id:
                ACTIVE_TURNS.pop(thread_id, None)
            lock.release()
            await queue.put(None)
    async def body():
        task = asyncio.create_task(produce())
        ACTIVE_TURNS[thread_id] = {"task": task, "turn_id": turn_id}
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
    return StreamingResponse(body(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


@app.delete("/api/threads/{thread_id}/turns/active")
async def cancel_active_turn(thread_id: str):
    active = ACTIVE_TURNS.get(thread_id)
    if not active or active["task"].done():
        return {"cancelled": False}
    active["task"].cancel()
    return {"cancelled": True, "turn_id": active["turn_id"]}


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
    agent = _agent_for_thread(agent, thread)
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
