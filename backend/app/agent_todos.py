"""Tenant-isolated, conversation-scoped todo state for coding agents."""

import json

from .db import connect, now


_STATUSES = {"pending", "in_progress", "completed"}
_MAX_ITEMS = 50
_MAX_CONTENT = 500


def read_todos(thread_id: str | None):
    if not thread_id:
        return []
    with connect() as db:
        row = db.execute("SELECT items_json FROM agent_todos WHERE thread_id=?", (thread_id,)).fetchone()
    return json.loads(row["items_json"]) if row else []


def write_todos(thread_id: str | None, todos):
    if not thread_id:
        raise ValueError("Todo 工具需要绑定到一个对话")
    if not isinstance(todos, list) or len(todos) > _MAX_ITEMS:
        raise ValueError(f"Todo 列表最多包含 {_MAX_ITEMS} 项")
    normalized = []
    for item in todos:
        if not isinstance(item, dict):
            raise ValueError("每个 Todo 必须是对象")
        content = str(item.get("content") or "").strip()
        status = str(item.get("status") or "pending")
        active_form = str(item.get("activeForm") or content).strip()
        if not content or len(content) > _MAX_CONTENT:
            raise ValueError(f"Todo 内容长度须为 1–{_MAX_CONTENT} 个字符")
        if status not in _STATUSES:
            raise ValueError("Todo 状态必须是 pending、in_progress 或 completed")
        normalized.append({"content": content, "status": status, "activeForm": active_form[:_MAX_CONTENT]})
    encoded = json.dumps(normalized, ensure_ascii=False)
    with connect() as db:
        if not db.execute("SELECT 1 FROM threads WHERE id=?", (thread_id,)).fetchone():
            raise ValueError("对话不存在或不属于当前用户")
        db.execute(
            "INSERT INTO agent_todos(thread_id,items_json,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(thread_id) DO UPDATE SET items_json=excluded.items_json,updated_at=excluded.updated_at",
            (thread_id, encoded, now()),
        )
    return normalized
