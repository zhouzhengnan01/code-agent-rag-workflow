"""Versioned canvas saves using the same tenant store as conversational drafts."""

import json
import math

from .db import connect, new_id, now, resource_get


class WorkflowConflict(ValueError):
    pass


def prepare_workflow(payload, existing=None):
    from .workflows import validate_workflow
    definition = {**(existing or {}), **payload}
    name = str(definition.get("name", "")).strip()
    if not name or len(name) > 100:
        raise ValueError("工作流名称长度须为 1–100 个字符")
    if len(str(definition.get("description", ""))) > 2000:
        raise ValueError("工作流描述不能超过 2000 个字符")
    definition["name"] = name
    if "enabled" in definition and not isinstance(definition["enabled"], bool):
        raise ValueError("enabled 必须为布尔值")
    expected_version = payload.get("expected_version")
    if expected_version is not None and (isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0):
        raise ValueError("expected_version 必须为非负整数")
    validate_workflow(definition)
    canvas = definition.get("canvas", {})
    if not isinstance(canvas, dict):
        raise ValueError("canvas 必须是对象")
    positions = canvas.get("positions", {})
    if not isinstance(positions, dict):
        raise ValueError("canvas.positions 必须是对象")
    for position in positions.values():
        if not isinstance(position, dict) or any(not isinstance(position.get(k), (int, float)) or isinstance(position.get(k), bool) or not math.isfinite(position[k]) for k in ("x", "y")):
            raise ValueError("节点坐标必须是有限数字")
    viewport = canvas.get("viewport")
    if viewport is not None:
        if not isinstance(viewport, dict) or any(not isinstance(viewport.get(k), (int, float)) or isinstance(viewport.get(k), bool) or not math.isfinite(viewport[k]) for k in ("x", "y", "zoom")) or not .1 <= viewport["zoom"] <= 4:
            raise ValueError("画布视口无效，缩放须在 0.1–4 之间")
    if definition.get("project_id"):
        from .projects import get_project
        if not get_project(definition["project_id"]):
            raise ValueError("关联项目不存在")
    return definition


def save_canvas_workflow(payload, workflow_id=None):
    # Read and compare inside the transaction; timestamps alone have 1s granularity.
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM resources WHERE kind='workflows' AND id=?", (workflow_id,)).fetchone() if workflow_id else None
        if workflow_id and not row:
            raise WorkflowConflict("工作流已被删除，请另存为新工作流")
        existing = {**json.loads(row["data"]), "name": row["name"], "enabled": bool(row["enabled"])} if row else {}
        version = int(existing.get("version") or 0)
        expected = payload.get("expected_version")
        if expected is not None and expected != version:
            raise WorkflowConflict("工作流已被其他操作修改，请导出当前变更后重新加载")
        definition = prepare_workflow(payload, existing)
        for key in ("id", "kind", "created_at", "updated_at", "expected_version"):
            definition.pop(key, None)
        definition["version"] = version + 1
        definition.setdefault("enabled", True)
        workflow_id = workflow_id or new_id("wor")
        timestamp = now()
        data = {k: v for k, v in definition.items() if k not in ("name", "enabled")}
        if row:
            db.execute("UPDATE resources SET name=?,enabled=?,data=?,updated_at=? WHERE id=? AND kind='workflows'", (definition["name"], int(bool(definition["enabled"])), json.dumps(data, ensure_ascii=False), timestamp, workflow_id))
        else:
            db.execute("INSERT INTO resources(id,kind,name,enabled,data,created_at,updated_at) VALUES(?,'workflows',?,?,?,?,?)", (workflow_id, definition["name"], int(bool(definition["enabled"])), json.dumps(data, ensure_ascii=False), timestamp, timestamp))
        db.execute("INSERT INTO workflow_versions(workflow_id,version,definition,created_at) VALUES(?,?,?,?)", (workflow_id, version + 1, json.dumps(definition, ensure_ascii=False), timestamp))
    return resource_get("workflows", workflow_id)
