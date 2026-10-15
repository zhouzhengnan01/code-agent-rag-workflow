"""Tenant-local, thread-authorized persistent agent mailboxes; no task launch."""
import json

from .db import connect, new_id, now, resource_get


SCHEMAS = {
    "team_send": {"description": "给本对话已授权团队成员发送持久消息；不会创建任务或授予额外权限。", "parameters": {"type": "object", "properties": {"agent_id": {"type": "string"}, "message": {"type": "string", "maxLength": 16000}}, "required": ["agent_id", "message"]}},
    "team_receive": {"description": "读取本对话发给自己的持久团队消息；默认只读未读消息并标记已读。", "parameters": {"type": "object", "properties": {"unread_only": {"type": "boolean"}, "limit": {"type": "integer", "maximum": 100}}}},
}


def _table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS coding_team_messages (
        id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT,
        sender_agent_id TEXT NOT NULL, receiver_agent_id TEXT NOT NULL,
        sender_task_id TEXT, content TEXT NOT NULL, created_at INTEGER NOT NULL,
        read_at INTEGER)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_coding_mailbox ON coding_team_messages(thread_id,receiver_agent_id,read_at,created_at)")


def _members(agent, thread_id, task_id):
    if not thread_id or not agent.get("id"):
        raise PermissionError("团队消息需要已绑定的对话与智能体")
    with connect() as db:
        thread = db.execute("SELECT agent_id FROM threads WHERE id=?", (thread_id,)).fetchone()
        if not thread:
            raise PermissionError("对话不存在或不属于当前用户")
        leader = resource_get("agents", thread["agent_id"]) or {}
        members = {thread["agent_id"], *(leader.get("subagent_ids") or [])}
        if leader.get("team_id"):
            team = resource_get("agent_teams", leader["team_id"])
            if team and team.get("enabled", True):
                members.update(team.get("member_ids") or [])
        if task_id:
            task = db.execute("SELECT parent_task_id,payload FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not task:
                raise PermissionError("团队任务不存在")
            payload = json.loads(task["payload"] or "{}")
            if payload.get("thread_id") != thread_id or payload.get("agent_id") != agent["id"]:
                raise PermissionError("任务的智能体或对话不匹配")
            parent_id = task["parent_task_id"] or task_id
            relatives = db.execute("SELECT id,payload FROM tasks WHERE id=? OR parent_task_id=?", (parent_id, parent_id)).fetchall()
            family = set()
            for row in relatives:
                value = json.loads(row["payload"] or "{}")
                if value.get("thread_id") == thread_id and value.get("agent_id"):
                    family.add(value["agent_id"])
            if agent["id"] in family:
                members.update(family)
        if agent["id"] not in members:
            raise PermissionError("当前智能体不是本对话已授权团队成员")
    return {value for value in members if value and resource_get("agents", value)}


async def execute(name, args, agent, thread_id=None, turn_id=None, current_task_id=None):
    members = _members(agent, thread_id, current_task_id)
    if name == "team_send":
        receiver = str(args.get("agent_id") or "")
        content = str(args.get("message") or "").strip()
        if receiver not in members:
            raise PermissionError("只能向本对话已授权的团队成员发送消息")
        if not content or len(content) > 16000:
            raise ValueError("团队消息长度须为 1–16000 字符")
        message_id = new_id("msg")
        with connect() as db:
            _table(db)
            db.execute("INSERT INTO coding_team_messages(id,thread_id,turn_id,sender_agent_id,receiver_agent_id,sender_task_id,content,created_at) VALUES(?,?,?,?,?,?,?,?)", (message_id, thread_id, turn_id, agent["id"], receiver, current_task_id, content, now()))
        return {"id": message_id, "agent_id": receiver, "delivered": True, "task_created": False}
    if name == "team_receive":
        limit = max(1, min(100, int(args.get("limit", 30))))
        with connect() as db:
            _table(db)
            db.execute("BEGIN IMMEDIATE")
            where = " AND read_at IS NULL" if args.get("unread_only", True) else ""
            rows = db.execute("SELECT * FROM coding_team_messages WHERE thread_id=? AND receiver_agent_id=?" + where + " ORDER BY created_at,id LIMIT ?", (thread_id, agent["id"], limit)).fetchall()
            for row in rows:
                db.execute("UPDATE coding_team_messages SET read_at=COALESCE(read_at,?) WHERE id=?", (now(), row["id"]))
        return {"messages": [dict(row) for row in rows], "count": len(rows)}
    raise ValueError("未知的团队消息工具")
