import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager


DATA_DIR = os.getenv("CODEZZN_DATA_DIR", os.path.join(os.getcwd(), "data"))
DB_PATH = os.path.join(DATA_DIR, "codezzn.db")
_lock = threading.RLock()


def now():
    return int(time.time())


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


@contextmanager
def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db():
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS resources (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 1, data TEXT NOT NULL DEFAULT '{}',
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_resources_kind ON resources(kind, updated_at DESC);
            CREATE TABLE IF NOT EXISTS threads (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, agent_id TEXT,
              status TEXT NOT NULL DEFAULT 'idle', archived INTEGER NOT NULL DEFAULT 0,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL,
              role TEXT NOT NULL, type TEXT NOT NULL DEFAULT 'message', content TEXT NOT NULL,
              meta TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL,
              FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, created_at);
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
              id TEXT PRIMARY KEY, knowledge_id TEXT NOT NULL, source TEXT NOT NULL,
              position INTEGER NOT NULL, content TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_kb ON knowledge_chunks(knowledge_id, position);
            CREATE TABLE IF NOT EXISTS workflow_runs (
              id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, status TEXT NOT NULL,
              input TEXT NOT NULL, output TEXT, trace TEXT NOT NULL DEFAULT '[]',
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            """
        )


def resource_list(kind):
    with connect() as db:
        rows = db.execute("SELECT * FROM resources WHERE kind=? ORDER BY updated_at DESC", (kind,)).fetchall()
    return [_resource(row) for row in rows]


def resource_get(kind, item_id):
    with connect() as db:
        row = db.execute("SELECT * FROM resources WHERE kind=? AND id=?", (kind, item_id)).fetchone()
    return _resource(row) if row else None


def resource_save(kind, payload, item_id=None):
    item_id = item_id or new_id(kind[:3])
    timestamp = now()
    name = str(payload.get("name") or "Untitled").strip()
    enabled = 1 if payload.get("enabled", True) else 0
    data = {k: v for k, v in payload.items() if k not in ("id", "kind", "name", "enabled", "created_at", "updated_at")}
    with connect() as db:
        old = db.execute("SELECT created_at FROM resources WHERE id=? AND kind=?", (item_id, kind)).fetchone()
        created = old["created_at"] if old else timestamp
        db.execute(
            "INSERT OR REPLACE INTO resources(id,kind,name,enabled,data,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (item_id, kind, name, enabled, json.dumps(data, ensure_ascii=False), created, timestamp),
        )
    return resource_get(kind, item_id)


def resource_delete(kind, item_id):
    with connect() as db:
        cur = db.execute("DELETE FROM resources WHERE kind=? AND id=?", (kind, item_id))
        if kind == "knowledge":
            db.execute("DELETE FROM knowledge_chunks WHERE knowledge_id=?", (item_id,))
    return cur.rowcount > 0


def _resource(row):
    value = dict(row)
    data = json.loads(value.pop("data"))
    value["enabled"] = bool(value["enabled"])
    value.update(data)
    return value


def seed_defaults():
    if resource_list("agents"):
        return
    provider = resource_save("providers", {
        "name": "OpenAI Compatible", "type": "openai", "base_url": "https://api.openai.com/v1",
        "api_key": "", "models": ["gpt-4.1-mini"], "default_model": "gpt-4.1-mini"
    })
    resource_save("agents", {
        "name": "Codezzn Assistant", "description": "通用智能体",
        "system_prompt": "你是 Codezzn 智能体。准确、务实地完成任务；调用工具前确认参数，清晰报告结果。",
        "provider_id": provider["id"], "model": "gpt-4.1-mini", "temperature": 0.2,
        "skill_ids": [], "knowledge_ids": [], "mcp_server_ids": [],
        "builtin_tools": ["knowledge_search", "list_files", "read_file", "write_file", "run_shell"],
        "max_tool_rounds": 6
    })


def migrate_bailian_providers():
    # Keep existing credentials while correcting legacy Qwen protocol paths/model IDs.
    from .model import is_bailian, normalize_provider

    for provider in resource_list("providers"):
        if not is_bailian(provider):
            continue
        normalized = normalize_provider(provider)
        comparable_keys = ("type", "base_url", "models", "default_model")
        if any(provider.get(key) != normalized.get(key) for key in comparable_keys):
            resource_save("providers", normalized, provider["id"])

    providers = resource_list("providers")
    provider_by_id = {provider["id"]: provider for provider in providers}
    fallback = next((provider for provider in providers if provider.get("enabled")), None)
    for agent in resource_list("agents"):
        provider = provider_by_id.get(agent.get("provider_id"))
        changed = False
        if provider is None and fallback:
            provider = fallback
            agent["provider_id"] = provider["id"]
            agent["model"] = provider.get("default_model")
            changed = True
        if provider and is_bailian(provider):
            from .model import normalize_qwen_model

            model = normalize_qwen_model(agent.get("model"))
            if not model.startswith("qwen"):
                model = normalize_provider(provider).get("default_model")
            if model != agent.get("model"):
                agent["model"] = model
                changed = True
        if changed:
            resource_save("agents", agent, agent["id"])
