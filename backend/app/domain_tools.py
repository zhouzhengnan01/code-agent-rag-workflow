"""Tenant-scoped project and workflow actions exposed to the agent.

The agent uses the same persistence model as the UI. Workflow edits are staged
as drafts, validated before saving, and guarded by optimistic concurrency.
"""

import json
import hashlib

from .db import connect, new_id, now, resource_get, resource_list, resource_save
from .projects import create_project, get_project, list_artifacts, list_projects
from .tasks import enqueue_task


def _asset(thread_id, turn_id, kind, resource_id, name, project_id=None, status="ready"):
    if not thread_id or not turn_id:
        return None
    asset_id = new_id("asset")
    with connect() as db:
        db.execute(
            "INSERT INTO resource_assets(id,thread_id,turn_id,kind,resource_id,name,project_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (asset_id, thread_id, turn_id, kind, resource_id, name, project_id, status, now()),
        )
    return {"id": asset_id, "kind": kind, "resource_id": resource_id, "name": name, "project_id": project_id, "status": status}


def _workflow_fingerprint(row):
    if row is None:
        return None
    payload = json.dumps([row["name"], row["enabled"], row["data"]], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def list_project_tools():
    return [{"id": item["id"], "name": item["name"], "description": item["description"], "updated_at": item["updated_at"]} for item in list_projects()]


def create_project_tool(name, description, *, thread_id, turn_id):
    project = create_project(name, description)
    select_project_tool(project["id"], thread_id=thread_id, turn_id=turn_id, record_link=False)
    _asset(thread_id, turn_id, "project", project["id"], project["name"], project["id"])
    return project


def select_project_tool(project_id, *, thread_id, turn_id, record_link=True):
    project = get_project(project_id)
    if not project:
        raise ValueError("项目不存在")
    if thread_id and turn_id:
        with connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO thread_projects(thread_id,project_id,created_at) VALUES(?,?,?)",
                (thread_id, project_id, now()),
            )
            db.execute("UPDATE threads SET active_project_id=?,updated_at=? WHERE id=?", (project_id, now(), thread_id))
            db.execute(
                "INSERT INTO turn_projects(turn_id,thread_id,project_id,save_to_project,created_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(turn_id) DO UPDATE SET project_id=excluded.project_id,save_to_project=excluded.save_to_project",
                (turn_id, thread_id, project_id, 1, now()),
            )
    if record_link:
        _asset(thread_id, turn_id, "project", project_id, project["name"], project_id, "linked")
    return project


def _draft_payload(arguments, existing=None):
    from .workflows import validate_workflow
    current = existing or {}
    name = str(arguments.get("name", current.get("name", ""))).strip()
    description = str(arguments.get("description", current.get("description", ""))).strip()
    if not name or len(name) > 100:
        raise ValueError("Workflow 名称长度须为 1–100 个字符")
    if len(description) > 2000:
        raise ValueError("Workflow 描述不能超过 2000 个字符")
    definition = {
        "nodes": arguments.get("nodes", current.get("nodes", [])),
        "edges": arguments.get("edges", current.get("edges", [])),
        "max_parallel": arguments.get("max_parallel", current.get("max_parallel", 4)),
    }
    if not isinstance(definition["nodes"], list) or len(definition["nodes"]) > 100:
        raise ValueError("Workflow nodes 必须是最多 100 个节点的数组")
    if not isinstance(definition["edges"], list) or len(definition["edges"]) > 300:
        raise ValueError("Workflow edges 必须是最多 300 条边的数组")
    validate_workflow(definition)
    return name, description, definition


def create_workflow_draft(arguments, *, thread_id, turn_id):
    workflow_id = arguments.get("workflow_id")
    existing = resource_get("workflows", workflow_id) if workflow_id else None
    if workflow_id and not existing:
        raise ValueError("Workflow 不存在")
    project_id = arguments.get("project_id") or (existing or {}).get("project_id")
    if existing and existing.get("project_id") and project_id != existing["project_id"]:
        raise ValueError("不能在编辑草稿时把 Workflow 移到另一个项目")
    if project_id and not get_project(project_id):
        raise ValueError("项目不存在")
    name, description, definition = _draft_payload(arguments, existing)
    draft_id, timestamp = new_id("wfd"), now()
    with connect() as db:
        base = db.execute("SELECT name,enabled,data FROM resources WHERE id=? AND kind='workflows'", (workflow_id,)).fetchone() if workflow_id else None
        db.execute(
            "INSERT INTO workflow_drafts(id,workflow_id,base_updated_at,base_fingerprint,name,description,definition,project_id,status,thread_id,turn_id,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,'draft',?,?,?,?)",
            (draft_id, workflow_id, existing["updated_at"] if existing else None, _workflow_fingerprint(base), name, description,
             json.dumps(definition, ensure_ascii=False), project_id, thread_id, turn_id, timestamp, timestamp),
        )
    _asset(thread_id, turn_id, "workflow_draft", draft_id, name, project_id, "draft")
    return {"draft_id": draft_id, "workflow_id": workflow_id, "name": name, "definition": definition, "status": "draft"}


def get_workflow_draft(draft_id):
    with connect() as db:
        row = db.execute("SELECT * FROM workflow_drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["definition"] = json.loads(result["definition"])
    return result


def update_workflow_draft(draft_id, arguments):
    draft = get_workflow_draft(draft_id)
    if not draft or draft["status"] != "draft":
        raise ValueError("Workflow 草稿不存在或已处理")
    name, description, definition = _draft_payload(arguments, {**draft["definition"], "name": draft["name"], "description": draft["description"]})
    with connect() as db:
        db.execute(
            "UPDATE workflow_drafts SET name=?,description=?,definition=?,updated_at=? WHERE id=? AND status='draft'",
            (name, description, json.dumps(definition, ensure_ascii=False), now(), draft_id),
        )
    return {"draft_id": draft_id, "workflow_id": draft["workflow_id"], "name": name, "definition": definition, "status": "draft"}


def save_workflow_draft(draft_id, *, thread_id, turn_id):
    from .workflows import validate_workflow
    draft = get_workflow_draft(draft_id)
    if not draft or draft["status"] != "draft":
        raise ValueError("Workflow 草稿不存在或已处理")
    validate_workflow(draft["definition"])
    current = resource_get("workflows", draft["workflow_id"]) if draft["workflow_id"] else None
    if draft["workflow_id"] and (not current or current["updated_at"] != draft["base_updated_at"]):
        raise ValueError("Workflow 已被其他操作修改；请重新读取后创建新草稿")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if draft["workflow_id"]:
            row = db.execute("SELECT name,enabled,data,updated_at FROM resources WHERE id=? AND kind='workflows'", (draft["workflow_id"],)).fetchone()
            if not row or _workflow_fingerprint(row) != draft["base_fingerprint"]:
                raise ValueError("Workflow 已被其他操作修改；请重新读取后创建新草稿")
        row = db.execute("SELECT status FROM workflow_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["status"] != "draft":
            raise ValueError("Workflow 草稿已处理")
        workflow_id = draft["workflow_id"] or new_id("wor")
        version = int((current or {}).get("version") or 0) + 1
        payload = {"name": draft["name"], "description": draft["description"], **draft["definition"],
                   "project_id": draft["project_id"], "version": version, "enabled": True}
        data = {key: value for key, value in payload.items() if key not in {"name", "enabled"}}
        timestamp = now()
        if current:
            db.execute(
                "UPDATE resources SET name=?,enabled=1,data=?,updated_at=? WHERE id=? AND kind='workflows'",
                (draft["name"], json.dumps(data, ensure_ascii=False), timestamp, workflow_id),
            )
        else:
            db.execute(
                "INSERT INTO resources(id,kind,name,enabled,data,created_at,updated_at) VALUES(?,'workflows',?,1,?,?,?)",
                (workflow_id, draft["name"], json.dumps(data, ensure_ascii=False), timestamp, timestamp),
            )
        db.execute(
            "INSERT INTO workflow_versions(workflow_id,version,definition,created_at) VALUES(?,?,?,?)",
            (workflow_id, version, json.dumps(payload, ensure_ascii=False), timestamp),
        )
        db.execute("UPDATE workflow_drafts SET status='saved',workflow_id=?,updated_at=? WHERE id=?", (workflow_id, timestamp, draft_id))
        db.execute("UPDATE resource_assets SET status='saved' WHERE kind='workflow_draft' AND resource_id=?", (draft_id,))
    _asset(thread_id, turn_id, "workflow", workflow_id, draft["name"], draft["project_id"])
    return {"workflow_id": workflow_id, "version": version, "name": draft["name"], "status": "saved"}


def discard_workflow_draft(draft_id):
    with connect() as db:
        row = db.execute("SELECT status FROM workflow_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["status"] != "draft":
            raise ValueError("Workflow 草稿不存在或已处理")
        db.execute("UPDATE workflow_drafts SET status='discarded',updated_at=? WHERE id=?", (now(), draft_id))
        db.execute("UPDATE resource_assets SET status='discarded' WHERE kind='workflow_draft' AND resource_id=?", (draft_id,))
    return {"draft_id": draft_id, "status": "discarded"}


def enqueue_workflow_run(workflow_id, input_value, *, thread_id, turn_id):
    from .workflows import validate_workflow
    workflow = resource_get("workflows", workflow_id)
    if not workflow or not workflow.get("enabled", True):
        raise ValueError("Workflow 不存在或已禁用")
    validate_workflow(workflow)
    run_id, timestamp = new_id("run"), now()
    with connect() as db:
        db.execute(
            "INSERT INTO workflow_runs(id,workflow_id,status,input,state,created_at,updated_at) VALUES(?,?,'queued',?,?,?,?)",
            (run_id, workflow_id, json.dumps(input_value, ensure_ascii=False), "{}", timestamp, timestamp),
        )
    try:
        task = enqueue_task("workflow", workflow.get("name") or "Workflow", {"workflow_id": workflow_id, "run_id": run_id, "input": input_value}, 3)
    except Exception as exc:
        with connect() as db:
            db.execute(
                "UPDATE workflow_runs SET status='failed',output=?,updated_at=? WHERE id=?",
                (json.dumps({"error": "任务入队失败", "detail": str(exc)}, ensure_ascii=False), now(), run_id),
            )
        raise
    _asset(thread_id, turn_id, "workflow_run", run_id, workflow["name"], workflow.get("project_id"), "queued")
    return {"run_id": run_id, "task_id": task["id"], "workflow_id": workflow_id, "status": "queued"}


def get_workflow_run(run_id):
    with connect() as db:
        row = db.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise ValueError("Workflow 运行不存在")
    result = dict(row)
    for key in ("input", "output", "trace"):
        result[key] = json.loads(result[key] or "null")
    return result


def list_workflow_versions(workflow_id):
    if not resource_get("workflows", workflow_id):
        return None
    with connect() as db:
        rows = db.execute(
            "SELECT version,created_at FROM workflow_versions WHERE workflow_id=? ORDER BY version DESC",
            (workflow_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_workflow_version(workflow_id, version):
    if not resource_get("workflows", workflow_id):
        return None
    with connect() as db:
        row = db.execute(
            "SELECT definition FROM workflow_versions WHERE workflow_id=? AND version=?",
            (workflow_id, version),
        ).fetchone()
    return json.loads(row["definition"]) if row else None


def list_workflow_tools():
    return [{"id": item["id"], "name": item["name"], "description": item.get("description", ""),
             "project_id": item.get("project_id"), "version": item.get("version", 0), "updated_at": item["updated_at"]}
            for item in resource_list("workflows")]


def list_project_artifacts_tool(project_id):
    result = list_artifacts(project_id)
    if result is None:
        raise ValueError("项目不存在")
    return result
