import asyncio

import pytest

from backend.app import db
from backend.app import domain_tools, intent, projects, workspace
from backend.app.workflows import validate_workflow


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "codezzn.db"))
    db.init_db()
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO threads(id,name,created_at,updated_at) VALUES('thr_test','test',1,1)"
        )


def _definition(name="Flow"):
    return {
        "name": name,
        "nodes": [{"id": "input", "type": "input"}, {"id": "output", "type": "output", "template": "{{input}}"}],
        "edges": [{"source": "input", "target": "output"}],
    }


def test_workflow_draft_save_update_discard_and_assets(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    draft = domain_tools.create_workflow_draft(_definition(), thread_id="thr_test", turn_id="turn_1")
    assert db.resource_list("workflows") == []
    saved = domain_tools.save_workflow_draft(draft["draft_id"], thread_id="thr_test", turn_id="turn_1")
    assert saved["version"] == 1
    assert db.resource_get("workflows", saved["workflow_id"])["name"] == "Flow"

    updated = domain_tools.create_workflow_draft(
        {**_definition("Flow v2"), "workflow_id": saved["workflow_id"]},
        thread_id="thr_test", turn_id="turn_2",
    )
    domain_tools.update_workflow_draft(updated["draft_id"], {"description": "second version"})
    result = domain_tools.save_workflow_draft(updated["draft_id"], thread_id="thr_test", turn_id="turn_2")
    assert result["version"] == 2
    assert db.resource_get("workflows", saved["workflow_id"])["description"] == "second version"
    with db.connect() as connection:
        versions = connection.execute("SELECT version FROM workflow_versions WHERE workflow_id=? ORDER BY version", (saved["workflow_id"],)).fetchall()
        assets = connection.execute("SELECT kind,status FROM resource_assets ORDER BY created_at,id").fetchall()
    assert [row["version"] for row in versions] == [1, 2]
    assert any(row["kind"] == "workflow" for row in assets)
    assert all(row["status"] != "draft" for row in assets)

    discarded = domain_tools.create_workflow_draft(
        {**_definition("Discard me"), "workflow_id": saved["workflow_id"]},
        thread_id="thr_test", turn_id="turn_3",
    )
    assert domain_tools.discard_workflow_draft(discarded["draft_id"])["status"] == "discarded"
    assert db.resource_get("workflows", saved["workflow_id"])["name"] == "Flow v2"


def test_workflow_draft_rejects_stale_update(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    existing = db.resource_save("workflows", _definition())
    draft = domain_tools.create_workflow_draft(
        {**_definition("Proposed"), "workflow_id": existing["id"]},
        thread_id="thr_test", turn_id="turn_1",
    )
    db.resource_save("workflows", {"name": "Other editor", "description": "changed"}, existing["id"])
    with pytest.raises(ValueError, match="其他操作修改"):
        domain_tools.save_workflow_draft(draft["draft_id"], thread_id="thr_test", turn_id="turn_1")
    assert db.resource_get("workflows", existing["id"])["name"] == "Other editor"


def test_semantic_intent_parses_model_json_and_rejects_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(intent, "model_candidates", lambda agent, content: [({"id": "provider", "api_mode": "chat_completions"}, "model")])

    async def fake_completion(provider, model, messages, temperature):
        return {"content": '{"requires_project": true, "kind": "file", "suggested_name": "快速排序", "reason": "需要创建脚本"}'}, {}

    monkeypatch.setattr(intent, "chat_completion", fake_completion)
    result = asyncio.run(intent.classify_intent({}, "能否帮我做一份可运行的 Python 排序脚本？"))
    assert result["requires_project"] is True
    assert result["kind"] == "file"
    assert result["suggested_name"] == "快速排序"

    async def invalid_completion(provider, model, messages, temperature):
        return {"content": "not json"}, {}

    monkeypatch.setattr(intent, "chat_completion", invalid_completion)
    with pytest.raises(ValueError, match="意图识别暂不可用"):
        asyncio.run(intent.classify_intent({}, "写文件"))


def test_workflow_draft_rejects_cycle():
    with pytest.raises(ValueError, match="不能包含环"):
        validate_workflow({"nodes": [{"id": "a"}, {"id": "b"}], "edges": [
            {"source": "a", "target": "b"}, {"source": "b", "target": "a"},
        ]})


def test_project_artifact_keeps_file_versions(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", tmp_path / "workspace")
    monkeypatch.setattr(projects.os, "chown", lambda *args: None)
    project = projects.create_project("Code")
    path = projects.project_root(project["id"]) / "sort.py"
    path.write_text("print(1)\n", encoding="utf-8")
    artifact = projects.record_artifact(project["id"], "thr_test", "turn_1", path, "file")
    path.write_text("print(2)\n", encoding="utf-8")
    projects.record_artifact(project["id"], "thr_test", "turn_2", path, "file")
    versions = projects.list_artifact_versions(project["id"], artifact["id"])
    assert [item["version"] for item in versions] == [2, 1]
    assert projects.get_artifact_version_content(project["id"], artifact["id"], 1) == b"print(1)\n"
    assert projects.get_artifact_version_content(project["id"], artifact["id"], 2) == b"print(2)\n"
