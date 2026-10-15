import asyncio
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app import coding_api, coding_workspace as cw, db, engineering, workspace


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", root)
    token = db.use_tenant(None)
    db.init_db()
    db.resource_save("agents", {"name": "Coder", "context_token_budget": 8000}, "coder")
    with db.connect() as connection:
        connection.execute("INSERT INTO threads(id,name,agent_id,created_at,updated_at) VALUES('thread','Test','coder',1,1)")
    app = FastAPI()
    app.include_router(coding_api.router)
    with TestClient(app) as client:
        yield root, client
    db.reset_tenant(token)


def test_state_read_only_does_not_create_workspace_or_engineering_tables(environment):
    root, client = environment
    before = set(root.iterdir())
    response = client.get("/api/threads/thread/coding/state")
    assert response.status_code == 200
    state = response.json()
    assert state["workspace"]["mode"] == "canonical-readonly"
    assert state["engineering"] == {} and state["checkpoints"] == []
    assert state["context"]["context_token_budget"] == 8000
    assert set(root.iterdir()) == before
    with db.connect() as connection:
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name='engineering_state'").fetchone() is None


def test_readonly_plan_hooks_discovery_and_write_tool_denials(environment):
    root, client = environment
    (root / "package.json").write_text(json.dumps({"scripts": {"test": "node test.js"}}))
    endpoint = "/api/threads/thread/coding/inspect"
    response = client.post(endpoint, json={"name": "plan_manage", "args": {"action": "get"}})
    assert response.json()["result"]["status"] == "none"
    assert client.post(endpoint, json={"name": "hook_manage", "args": {"action": "get"}}).json()["result"] == {"hooks": []}
    discovery = client.post(endpoint, json={"name": "quality_discover", "args": {}})
    assert discovery.status_code == 200
    assert "npm run test" in discovery.text
    for name, args in (("task_rewind", {"checkpoint_id": "no"}), ("quality_run", {"checks": []}), ("plan_manage", {"action": "approve"}), ("hook_manage", {"action": "set", "hooks": []}), ("run_shell", {"command": "touch unsafe"})):
        assert client.post(endpoint, json={"name": name, "args": args}).status_code == 403
    assert not (root / "unsafe").exists()
    assert not (root / ".codezzn-execution").exists()


def test_state_and_diff_match_existing_manifest_without_initialization(environment, monkeypatch):
    root, client = environment
    async def no_git(*args, **kwargs):
        return {"exit_code": 128}
    monkeypatch.setattr(cw, "run_command", no_git)
    item = asyncio.run(cw.prepare_coding_workspace(task_id="task", thread_id="thread", turn_id="turn"))
    execution = cw.workspace_path(item)
    (execution / "main.py").write_text("before\n")
    checkpoint = asyncio.run(engineering.execute("task_checkpoint", {"paths": ["main.py"], "label": "Original"}, {}, execution, "thread", "turn"))
    asyncio.run(engineering.execute("plan_manage", {"action": "create", "steps": [{"content": "test", "status": "pending"}]}, {}, execution, "thread", "turn"))
    (execution / "main.py").write_text("after\n")
    before = item["metadata"]
    state = client.get("/api/threads/thread/coding/state").json()
    assert state["workspace"]["path"] == item["path"]
    assert state["engineering"]["plan"]["steps"][0]["content"] == "test"
    assert state["checkpoints"][0]["label"] == "Original"
    diff = client.post("/api/threads/thread/coding/inspect", json={"name": "task_diff", "args": {"checkpoint_id": checkpoint["checkpoint_id"]}})
    assert diff.status_code == 200
    assert "-before" in diff.json()["result"]["changes"][0]["diff"]
    assert (execution / "main.py").read_text() == "after\n"
    assert (root / before).is_file()


def test_unknown_thread_and_other_thread_checkpoint_are_hidden(environment):
    root, client = environment
    with db.connect() as connection:
        connection.execute("INSERT INTO threads(id,name,agent_id,created_at,updated_at) VALUES('other','Other','coder',1,1)")
    checkpoint = asyncio.run(engineering.execute("task_checkpoint", {"paths": ["missing.py"]}, {}, root, "other", "turn"))
    assert client.get("/api/threads/missing/coding/state").status_code == 404
    response = client.post("/api/threads/thread/coding/inspect", json={"name": "task_diff", "args": {"checkpoint_id": checkpoint["checkpoint_id"]}})
    assert response.status_code == 404


def test_context_never_returns_saved_messages_or_private_reasoning(environment):
    root, client = environment
    saved = {"round": 3, "model": "test-model", "messages": [{"role": "system", "content": "secret-system-prompt"}], "reasoning": "private-chain-of-thought", "usage": {"total_tokens": 42}}
    with db.connect() as connection:
        connection.execute("INSERT INTO agent_runs(id,thread_id,agent_id,status,state,created_at,updated_at) VALUES('run','thread','coder','running',?,1,1)", (json.dumps(saved),))
    response = client.get("/api/threads/thread/coding/state")
    assert response.status_code == 200
    assert "secret-system-prompt" not in response.text and "private-chain-of-thought" not in response.text
    assert response.json()["context"]["round"] == 3


def test_context_can_be_cleared_and_restored(environment):
    root, client = environment
    token = cw.use_coding_workspace(None)
    assert cw.current_coding_workspace() is None
    cw.reset_coding_workspace(token)


def test_other_tenant_cannot_inspect_global_thread(environment):
    root, client = environment
    token = db.use_tenant("usr_0123456789abcdef")
    try:
        db.init_db()
        assert client.get("/api/threads/thread/coding/state").status_code == 404
        assert client.post("/api/threads/thread/coding/inspect", json={"name": "quality_discover", "args": {}}).status_code == 404
    finally:
        db.reset_tenant(token)


def test_canonical_project_fallback_does_not_create_execution_copy(environment):
    root, client = environment
    project = "prj_0123456789abcdef"
    canonical = cw.project_root(project)
    canonical.mkdir(parents=True)
    with db.connect() as connection:
        connection.execute("INSERT INTO projects(id,name,description,created_at,updated_at) VALUES(?,'Project','',1,1)", (project,))
        connection.execute("UPDATE threads SET active_project_id=? WHERE id='thread'", (project,))
    result = client.get("/api/threads/thread/coding/state").json()
    assert result["workspace"]["path"] == "projects/" + project
    assert not (root / ".codezzn-execution").exists()
