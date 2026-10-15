"""Read-only engineering panel API; changes remain approved chat tool actions."""
import base64
import difflib
import json

from fastapi import APIRouter, Body, HTTPException

from . import engineering
from .coding_workspace import inspect_workspace, workspace_path
from .db import connect, resource_get
from .projects import get_project, project_root
from .workspace import tenant_workspace


router = APIRouter()


def _table_exists(connection, name):
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _json(value, default=None):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {} if default is None else default


def _scope(thread_id):
    with connect() as connection:
        thread = connection.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
    if not thread:
        raise HTTPException(404, "对话不存在")
    thread = dict(thread)
    project_id = thread.get("active_project_id")
    if project_id and not get_project(project_id):
        raise HTTPException(409, "当前绑定项目已不存在，请先重新选择项目")
    item = inspect_workspace(thread_id, project_id=project_id)
    if item and workspace_path(item).is_dir():
        return thread, workspace_path(item), item
    root = project_root(project_id) if project_id else tenant_workspace()
    return thread, root, {"path": root.relative_to(tenant_workspace()).as_posix(), "project_id": project_id,
                          "mode": "canonical-readonly", "initialized": False}


def _engineering_state(root, thread_id):
    with connect() as connection:
        if not _table_exists(connection, "engineering_state"):
            return {}
        rows = connection.execute("SELECT kind,value FROM engineering_state WHERE thread_id=? AND root=?", (thread_id, engineering._key(root))).fetchall()
    return {row["kind"]: _json(row["value"]) for row in rows}


def _checkpoints(root, thread_id):
    with connect() as connection:
        if not _table_exists(connection, "engineering_checkpoints"):
            return []
        rows = connection.execute("SELECT id,label,created_at,files FROM engineering_checkpoints WHERE thread_id=? AND root=? ORDER BY created_at DESC,id DESC LIMIT 100", (thread_id, engineering._key(root))).fetchall()
    return [{"id": row["id"], "label": row["label"], "created_at": row["created_at"],
             "paths": list(_json(row["files"]))} for row in rows]


def _context(thread):
    agent = resource_get("agents", thread.get("agent_id")) or {}
    with connect() as connection:
        row = connection.execute("SELECT status,state,updated_at FROM agent_runs WHERE thread_id=? ORDER BY updated_at DESC,id DESC LIMIT 1", (thread["id"],)).fetchone()
    state = _json(row["state"]) if row else {}
    if not isinstance(state, dict):
        state = {}
    messages = state.get("messages") or []
    from .coding_context import estimate_tokens
    return {"agent_id": agent.get("id"), "context_token_budget": agent.get("context_token_budget", 40000),
            "semantic_compaction": agent.get("semantic_compaction", True),
            "status": row["status"] if row else thread.get("status", "idle"),
            "mode": state.get("mode", "chat"), "round": state.get("round", 0),
            "model": state.get("model"), "usage": state.get("usage", {}),
            "saved_message_count": len(messages), "estimated_tokens": estimate_tokens(messages) if messages else None,
            "updated_at": row["updated_at"] if row else None,
            "private_reasoning_exposed": False,
            "estimation_note": "保存上下文的保守估算，不是模型精确 tokenizer 或私有思维链"}


@router.get("/api/threads/{thread_id}/coding/state")
def coding_state(thread_id: str):
    thread, root, item = _scope(thread_id)
    return {"workspace": item, "engineering": _engineering_state(root, thread_id),
            "checkpoints": _checkpoints(root, thread_id), "context": _context(thread)}


def _diff(root, thread_id, checkpoint_id):
    with connect() as connection:
        row = connection.execute("SELECT files FROM engineering_checkpoints WHERE id=? AND thread_id=? AND root=?", (checkpoint_id, thread_id, engineering._key(root))).fetchone() if _table_exists(connection, "engineering_checkpoints") else None
    if not row:
        raise HTTPException(404, "快照不存在或不属于当前对话/工作区")
    snapshots = _json(row["files"])
    originals = {key: base64.b64decode(value, validate=True) if value is not None else None for key, value in snapshots.items()}
    contents = {key: engineering._bytes(engineering._path(root, key)) for key in snapshots}
    changes = []
    for path in originals:
        if originals[path] != contents[path]:
            changes.append({"path": path, "before_hash": engineering._hash(originals[path]),
                            "after_hash": engineering._hash(contents[path]),
                            "diff": "".join(difflib.unified_diff((originals[path] or b"").decode("utf-8", errors="replace").splitlines(True),
                                                                (contents[path] or b"").decode("utf-8", errors="replace").splitlines(True),
                                                                fromfile="before/" + path, tofile="current/" + path))[:100000]})
    return {"checkpoint_id": checkpoint_id, "changes": changes,
            "expected_hashes": {key: engineering._hash(value) for key, value in contents.items()}}


@router.post("/api/threads/{thread_id}/coding/inspect")
def coding_inspect(thread_id: str, payload: dict = Body(...)):
    _, root, _ = _scope(thread_id)
    name = payload.get("name")
    args = payload.get("args", {})
    if not isinstance(args, dict) or set(payload) - {"name", "args"}:
        raise HTTPException(400, "检查参数格式无效")
    try:
        if name == "task_diff" and set(args) == {"checkpoint_id"}:
            if not isinstance(args["checkpoint_id"], str) or not 1 <= len(args["checkpoint_id"]) <= 100:
                raise ValueError("快照 ID 格式无效")
            result = _diff(root, thread_id, args["checkpoint_id"])
        elif name == "quality_discover" and not args:
            result = engineering.discover(root)
        elif name in {"plan_manage", "hook_manage"} and args == {"action": "get"}:
            state = _engineering_state(root, thread_id)
            result = state.get("plan", {"status": "none", "steps": [], "required_checks": []}) if name == "plan_manage" else {"hooks": state.get("hooks", [])}
        else:
            raise HTTPException(403, "面板仅允许只读检查；修改、运行和回退必须通过对话审批")
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"result": result}
