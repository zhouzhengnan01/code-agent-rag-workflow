"""Cross-turn command handles backed only by the isolated Docker broker (not PTY)."""
import json
from pathlib import Path
import uuid

from .db import connect, now
from .sandbox import start_command, command_task
from .workspace import tenant_workspace
from .coding_workspace import logical_root


TERMINAL_SCHEMAS = {
    "terminal_start": {"description": "启动 Docker 沙箱后台命令，跨轮查询日志；不是交互式 TTY，不执行 Windows 主机命令。写命令需审批。", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "mode": {"type": "string", "enum": ["read-only", "workspace-write"]}, "cwd": {"type": "string"}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 86400}}, "required": ["command"]}},
    "terminal_status": {"description": "查询当前用户和工作区启动的后台命令状态", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
    "terminal_logs": {"description": "增量读取后台命令日志，传入上次返回的 next_cursor", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "cursor": {"type": "integer", "minimum": 0}}, "required": ["task_id"]}},
    "terminal_cancel": {"description": "取消当前用户和工作区的后台沙箱命令并清理容器", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
}


def _table(db):
    db.execute("CREATE TABLE IF NOT EXISTS terminal_tasks (task_id TEXT PRIMARY KEY, workspace TEXT NOT NULL, command TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, created_at INTEGER NOT NULL)")


async def execute_terminal(name, args, agent, root):
    if name not in TERMINAL_SCHEMAS: raise ValueError("Unknown terminal operation")
    root = Path(root).resolve()
    if name == "terminal_start":
        if not agent.get("allow_shell", False): raise PermissionError("智能体未启用 shell")
        policy_mode = agent.get("sandbox_mode", "workspace-write")
        if policy_mode not in ("read-only", "workspace-write"): raise PermissionError("Unsupported agent sandbox policy")
        mode = args.get("mode", policy_mode)
        if mode == "workspace-write" and policy_mode == "read-only": raise PermissionError("智能体沙箱为只读")
        raw = str(args.get("cwd") or ".")
        if Path(raw).is_absolute(): raise ValueError("cwd must be relative to task workspace")
        target = (root / raw).resolve()
        try:
            target.relative_to(root)
            cwd = target.relative_to(tenant_workspace().resolve()).as_posix() or "."
        except ValueError: raise ValueError("Terminal cwd escapes isolated workspace")
        task_id = uuid.uuid4().hex
        with connect() as db:
            _table(db)
            db.execute("INSERT INTO terminal_tasks VALUES(?,?,?,?,?,?)", (task_id, str(root), str(args["command"]), mode, "submitting", now()))
        # Identity is durably recorded before network send. A lost response does not launch a second command.
        try: result = await start_command(args["command"], mode, cwd, args.get("timeout_seconds"), task_id)
        except Exception as exc:
            raise RuntimeError(f"Command submission uncertain; query terminal_status task_id={task_id} before retrying: {exc}") from exc
    else:
        task_id = str(args.get("task_id", ""))
        with connect() as db:
            _table(db)
            row = db.execute("SELECT * FROM terminal_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row: raise PermissionError("Unknown command for this user/workspace")
        if logical_root(Path(row['workspace'])) != logical_root(root):
            raise PermissionError('Unknown command for this user/workspace')
        result = await command_task(task_id, cancel=name == "terminal_cancel")
    with connect() as db:
        db.execute("UPDATE terminal_tasks SET status=? WHERE task_id=?", (result["status"], task_id))
    output = result.get("output", "")
    if name == "terminal_logs":
        cursor = args.get("cursor", 0)
        if isinstance(cursor, bool) or not isinstance(cursor, int) or not 0 <= cursor <= len(output): raise ValueError("Invalid log cursor")
        return {"task_id": task_id, "status": result["status"], "output": output[cursor:], "next_cursor": len(output), "truncated": len(output) >= 20000, "pty": False, '_execution_root': row['workspace']}
    return {**result, "task_id": task_id, "pty": False, "log_cursor": 0, '_execution_root': str(root) if name == 'terminal_start' else row['workspace']}
