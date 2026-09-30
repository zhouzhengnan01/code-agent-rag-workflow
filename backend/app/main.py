import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from datetime import datetime
import asyncio
import zipfile
import tempfile
import mimetypes
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader

from .agent import load_agent_run, persist_event, run_agent
from .capabilities import ROLE_TEMPLATES, tool_policy_decision
from .db import connect, current_tenant, ensure_tenant, init_db, migrate_bailian_providers, new_id, now, reset_tenant, resource_delete, resource_get, resource_list, resource_save, seed_defaults, tenant_ids, use_tenant
from .knowledge import KnowledgeConflictError, KnowledgeError, KnowledgeValidationError, drop_knowledge_index, rag_status
from .knowledge_eval import evaluate as evaluate_knowledge_backends
from .knowledge_service import delete_document as delete_knowledge_document, ensure_remote_dataset, health as knowledge_health, reindex as reindex_knowledge_service, search as search_knowledge_service, status as knowledge_status, upload as upload_knowledge_document
from .ragflow import RAGFlowError
from .mcp import mcp_manager
from .memory import backfill_memory_embeddings, confirm_memory, delete_memory, expire_memories, get_memory, list_memories, save_memory, search_memories
from .model import BAILIAN_PRESETS, normalize_provider, public_provider, test_provider
from .sandbox import sandbox_status
from .tasks import cancel_task, enqueue_task, get_task, list_tasks, task_events, task_queue
from .workflows import create_run
from .worktrees import ensure_worktree, list_worktrees, remove_worktree, worktree_path
from .workspace import reset_workspace, use_workspace, tenant_workspace
from .projects import artifact_path, create_project, get_artifact as get_project_artifact, get_artifact_version_content, get_project, list_artifact_versions, list_artifacts, list_projects, update_project
from .domain_tools import discard_workflow_draft, get_workflow_draft, get_workflow_version, list_workflow_versions, save_workflow_draft
from .intent import classify_intent, parse_project_directive
from .skill_packages import import_package, read_package_file
from .code_intelligence import rebuild_index, symbols as code_symbols, references as code_references, graph as code_graph
from .lsp import lsp_manager
from .browser import browser_manager
from .tenant_migration import migrate_legacy_owner
from .auth import (
    OAUTH_STATE_COOKIE, clear_session, create_session, github_authorize_url, github_callback,
    github_configured, google_authorize_url, google_callback, google_configured,
    login_user, register_user, request_user, set_session_cookie,
)
from .email_auth import send_email_code, smtp_configured, verify_email_code
from .help import asks_for_own_projects, search_faq
from .model import chat_completion


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
    # A selected project is context, not permission to modify its files.
    active_project_id = thread["active_project_id"] if "active_project_id" in thread.keys() else None
    if active_project_id:
        scoped["_project_id"] = active_project_id
        scoped["memory_project_id"] = active_project_id
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
RESOURCE_KINDS = {"agents", "agent_teams", "skills", "providers", "mcp_servers", "lsp_servers", "knowledge", "workflows"}
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("font/woff2", ".woff2")


async def run_agent_isolated(agent, history, prompt, *, task_id=None, thread_id=None, **kwargs):
    worktree = await ensure_worktree(task_id=task_id, thread_id=thread_id)
    token = use_workspace(worktree_path(worktree)) if worktree else None
    try:
        checkpoint = load_agent_run(task_id=task_id, turn_id=kwargs.get("turn_id"))
        if checkpoint and not kwargs.get("resume_state"): kwargs["resume_state"] = checkpoint["state"]
        return await run_agent(agent, history, prompt, thread_id=thread_id, current_task_id=task_id, **kwargs)
    finally:
        if token is not None: reset_workspace(token)


async def execute_persistent_task(task):
    payload = task.get("payload") or {}
    if task["kind"] in {"agent", "subagent", "agent_resume"}:
        agent = resource_get("agents", payload.get("agent_id"))
        if not agent:
            raise ValueError("后台任务引用的智能体不存在")
        subagent_run_id = payload.get("subagent_run_id")
        if subagent_run_id:
            with connect() as db:
                db.execute("UPDATE subagent_runs SET status='running',updated_at=? WHERE id=?", (now(), subagent_run_id))
        try:
            result = await run_agent_isolated(
                agent,
                payload.get("history") or [],
                str(payload.get("task") or payload.get("prompt") or ""),
                task_id=task["id"], thread_id=payload.get("thread_id"),
                turn_id=payload.get("turn_id"),
                depth=int(payload.get("depth", 0)),
            )
            if subagent_run_id:
                with connect() as db:
                    db.execute("UPDATE subagent_runs SET status='completed',result=?,error=NULL,updated_at=? WHERE id=?", (json.dumps(result, ensure_ascii=False, default=str), now(), subagent_run_id))
            if task["kind"] == "agent_resume" and payload.get("thread_id") and payload.get("turn_id") and result.get("status") == "completed":
                with connect() as db:
                    exists = db.execute("SELECT 1 FROM messages WHERE thread_id=? AND turn_id=? AND role='assistant'", (payload["thread_id"], payload["turn_id"])).fetchone()
                    if not exists: db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?,?)", (new_id("msg"),payload["thread_id"],payload["turn_id"],"assistant",result["content"],json.dumps({"events":result["events"],"usage":result["usage"],"runtime":result["runtime"],"sources":result["sources"]},ensure_ascii=False),now()))
                    db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?", (now(), payload["thread_id"]))
            return result
        except Exception as exc:
            if subagent_run_id:
                with connect() as db:
                    db.execute("UPDATE subagent_runs SET status='failed',error=?,updated_at=? WHERE id=?", (str(exc)[:4000], now(), subagent_run_id))
            if payload.get("turn_id"):
                with connect() as db:
                    db.execute("UPDATE agent_runs SET status='failed',error=?,updated_at=? WHERE turn_id=? AND status IN ('running','recovering')", (str(exc)[:4000], now(), payload["turn_id"]))
                    if payload.get("thread_id"): db.execute("UPDATE threads SET status='error',updated_at=? WHERE id=?", (now(), payload["thread_id"]))
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
    legacy_owner = os.getenv("CODEZZN_LEGACY_OWNER_GITHUB_ID", "").strip()
    if legacy_owner:
        migrate_legacy_owner(legacy_owner)
    for user_id in ([None] if not legacy_owner else []) + tenant_ids():
        if user_id:
            ensure_tenant(user_id)
            tenant_workspace(user_id).mkdir(parents=True, exist_ok=True)
        token = use_tenant(user_id)
        try:
            expire_memories()
            backfill_memory_embeddings()
            with connect() as db:
                interrupted = db.execute("SELECT * FROM agent_runs WHERE status='running' AND task_id IS NULL").fetchall()
            for row in interrupted:
                state = json.loads(row["state"] or "{}")
                enqueue_task("agent_resume", "恢复中断的智能体任务", {"agent_id":row["agent_id"],"thread_id":row["thread_id"],"turn_id":row["turn_id"],"prompt":state.get("user_message", "")}, max_attempts=3)
                with connect() as db: db.execute("UPDATE agent_runs SET status='recovering',updated_at=? WHERE id=?", (now(), row["id"]))
        finally:
            reset_tenant(token)
    await task_queue.start(execute_persistent_task, int(os.getenv("CODEZZN_TASK_WORKERS", "4")))
    try:
        yield
    finally:
        await task_queue.close()
        await mcp_manager.close()
        await lsp_manager.close()
        await browser_manager.close()


app = FastAPI(title="Codezzn", version="0.3.0", description="可部署的智能体开发与运行平台", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/assets", StaticFiles(directory=WEB), name="assets")
LANDING_ASSETS = ROOT / "public" / "sites" / "browser-use-com-ef244017" / "web-agents-4de235c6"
app.mount(
    "/site-assets",
    StaticFiles(directory=LANDING_ASSETS),
    name="browser-use-landing-assets",
)


PUBLIC_PATHS = {"/", "/healthz", "/login", "/register", "/api/help/faq"}


@app.middleware("http")
async def access_control(request: Request, call_next):
    key = os.getenv("CODEZZN_ADMIN_KEY")
    path = request.url.path
    public = path in PUBLIC_PATHS or path.startswith("/assets/") or path.startswith("/site-assets/") or path.startswith("/api/auth/")
    user = request_user(request) if not public or path in {"/api/auth/me", "/api/help/faq", "/api/help/ask"} else None
    request.state.user = user
    supplied = request.headers.get("X-Codezzn-Key") or request.query_params.get("api_key")
    key_valid = bool(key and supplied == key)
    auth_required = os.getenv("CODEZZN_AUTH_REQUIRED", "false").lower() == "true"
    if not public and (auth_required or key) and not user and not key_valid:
        if path == "/workbench.html":
            return RedirectResponse("/login?next=/workbench.html", status_code=303)
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    token = use_tenant(user["id"] if user else None)
    try:
        if user:
            ensure_tenant(user["id"])
            tenant_workspace().mkdir(parents=True, exist_ok=True)
        return await call_next(request)
    finally:
        reset_tenant(token)


@app.get("/")
def public_home():
    return FileResponse(WEB / "home.html")


@app.get("/workbench.html")
def workbench():
    return FileResponse(WEB / "workbench.html")


@app.get("/login")
def login_page():
    return FileResponse(WEB / "login.html")


@app.get("/register")
def register_page():
    return FileResponse(WEB / "register.html")


@app.get("/api/auth/me")
def auth_me(request: Request):
    return {"authenticated": bool(request.state.user), "user": request.state.user,
            "github_configured": github_configured(), "google_configured": google_configured(),
            "email_code_configured": smtp_configured()}


@app.get("/api/help/faq")
def help_faq(q: str = ""):
    return {"data": search_faq(q)}


@app.post("/api/help/ask")
async def help_ask(request: Request, payload: dict = Body(...)):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "请先登录后使用帮助助手")
    question = str(payload.get("question") or "").strip()
    if not question or len(question) > 2000:
        raise HTTPException(400, "问题长度须为 1–2000 个字符")
    matches = search_faq(question, 4)
    # Only authenticated tenant sessions may use the assistant.
    if asks_for_own_projects(question):
        projects = list_projects()
        if projects:
            names = "\n".join(f"{index}. {item['name']}（ID：{item['id']}）" for index, item in enumerate(projects, 1))
            answer = f"你当前有 {len(projects)} 个项目：\n{names}\n\n在左侧「项目」页面可以打开项目；在对话顶部的「当前项目」可以切换项目。"
        else:
            answer = "你当前还没有项目。可以在左侧「项目」页面创建，或在对话中创建并选择项目。"
        return {"answer": answer, "source": "workspace", "matches": []}
    agents = [item for item in resource_list("agents") if item.get("enabled", True)]
    agent = next((item for item in agents if item.get("role_template") == "general"), agents[0] if agents else None)
    provider = resource_get("providers", agent.get("provider_id")) if agent else None
    if not provider or not provider.get("api_key"):
        answer = matches[0]["answer"] if matches else "当前没有可用的模型提供方。请先在“模型接入”配置模型；你也可以搜索上方的帮助问题。"
        return {"answer": answer, "source": "faq", "matches": matches}
    context = "\n\n".join(f"Q: {item['question']}\nA: {item['answer']}" for item in matches)
    try:
        response, _ = await chat_completion(provider, agent.get("model") or provider.get("default_model"), [
            {"role": "system", "content": "你是 Codezzn 的产品帮助助手。使用用户当前 Codezzn 部署中的 FAQ 作为依据，用简体中文简洁回答产品使用问题。不要调用工具，不要承诺你已经执行了操作，也不要索取密码、API Key、验证码或其他凭据。如果 FAQ 无法回答，明确说目前没有找到依据，并建议用户在智能体工作台继续询问。\n\nCodezzn FAQ:\n" + context},
            {"role": "user", "content": question},
        ], tools=None, temperature=0.2)
        answer = str(response.get("content") or "").strip()
        if answer:
            return {"answer": answer, "source": "agent", "matches": matches}
    except Exception:
        pass
    return {"answer": matches[0]["answer"] if matches else "暂时无法生成回答，请稍后重试。", "source": "faq", "matches": matches}


@app.post("/api/auth/register")
def auth_register(payload: dict = Body(...)):
    if smtp_configured():
        raise HTTPException(403, "请通过邮箱验证码注册账号")
    user = register_user(payload.get("name"), payload.get("email"), payload.get("password"))
    token, expires = create_session(user["id"])
    response = JSONResponse({"user": user})
    set_session_cookie(response, token, expires)
    return response


@app.post("/api/auth/login")
def auth_login(payload: dict = Body(...)):
    user = login_user(payload.get("email"), payload.get("password"))
    token, expires = create_session(user["id"])
    response = JSONResponse({"user": user})
    set_session_cookie(response, token, expires)
    return response


@app.post("/api/auth/email/code")
def auth_email_code(payload: dict = Body(...)):
    response = JSONResponse(send_email_code(payload.get("email")))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/api/auth/email/verify")
def auth_email_verify(request: Request, payload: dict = Body(...)):
    user = verify_email_code(payload.get("email"), payload.get("code"))
    response = JSONResponse({"user": user})
    clear_session(request, response)
    token, expires = create_session(user["id"])
    set_session_cookie(response, token, expires)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    response = JSONResponse({"ok": True})
    clear_session(request, response)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/", samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/auth/github/start")
def auth_github_start(next: str = "/workbench.html"):
    url, state = github_authorize_url(next)
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        OAUTH_STATE_COOKIE, state, max_age=600, httponly=True,
        secure=os.getenv("CODEZZN_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/auth/github/callback")
async def auth_github_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        response = RedirectResponse("/login?error=github_denied", status_code=303)
    elif not code or not state or not secrets.compare_digest(request.cookies.get(OAUTH_STATE_COOKIE) or "", state):
        response = RedirectResponse("/login?error=github_invalid", status_code=303)
    else:
        try:
            user, next_path = await github_callback(code, state)
        except HTTPException as exc:
            response = RedirectResponse(f"/login?error=github_{exc.status_code}", status_code=303)
        else:
            response = RedirectResponse(next_path, status_code=303)
            clear_session(request, response)
            token, expires = create_session(user["id"])
            set_session_cookie(response, token, expires)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/", samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/auth/google/start")
def auth_google_start(next: str = "/workbench.html"):
    url, state = google_authorize_url(next)
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        OAUTH_STATE_COOKIE, state, max_age=600, httponly=True,
        secure=os.getenv("CODEZZN_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/auth/google/callback")
async def auth_google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        response = RedirectResponse("/login?error=google_denied", status_code=303)
    elif not code or not state or not secrets.compare_digest(request.cookies.get(OAUTH_STATE_COOKIE) or "", state):
        response = RedirectResponse("/login?error=google_invalid", status_code=303)
    else:
        try:
            user, next_path = await google_callback(code, state)
        except HTTPException as exc:
            response = RedirectResponse(f"/login?error=google_{exc.status_code}", status_code=303)
        else:
            response = RedirectResponse(next_path, status_code=303)
            clear_session(request, response)
            token, expires = create_session(user["id"])
            set_session_cookie(response, token, expires)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/", samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz")
def health():
    return {"status": "ok", "name": "codezzn", "version": app.version}


@app.post("/api/agent/intent")
async def agent_intent(payload: dict = Body(...)):
    agent_id = payload.get("agent_id")
    content = payload.get("content")
    if not isinstance(agent_id, str) or not isinstance(content, str):
        raise HTTPException(400, "必须提供 agent_id 和 content")
    agent = resource_get("agents", agent_id)
    if not agent or agent.get("enabled") is False:
        raise HTTPException(404, "智能体不存在")
    thread_id = payload.get("thread_id")
    history = []
    if thread_id:
        with connect() as db:
            thread = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
            history = [dict(row) for row in db.execute(
                "SELECT role,content FROM messages WHERE thread_id=? ORDER BY created_at DESC LIMIT 6", (thread_id,),
            ).fetchall()]
        if not thread:
            raise HTTPException(404, "对话不存在")
        agent = _agent_for_thread(agent, thread)
    try:
        return await classify_intent(agent, content, list(reversed(history)), projects=list_projects())
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc


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
    try: return import_package(file.filename or "SKILL.md", await file.read())
    except (ValueError, zipfile.BadZipFile) as exc: raise HTTPException(400, str(exc)) from exc


@app.get("/api/skills/{skill_id}/files/{path:path}")
def get_skill_file(skill_id: str, path: str):
    skill = resource_get("skills", skill_id)
    if not skill: raise HTTPException(404, "技能不存在")
    try: return read_package_file(skill, path)
    except (ValueError, FileNotFoundError) as exc: raise HTTPException(404, str(exc)) from exc


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


@app.get("/api/workflow-drafts/{draft_id}")
def read_workflow_draft(draft_id: str):
    draft = get_workflow_draft(draft_id)
    if not draft:
        raise HTTPException(404, "Workflow 草稿不存在")
    return draft


@app.get("/api/workflows/{workflow_id}/versions")
def workflow_versions_endpoint(workflow_id: str):
    versions = list_workflow_versions(workflow_id)
    if versions is None:
        raise HTTPException(404, "Workflow 不存在")
    return {"data": versions}


@app.get("/api/workflows/{workflow_id}/versions/{version}")
def workflow_version_endpoint(workflow_id: str, version: int):
    definition = get_workflow_version(workflow_id, version)
    if definition is None:
        raise HTTPException(404, "Workflow 版本不存在")
    return definition


@app.post("/api/workflow-drafts/{draft_id}/save")
def save_workflow_draft_endpoint(draft_id: str):
    draft = get_workflow_draft(draft_id)
    if not draft:
        raise HTTPException(404, "Workflow 草稿不存在")
    try:
        return save_workflow_draft(draft_id, thread_id=draft["thread_id"], turn_id=draft["turn_id"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/workflow-drafts/{draft_id}/discard")
def discard_workflow_draft_endpoint(draft_id: str):
    try:
        return discard_workflow_draft(draft_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


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
        return save_memory(payload.get("scope", "project"), payload.get("scope_id", "default"), payload.get("content", ""), payload.get("kind", "experience"), payload.get("importance", 0.5), payload.get("metadata"), payload.get("confidence", 0.7), payload.get("expires_at"), payload.get("confirmed", True), payload.get("supersedes_id"))
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


@app.post("/api/memories/{memory_id}/confirm")
def approve_memory(memory_id: str, payload: dict = Body(default={})):
    result = confirm_memory(memory_id, payload.get("accept", True), payload.get("supersede_conflict", False))
    if not result: raise HTTPException(404, "记忆不存在")
    return result


@app.get("/api/worktrees")
def get_worktrees(): return {"data": list_worktrees()}


@app.delete("/api/worktrees/{worktree_id}")
async def delete_worktree(worktree_id: str): return {"removed": await remove_worktree(worktree_id)}


@app.post("/api/code-index/rebuild")
async def rebuild_code_index(): return await asyncio.to_thread(rebuild_index, tenant_workspace())


@app.get("/api/code-index/symbols")
def query_code_symbols(query: str = "", limit: int = 100): return {"data": code_symbols(tenant_workspace(), query, limit)}


@app.get("/api/code-index/references")
def query_code_references(symbol: str, limit: int = 200): return {"data": code_references(tenant_workspace(), symbol, limit)}


@app.get("/api/code-index/graph")
def query_code_graph(kind: str = "call", symbol: str = "", limit: int = 300):
    if kind not in {"call", "import"}: raise HTTPException(400, "kind 必须为 call 或 import")
    return {"data": code_graph(tenant_workspace(), kind, symbol, limit)}


@app.get("/api/artifacts")
def get_artifact(path: str):
    root = tenant_workspace().resolve()
    target = (root / path).resolve()
    if root not in target.parents or not target.is_file(): raise HTTPException(404, "产物不存在")
    return FileResponse(target)


@app.get("/api/projects")
def projects_list():
    return {"data": list_projects()}


@app.post("/api/projects")
def projects_create(payload: dict = Body(...)):
    try:
        return create_project(payload.get("name"), payload.get("description", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/projects/{project_id}")
def projects_read(project_id: str):
    try:
        project = get_project(project_id)
    except ValueError:
        project = None
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@app.patch("/api/projects/{project_id}")
def projects_update(project_id: str, payload: dict = Body(...)):
    try:
        project = update_project(project_id, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@app.get("/api/projects/{project_id}/artifacts")
def projects_artifacts(project_id: str):
    try:
        artifacts = list_artifacts(project_id)
    except ValueError:
        artifacts = None
    if artifacts is None:
        raise HTTPException(404, "项目不存在")
    return {"data": artifacts}


@app.get("/api/projects/{project_id}/artifacts/archive")
def projects_artifacts_archive(project_id: str, prefix: str = ""):
    """Download a ZIP made only from this tenant's registered project artifacts."""
    if len(prefix) > 500 or prefix.startswith("/") or prefix.endswith("/"):
        raise HTTPException(400, "文件夹路径无效")
    prefix = prefix.strip("/")
    if prefix and ("\\" in prefix or any(part in {"", ".", ".."} for part in prefix.split("/"))):
        raise HTTPException(400, "文件夹路径无效")
    try:
        artifacts = list_artifacts(project_id)
    except ValueError:
        artifacts = None
    if artifacts is None:
        raise HTTPException(404, "项目不存在")
    if prefix:
        artifacts = [item for item in artifacts if item["path"].startswith(prefix + "/")]
        if not artifacts:
            raise HTTPException(404, "文件夹中没有已登记的文件")
    if len(artifacts) > 1000:
        raise HTTPException(413, "项目文件超过 1000 个，无法打包下载")

    total_bytes = 0
    files = []
    for artifact in artifacts:
        try:
            target = artifact_path(project_id, artifact["path"])
        except ValueError:
            continue
        if not target.is_file():
            continue
        size = target.stat().st_size
        total_bytes += size
        if total_bytes > 128 * 1024 * 1024:
            raise HTTPException(413, "项目文件总大小超过 128 MiB，无法打包下载")
        files.append((target, artifact["path"]))

    archive = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    try:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for target, relative_path in files:
                bundle.write(target, arcname=relative_path)
        archive.seek(0)
    except Exception:
        archive.close()
        raise

    def chunks():
        try:
            while chunk := archive.read(1024 * 1024):
                yield chunk
        finally:
            archive.close()

    return StreamingResponse(
        chunks(), media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="project-{project_id}.zip"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@app.get("/api/projects/{project_id}/resources")
def projects_resources(project_id: str):
    try:
        project = get_project(project_id)
    except ValueError:
        project = None
    if not project:
        raise HTTPException(404, "项目不存在")
    workflows = [
        {"id": item["id"], "name": item["name"], "description": item.get("description", ""),
         "version": item.get("version", 0), "updated_at": item["updated_at"]}
        for item in resource_list("workflows") if item.get("project_id") == project_id
    ]
    return {"workflows": workflows}


@app.get("/api/projects/{project_id}/artifacts/{artifact_id}/download")
def projects_artifact_download(project_id: str, artifact_id: str):
    try:
        artifact = get_project_artifact(project_id, artifact_id)
        target = artifact_path(project_id, artifact["path"]) if artifact else None
    except ValueError:
        target = None
    if not target or not target.is_file():
        raise HTTPException(404, "产物不存在")
    return FileResponse(target, filename=target.name, headers={"X-Content-Type-Options": "nosniff"})


@app.get("/api/projects/{project_id}/artifacts/{artifact_id}/versions")
def projects_artifact_versions(project_id: str, artifact_id: str):
    try:
        versions = list_artifact_versions(project_id, artifact_id)
    except ValueError:
        versions = None
    if versions is None:
        raise HTTPException(404, "产物不存在")
    return {"data": versions}


@app.get("/api/projects/{project_id}/artifacts/{artifact_id}/versions/{version}/download")
def projects_artifact_version_download(project_id: str, artifact_id: str, version: int):
    try:
        artifact = get_project_artifact(project_id, artifact_id)
        content = get_artifact_version_content(project_id, artifact_id, version) if artifact else None
    except ValueError:
        artifact, content = None, None
    if artifact is None or content is None:
        raise HTTPException(404, "该版本不存在或文件过大，未保存版本快照")
    filename = Path(artifact["path"]).name.replace('"', "")
    return Response(content, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff",
    })


@app.get("/api/projects/{project_id}/artifacts/{artifact_id}/content")
def projects_artifact_content(project_id: str, artifact_id: str):
    try:
        artifact = get_project_artifact(project_id, artifact_id)
        target = artifact_path(project_id, artifact["path"]) if artifact else None
    except ValueError:
        target = None
    if not target or not target.is_file():
        raise HTTPException(404, "产物不存在")
    if target.stat().st_size > 1024 * 1024:
        raise HTTPException(413, "文件过大，请下载后查看")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(415, "该产物不是 UTF-8 文本，请下载后查看") from exc
    return {"artifact": artifact, "content": content}


def _agent_can_save_project_files(agent: dict | None, intent_kind: str = "file") -> bool:
    """A project choice may cover files or domain assets, but never bypass policy."""
    if not agent or agent.get("enabled") is False:
        return False
    if agent.get("sandbox_mode") not in {"workspace-write", "danger-full-access"}:
        return False
    file_writer = any(
        (name in (agent.get("builtin_tools") or []) or agent.get("role_template") == "coding")
        and tool_policy_decision(agent, name) != "deny"
        for name in ("write_file", "apply_patch")
    )
    if intent_kind == "workflow":
        return all(tool_policy_decision(agent, name) != "deny" for name in (
            "workflow_draft_create", "workflow_draft_save",
        ))
    if intent_kind == "project":
        return tool_policy_decision(agent, "project_create") != "deny"
    return file_writer


def _validate_turn_project_choice(db, payload: dict, agent: dict | None = None):
    project_id = payload.get("project_id")
    save = payload.get("save_to_project", False)
    if not isinstance(save, bool):
        raise HTTPException(400, "save_to_project 必须是布尔值")
    if project_id is not None:
        if not isinstance(project_id, str) or not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(404, "项目不存在")
    if save and not project_id:
        raise HTTPException(400, "保存产物前必须选择项目")
    if save and agent is not None and not _agent_can_save_project_files(agent, str(payload.get("intent_kind") or "file")):
        raise HTTPException(409, "当前智能体没有项目或文件写入能力；请检查工具策略和沙箱模式")
    return project_id, save


def _turn_project_choice(db, thread_id: str, turn_id: str, payload: dict, timestamp: int, agent: dict | None = None):
    """Persist explicit turn intent before the agent starts or streams."""
    if "project_id" not in payload and "save_to_project" not in payload:
        return
    project_id, save = _validate_turn_project_choice(db, payload, agent)
    db.execute(
        "INSERT INTO turn_projects(turn_id,thread_id,project_id,save_to_project,created_at) VALUES(?,?,?,?,?)",
        (turn_id, thread_id, project_id, int(save), timestamp),
    )
    if project_id:
        db.execute(
            "INSERT OR IGNORE INTO thread_projects(thread_id,project_id,created_at) VALUES(?,?,?)",
            (thread_id, project_id, timestamp),
        )
        db.execute("UPDATE threads SET active_project_id=? WHERE id=?", (project_id, thread_id))


@app.post("/api/threads")
def create_thread(payload: dict = Body(default={})):
    thread_id, timestamp = new_id("thr"), now()
    with connect() as db:
        db.execute("INSERT INTO threads(id,name,agent_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", (thread_id, payload.get("name", "新对话"), payload.get("agent_id"), "idle", timestamp, timestamp))
    return {"id": thread_id, "name": payload.get("name", "新对话"), "agent_id": payload.get("agent_id"), "status": "idle", "capability_overrides": {}, "active_project_id": None, "created_at": timestamp, "updated_at": timestamp}


@app.get("/api/threads")
def list_threads(archived: bool = False):
    with connect() as db:
        rows = db.execute("SELECT * FROM threads WHERE archived=? ORDER BY updated_at DESC", (1 if archived else 0,)).fetchall()
    return {"data": [_thread_payload(row) for row in rows]}


@app.post("/api/threads/{thread_id}/project-switch")
def switch_thread_project(thread_id: str, payload: dict = Body(...)):
    """Bind an existing project without treating the switch as file-write consent."""
    project_name = payload.get("project_name")
    content = payload.get("content")
    if not isinstance(project_name, str) or not project_name.strip() or len(project_name.strip()) > 100:
        raise HTTPException(400, "项目名称无效")
    if not isinstance(content, str) or not content.strip() or len(content) > 8000:
        raise HTTPException(400, "消息内容无效")
    project_name = project_name.strip()
    directive = parse_project_directive(content, [{"id": "requested", "name": project_name}])
    if not directive or directive["remaining_task"] or directive["project_name"].casefold() != project_name.casefold():
        raise HTTPException(400, "此接口只接受单独的项目切换指令；复合任务必须继续处理剩余步骤")
    timestamp = now()
    turn_id = new_id("turn")
    with connect() as db:
        thread = db.execute("SELECT id,status FROM threads WHERE id=?", (thread_id,)).fetchone()
        if not thread:
            raise HTTPException(404, "对话不存在")
        if thread["status"] in {"running", "waiting_for_approval"}:
            raise HTTPException(409, "请先完成当前运行或审批，再切换项目")
        projects = db.execute("SELECT id,name FROM projects WHERE name=? COLLATE NOCASE", (project_name,)).fetchall()
        if not projects:
            raise HTTPException(404, f"找不到项目「{project_name}」，请从当前项目菜单选择或创建项目")
        if len(projects) > 1:
            raise HTTPException(409, f"存在多个同名项目「{project_name}」，请从当前项目菜单选择具体项目")
        project = dict(projects[0])
        reply = f"已切换到项目「{project['name']}」（ID: {project['id']}）。这次操作只切换对话项目，不授权写入文件。"
        db.execute("INSERT OR IGNORE INTO thread_projects(thread_id,project_id,created_at) VALUES(?,?,?)", (thread_id, project["id"], timestamp))
        db.execute("UPDATE threads SET active_project_id=?,updated_at=? WHERE id=?", (project["id"], timestamp, thread_id))
        db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,created_at) VALUES(?,?,?,?,?,?)", (new_id("msg"), thread_id, turn_id, "user", content.strip(), timestamp))
        db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,created_at) VALUES(?,?,?,?,?,?)", (new_id("msg"), thread_id, turn_id, "assistant", reply, timestamp))
    return {"project": project, "content": reply, "turn_id": turn_id}


@app.post("/api/threads/{thread_id}/fork")
def fork_thread(thread_id: str, payload: dict = Body(default={} )):
    with connect() as db:
        source = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        messages = db.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY created_at", (thread_id,)).fetchall()
    if not source:
        raise HTTPException(404, "对话不存在")
    new_thread, timestamp = new_id("thr"), now()
    with connect() as db:
        db.execute("INSERT INTO threads(id,name,agent_id,status,capability_overrides,active_project_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (new_thread, payload.get("name") or f"{source['name']} (fork)", source["agent_id"], "idle", source["capability_overrides"], source["active_project_id"], timestamp, timestamp))
        db.execute("INSERT INTO thread_projects(thread_id,project_id,created_at) SELECT ?,project_id,? FROM thread_projects WHERE thread_id=?", (new_thread, timestamp, thread_id))
        for message in messages:
            db.execute("INSERT INTO messages(id,thread_id,turn_id,role,type,content,meta,created_at) VALUES(?,?,?,?,?,?,?,?)", (new_id("msg"), new_thread, message["turn_id"], message["role"], message["type"], message["content"], message["meta"], message["created_at"]))
    return {"id": new_thread, "name": payload.get("name") or f"{source['name']} (fork)", "agent_id": source["agent_id"], "status": "idle", "capability_overrides": json.loads(source["capability_overrides"] or "{}"), "active_project_id": source["active_project_id"]}


@app.get("/api/threads/{thread_id}")
def read_thread(thread_id: str):
    with connect() as db:
        thread = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        messages = db.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY created_at", (thread_id,)).fetchall()
        project_rows = db.execute("SELECT project_id FROM thread_projects WHERE thread_id=? ORDER BY created_at", (thread_id,)).fetchall()
        turn_choices = db.execute("SELECT turn_id,project_id,save_to_project FROM turn_projects WHERE thread_id=?", (thread_id,)).fetchall()
        artifacts = db.execute("SELECT * FROM project_artifacts WHERE thread_id=? ORDER BY created_at,id", (thread_id,)).fetchall()
        resource_assets = db.execute("SELECT * FROM resource_assets WHERE thread_id=? ORDER BY created_at,id", (thread_id,)).fetchall()
        run_status = {row["id"]: row["status"] for row in db.execute(
            "SELECT id,status FROM workflow_runs WHERE id IN (SELECT resource_id FROM resource_assets WHERE thread_id=? AND kind='workflow_run')",
            (thread_id,),
        )}
    if not thread:
        raise HTTPException(404, "对话不存在")
    result = _thread_payload(thread)
    choices_by_turn = {row["turn_id"]: {"project_id": row["project_id"], "save_to_project": bool(row["save_to_project"])} for row in turn_choices}
    artifacts_by_turn = {}
    for row in artifacts:
        artifacts_by_turn.setdefault(row["turn_id"], []).append(dict(row))
    resources_by_turn = {}
    for row in resource_assets:
        item = dict(row)
        if item["kind"] == "workflow_run":
            item["status"] = run_status.get(item["resource_id"], item["status"])
        resources_by_turn.setdefault(row["turn_id"], []).append(item)
    result["messages"] = [{
        **dict(row), "meta": json.loads(row["meta"]),
        "project_choice": choices_by_turn.get(row["turn_id"]) if row["role"] == "assistant" else None,
        "project_artifacts": artifacts_by_turn.get(row["turn_id"], []) if row["role"] == "assistant" else [],
        "resource_assets": resources_by_turn.get(row["turn_id"], []) if row["role"] == "assistant" else [],
    } for row in messages]
    result["project_ids"] = [row["project_id"] for row in project_rows]
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
    if "active_project_id" in payload:
        project_id = payload["active_project_id"]
        if project_id is not None:
            try:
                valid_project = isinstance(project_id, str) and get_project(project_id)
            except ValueError:
                valid_project = False
            if not valid_project:
                raise HTTPException(404, "项目不存在")
        updates.append("active_project_id=?")
        values.append(project_id)
    if not updates:
        raise HTTPException(400, "没有可更新的会话字段")
    updates.append("updated_at=?")
    values.append(now())
    values.append(thread_id)
    with connect() as db:
        cur = db.execute(f"UPDATE threads SET {', '.join(updates)} WHERE id=?", values)
        if cur.rowcount and payload.get("active_project_id"):
            db.execute("INSERT OR IGNORE INTO thread_projects(thread_id,project_id,created_at) VALUES(?,?,?)", (thread_id, payload["active_project_id"], now()))
        thread = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
    if not cur.rowcount or not thread:
        raise HTTPException(404, "会话不存在")
    return _thread_payload(thread)


@app.get("/api/threads/{thread_id}/approvals")
def list_approvals(thread_id: str, status: str = "pending"):
    with connect() as db:
        rows = db.execute("""SELECT a.*, EXISTS(
            SELECT 1 FROM turn_checkpoints c WHERE c.turn_id=a.turn_id AND c.status='waiting'
        ) AS has_checkpoint FROM approvals a WHERE a.thread_id=? AND a.status=? ORDER BY a.created_at""", (thread_id, status)).fetchall()
    return {"data": [{**dict(row), "resumable": bool(row["resumable"] and row["tool_call_id"] and row["has_checkpoint"]),
                      "arguments": json.loads(row["arguments"])} for row in rows]}


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
    if approval["tool_name"] == "ask_user" and decision == "approved" and not reason.strip():
        raise HTTPException(400, "请填写或选择一个回答")
    if len(reason) > 4000:
        raise HTTPException(400, "回答不能超过 4000 个字符")
    if not approval["resumable"] or not approval["tool_call_id"]:
        raise HTTPException(409, "该审批缺少可恢复状态，不能执行旧工具调用；请使用「重新填写任务」发起新任务")
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

        result = await run_agent_isolated(
            agent, [], "", on_event=emit, streaming=False, thread_id=thread_id, turn_id=turn_id,
            resume_state=state,
            approval_decision={"tool_call_id": approval["tool_call_id"], "decision": decision, "reason": reason},
        )
        if result["status"] == "waiting_for_approval":
            with connect() as db:
                db.execute("UPDATE threads SET status='waiting_for_approval',updated_at=? WHERE id=?", (now(), thread_id))
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


@app.post("/api/approvals/{approval_id}/dismiss")
def dismiss_stale_approval(approval_id: str):
    """Retire a pre-checkpoint approval without executing its old tool call."""
    with connect() as db:
        approval = db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        if not approval:
            raise HTTPException(404, "审批不存在")
        if approval["status"] != "pending":
            raise HTTPException(409, "审批已处理")
        checkpoint = db.execute("SELECT 1 FROM turn_checkpoints WHERE turn_id=? AND status='waiting'", (approval["turn_id"],)).fetchone()
        if approval["resumable"] and approval["tool_call_id"] and checkpoint:
            raise HTTPException(409, "这是可续跑的审批，请选择允许或拒绝")
        user_message = db.execute("SELECT content FROM messages WHERE thread_id=? AND turn_id=? AND role='user' ORDER BY created_at LIMIT 1", (approval["thread_id"], approval["turn_id"])).fetchone()
        db.execute("UPDATE approvals SET status='expired',resolution='旧版本审批缺少续跑检查点，未执行工具',resolved_at=? WHERE id=? AND status='pending'", (now(), approval_id))
    return {"status": "expired", "content": user_message["content"] if user_message else "", "thread_id": approval["thread_id"]}


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
    with connect() as db:
        _validate_turn_project_choice(db, payload, agent)
    lock = await thread_lock(thread_id)
    if lock.locked():
        raise HTTPException(409, "该会话已有任务正在运行")
    await lock.acquire()
    turn_id, timestamp = new_id("turn"), now()
    try:
        with connect() as db:
            db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,created_at) VALUES(?,?,?,?,?,?)", (new_id("msg"), thread_id, turn_id, "user", content, timestamp))
            _turn_project_choice(db, thread_id, turn_id, payload, timestamp, agent)
            db.execute("UPDATE threads SET agent_id=?,status='running',updated_at=? WHERE id=?", (agent_id, timestamp, thread_id))
    except Exception:
        lock.release()
        raise
    queue = asyncio.Queue()
    event_sequence = 0
    async def emit(event):
        nonlocal event_sequence
        event_sequence += 1
        persist_event(event, thread_id, turn_id, event_sequence)
        await queue.put({**event, "sequence": event_sequence})
    async def produce():
        try:
            result = await run_agent_isolated(agent, [dict(item) for item in history], content, on_event=emit, streaming=True, thread_id=thread_id, turn_id=turn_id)
            if result["status"] == "waiting_for_approval":
                # run_agent has already persisted a resumable checkpoint and set
                # the thread to waiting_for_approval. Do not turn the empty
                # interim assistant content into a completed message, and do not
                # overwrite the waiting state with idle.
                await queue.put({
                    "type": "turn_result",
                    "turn_id": turn_id,
                    "status": result["status"],
                    "approval_id": result.get("approval_id"),
                    **{key: result[key] for key in ("content", "usage", "runtime", "sources")},
                })
                return
            with connect() as db:
                db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?,?)", (new_id("msg"), thread_id, turn_id, "assistant", result["content"], json.dumps({"events": result["events"], "usage": result["usage"], "runtime": result["runtime"], "sources": result["sources"]}, ensure_ascii=False), now()))
                db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?", (now(), thread_id))
            await queue.put({"type": "turn_result", "turn_id": turn_id, "status": result["status"], **{key: result[key] for key in ("content", "usage", "runtime", "sources")}})
        except asyncio.CancelledError:
            event = {"id": new_id("evt"), "timestamp": datetime.utcnow().isoformat() + "Z", "type": "turn_cancelled", "turn_id": turn_id}
            persist_event(event, thread_id, turn_id, event_sequence + 1)
            with connect() as db:
                db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?", (now(), thread_id))
                db.execute("UPDATE agent_runs SET status='cancelled',updated_at=? WHERE turn_id=? AND status IN ('running','waiting')", (now(), turn_id))
            await queue.put(event)
        except Exception as exc:
            with connect() as db:
                db.execute("UPDATE threads SET status='error',updated_at=? WHERE id=?", (now(), thread_id))
                db.execute("UPDATE agent_runs SET status='failed',error=?,updated_at=? WHERE turn_id=? AND status='running'", (str(exc)[:4000], now(), turn_id))
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
    with connect() as db:
        _validate_turn_project_choice(db, payload, agent)
    lock = await thread_lock(thread_id)
    if lock.locked():
        raise HTTPException(409, "该会话已有任务正在运行")
    await lock.acquire()
    turn_id, timestamp = new_id("turn"), now()
    try:
        with connect() as db:
            db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,created_at) VALUES(?,?,?,?,?,?)", (new_id("msg"), thread_id, turn_id, "user", content, timestamp))
            _turn_project_choice(db, thread_id, turn_id, payload, timestamp, agent)
            db.execute("UPDATE threads SET agent_id=?,status='running',updated_at=? WHERE id=?", (agent_id, timestamp, thread_id))
    except Exception:
        lock.release()
        raise
    try:
        result = await run_agent_isolated(agent, [dict(item) for item in history], content, thread_id=thread_id, turn_id=turn_id)
        if result["status"] == "waiting_for_approval":
            return {"turn_id": turn_id, **result}
        with connect() as db:
            db.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?,?)", (new_id("msg"), thread_id, turn_id, "assistant", result["content"], json.dumps({"events": result["events"], "usage": result["usage"], "runtime": result["runtime"], "sources": result["sources"]}, ensure_ascii=False), now()))
            db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?", (now(), thread_id))
        return {"turn_id": turn_id, **result}
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE threads SET status='error',updated_at=? WHERE id=?", (now(), thread_id))
            db.execute("UPDATE agent_runs SET status='failed',error=?,updated_at=? WHERE turn_id=? AND status='running'", (str(exc)[:4000], now(), turn_id))
        raise HTTPException(502, str(exc))
    finally:
        lock.release()
