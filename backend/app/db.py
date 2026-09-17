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
              capability_overrides TEXT NOT NULL DEFAULT '{}',
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL,
              role TEXT NOT NULL, type TEXT NOT NULL DEFAULT 'message', content TEXT NOT NULL,
              meta TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL,
              FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, created_at);
            CREATE TABLE IF NOT EXISTS approvals (
              id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL,
              tool_name TEXT NOT NULL, arguments TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
              created_at INTEGER NOT NULL, resolved_at INTEGER, resolution TEXT,
              FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_approvals_thread ON approvals(thread_id, status, created_at);
            CREATE TABLE IF NOT EXISTS turn_checkpoints (
              id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL UNIQUE,
              agent_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'waiting', state TEXT NOT NULL,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
              FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_turn_checkpoints_thread ON turn_checkpoints(thread_id, status, updated_at);
            CREATE TABLE IF NOT EXISTS turn_events (
              id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL,
              sequence INTEGER NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL, created_at INTEGER NOT NULL,
              UNIQUE(turn_id, sequence), FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_turn_events_turn ON turn_events(turn_id, sequence);
            CREATE TABLE IF NOT EXISTS thread_artifacts (
              id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL,
              kind TEXT NOT NULL, path TEXT NOT NULL, backup_path TEXT, created_at INTEGER NOT NULL,
              FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
              id TEXT PRIMARY KEY, knowledge_id TEXT NOT NULL, source TEXT NOT NULL,
              position INTEGER NOT NULL, content TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_kb ON knowledge_chunks(knowledge_id, position);
            CREATE TABLE IF NOT EXISTS workflow_runs (
              id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, status TEXT NOT NULL,
              input TEXT NOT NULL, output TEXT, trace TEXT NOT NULL DEFAULT '[]',
              state TEXT NOT NULL DEFAULT '{}', error TEXT,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued', payload TEXT NOT NULL DEFAULT '{}',
              result TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
              max_attempts INTEGER NOT NULL DEFAULT 3, available_at INTEGER NOT NULL,
              lease_until INTEGER, worker_id TEXT, parent_task_id TEXT,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_claim ON tasks(status, available_at, created_at);
            CREATE TABLE IF NOT EXISTS task_events (
              id TEXT PRIMARY KEY, task_id TEXT NOT NULL, sequence INTEGER NOT NULL,
              type TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL,
              UNIQUE(task_id, sequence), FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS memories (
              id TEXT PRIMARY KEY, scope TEXT NOT NULL, scope_id TEXT NOT NULL,
              kind TEXT NOT NULL DEFAULT 'experience', content TEXT NOT NULL,
              metadata TEXT NOT NULL DEFAULT '{}', importance REAL NOT NULL DEFAULT 0.5,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, last_accessed_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope, scope_id, updated_at DESC);
            CREATE TABLE IF NOT EXISTS subagent_runs (
              id TEXT PRIMARY KEY, parent_task_id TEXT, parent_thread_id TEXT,
              parent_turn_id TEXT, agent_id TEXT NOT NULL, name TEXT NOT NULL,
              task TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', result TEXT,
              error TEXT, depth INTEGER NOT NULL DEFAULT 1,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_subagents_parent ON subagent_runs(parent_thread_id, parent_turn_id, created_at);
            """
        )
        db.execute("""CREATE TABLE IF NOT EXISTS knowledge_documents (
            id TEXT PRIMARY KEY, knowledge_id TEXT NOT NULL, source TEXT NOT NULL,
            content TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}',
            revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL, UNIQUE(knowledge_id, source)
        )""")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(knowledge_chunks)")}
        if "document_id" not in columns:
            db.execute("ALTER TABLE knowledge_chunks ADD COLUMN document_id TEXT NOT NULL DEFAULT ''")
        if "metadata" not in columns:
            db.execute("ALTER TABLE knowledge_chunks ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
        approval_columns = {row["name"] for row in db.execute("PRAGMA table_info(approvals)")}
        if "tool_call_id" not in approval_columns:
            db.execute("ALTER TABLE approvals ADD COLUMN tool_call_id TEXT")
        if "resumable" not in approval_columns:
            db.execute("ALTER TABLE approvals ADD COLUMN resumable INTEGER NOT NULL DEFAULT 0")
        thread_columns = {row["name"] for row in db.execute("PRAGMA table_info(threads)")}
        if "capability_overrides" not in thread_columns:
            db.execute("ALTER TABLE threads ADD COLUMN capability_overrides TEXT NOT NULL DEFAULT '{}'")
        workflow_columns = {row["name"] for row in db.execute("PRAGMA table_info(workflow_runs)")}
        if "state" not in workflow_columns:
            db.execute("ALTER TABLE workflow_runs ADD COLUMN state TEXT NOT NULL DEFAULT '{}'")
        if "error" not in workflow_columns:
            db.execute("ALTER TABLE workflow_runs ADD COLUMN error TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document ON knowledge_chunks(document_id)")


def resource_list(kind):
    with connect() as db:
        rows = db.execute("SELECT * FROM resources WHERE kind=? ORDER BY updated_at DESC", (kind,)).fetchall()
    return [_resource(row) for row in rows]


def resource_get(kind, item_id):
    with connect() as db:
        row = db.execute("SELECT * FROM resources WHERE kind=? AND id=?", (kind, item_id)).fetchone()
    return _resource(row) if row else None


def resource_save(kind, payload, item_id=None):
    creating = item_id is None
    item_id = item_id or new_id(kind[:3])
    timestamp = now()
    if kind == "knowledge" and creating and "backend" not in payload:
        payload = {"backend": os.getenv("CODEZZN_KNOWLEDGE_BACKEND", "local"), **payload}
    name = str(payload.get("name") or "Untitled").strip()
    enabled = 1 if payload.get("enabled", True) else 0
    data = {k: v for k, v in payload.items() if k not in ("id", "kind", "name", "enabled", "created_at", "updated_at")}
    with connect() as db:
        old_row = db.execute("SELECT * FROM resources WHERE id=? AND kind=?", (item_id, kind)).fetchone()
        old = _resource(old_row) if old_row else {}
        created = old_row["created_at"] if old_row else timestamp
        if old_row:
            merged = {k: v for k, v in old.items() if k not in ("id", "kind", "name", "enabled", "created_at", "updated_at")}
            merged.update(data)
            data = merged
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
            db.execute("DELETE FROM knowledge_documents WHERE knowledge_id=?", (item_id,))
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
        "builtin_tools": ["knowledge_search", "list_files", "read_file", "write_file", "apply_patch", "run_shell", "git_status", "git_diff", "git_log", "review"],
        "max_tool_rounds": 6, "auto_approve": False, "sandbox_mode": "read-only", "allow_shell": False
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
