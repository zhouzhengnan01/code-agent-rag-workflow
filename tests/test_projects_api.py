from fastapi.testclient import TestClient
import pytest
import sqlite3

from backend.app import db, main, workspace
from backend.app.projects import get_turn_project, project_root, record_artifact


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "shared.db"))
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", tmp_path / "workspace")
    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "true")
    monkeypatch.delenv("CODEZZN_ADMIN_KEY", raising=False)
    monkeypatch.delenv("CODEZZN_LEGACY_OWNER_GITHUB_ID", raising=False)
    db.init_db()


def _register(client, email):
    response = client.post("/api/auth/register", json={
        "name": email, "email": email, "password": "password-12345",
    })
    assert response.status_code == 200
    return response.cookies["codezzn_session"]


def test_existing_threads_schema_migrates_without_losing_messages(tmp_path, monkeypatch):
    database = tmp_path / "old.db"
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TABLE threads (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, agent_id TEXT,
            status TEXT NOT NULL DEFAULT 'idle', archived INTEGER NOT NULL DEFAULT 0,
            capability_overrides TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        )""")
        connection.execute("INSERT INTO threads(id,name,created_at,updated_at) VALUES('thr_existing','旧对话',1,1)")
    monkeypatch.setattr(db, "DB_PATH", str(database))
    db.init_db()
    with db.connect() as connection:
        existing = connection.execute("SELECT name,active_project_id FROM threads WHERE id='thr_existing'").fetchone()
        assert dict(existing) == {"name": "旧对话", "active_project_id": None}
        assert connection.execute("SELECT count(*) FROM projects").fetchone()[0] == 0


def test_project_turn_artifact_and_user_isolation(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    async def fake_agent(agent, history, content, **kwargs):
        choice = get_turn_project(kwargs["turn_id"])
        assert choice == {"project_id": project_id, "save_to_project": True}
        root = project_root(project_id)
        root.mkdir(parents=True, exist_ok=True)
        file = root / "quicksort.py"
        file.write_text("print('sort')\n", encoding="utf-8")
        record_artifact(project_id, kwargs["thread_id"], kwargs["turn_id"], file, "code")
        return {"status": "completed", "content": "已保存", "events": [], "usage": {}, "runtime": {}, "sources": []}

    monkeypatch.setattr(main, "run_agent_isolated", fake_agent)
    with TestClient(main.app) as client:
        first_cookie = _register(client, "project-first@example.com")
        agent_id = client.post("/api/resources/agents", json={
            "name": "Writer", "sandbox_mode": "workspace-write", "builtin_tools": ["write_file"],
        }).json()["id"]
        project_response = client.post("/api/projects", json={"name": "排序示例", "description": "测试项目"})
        assert project_response.status_code == 200
        project_id = project_response.json()["id"]
        assert project_response.json()["name"] == "排序示例"
        assert client.patch(f"/api/projects/{project_id}", json={"name": "排序项目"}).json()["name"] == "排序项目"
        thread_id = client.post("/api/threads", json={"agent_id": agent_id}).json()["id"]
        response = client.post(f"/api/threads/{thread_id}/turns", json={
            "agent_id": agent_id, "content": "写个快速排序", "project_id": project_id, "save_to_project": True,
        })
        assert response.status_code == 200, response.text
        streamed = client.post(f"/api/threads/{thread_id}/turns/stream", json={
            "agent_id": agent_id, "content": "更新快速排序", "project_id": project_id, "save_to_project": True,
        })
        assert streamed.status_code == 200, streamed.text
        assert '"type": "turn_result"' in streamed.text
        thread_data = client.get(f"/api/threads/{thread_id}").json()
        assert thread_data["active_project_id"] == project_id
        assert thread_data["project_ids"] == [project_id]
        saved_answers = [item for item in thread_data["messages"] if item["role"] == "assistant"]
        assert saved_answers[0]["project_choice"] == {"project_id": project_id, "save_to_project": True}
        assert saved_answers[-1]["project_artifacts"][0]["path"] == "quicksort.py"
        artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()["data"]
        assert [artifact["path"] for artifact in artifacts] == ["quicksort.py"]
        download = client.get(f"/api/projects/{project_id}/artifacts/{artifacts[0]['id']}/download")
        assert download.status_code == 200
        assert download.content == b"print('sort')\n"
        preview = client.get(f"/api/projects/{project_id}/artifacts/{artifacts[0]['id']}/content")
        assert preview.json()["content"] == "print('sort')\n"

        second_cookie = _register(client, "project-second@example.com")
        assert second_cookie != first_cookie
        assert client.get("/api/projects").json()["data"] == []
        assert client.get(f"/api/projects/{project_id}").status_code == 404
        assert client.get(f"/api/projects/{project_id}/artifacts").status_code == 404
        assert client.get(f"/api/projects/{project_id}/artifacts/{artifacts[0]['id']}/download").status_code == 404
        assert client.get(f"/api/projects/{project_id}/artifacts/{artifacts[0]['id']}/content").status_code == 404
        other_thread = client.post("/api/threads", json={}).json()["id"]
        assert client.patch(f"/api/threads/{other_thread}", json={"active_project_id": project_id}).status_code == 404
        other_agent = client.post("/api/resources/agents", json={"name": "Other"}).json()["id"]
        assert client.post(f"/api/threads/{other_thread}/turns", json={
            "agent_id": other_agent, "content": "跨账号写入", "project_id": project_id,
            "save_to_project": True,
        }).status_code == 404
        client.cookies.set("codezzn_session", first_cookie)
        assert client.get(f"/api/projects/{project_id}").status_code == 200


def test_project_choice_requires_existing_project_and_safe_paths(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    async def answer_only(agent, history, content, **kwargs):
        return {"status": "completed", "content": "仅回答", "events": [], "usage": {}, "runtime": {}, "sources": []}

    monkeypatch.setattr(main, "run_agent_isolated", answer_only)
    with TestClient(main.app) as client:
        _register(client, "safe@example.com")
        user_id = client.get("/api/auth/me").json()["user"]["id"]
        thread_id = client.post("/api/threads", json={}).json()["id"]
        project_id = client.post("/api/projects", json={"name": "Safe"}).json()["id"]
        agent_id = client.post("/api/resources/agents", json={"name": "Answer"}).json()["id"]
        no_save = client.post(f"/api/threads/{thread_id}/turns", json={
            "agent_id": agent_id, "content": "只回答", "project_id": project_id, "save_to_project": False,
        })
        assert no_save.status_code == 200
        token = db.use_tenant(user_id)
        try:
            assert get_turn_project(no_save.json()["turn_id"]) == {"project_id": project_id, "save_to_project": False}
        finally:
            db.reset_tenant(token)
        legacy = client.post(f"/api/threads/{thread_id}/turns", json={
            "agent_id": agent_id, "content": "旧版调用",
        })
        assert legacy.status_code == 200
        bad_save = client.post(f"/api/threads/{thread_id}/turns", json={
            "agent_id": agent_id, "content": "保存但未选项目", "save_to_project": True,
        })
        assert bad_save.status_code == 400
        bad_project = client.post(f"/api/threads/{thread_id}/turns", json={
            "agent_id": agent_id, "content": "错误项目", "save_to_project": True,
            "project_id": "prj_0000000000000000",
        })
        assert bad_project.status_code == 404
        no_write = client.post(f"/api/threads/{thread_id}/turns", json={
            "agent_id": agent_id, "content": "需要文件", "save_to_project": True,
            "project_id": project_id,
        })
        assert no_write.status_code == 409
        assert "写入能力" in no_write.json()["detail"]
        no_write_stream = client.post(f"/api/threads/{thread_id}/turns/stream", json={
            "agent_id": agent_id, "content": "需要文件", "save_to_project": True,
            "project_id": project_id,
        })
        assert no_write_stream.status_code == 409
        token = db.use_tenant(user_id)
        try:
            assert get_turn_project(legacy.json()["turn_id"]) is None
            with db.connect() as connection:
                assert connection.execute("SELECT count(*) FROM turn_projects").fetchone()[0] == 1
        finally:
            db.reset_tenant(token)
        with db.connect() as connection:
            with pytest.raises(Exception):
                main._validate_turn_project_choice(connection, {"project_id": None, "save_to_project": True})
            with pytest.raises(Exception):
                main._validate_turn_project_choice(connection, {"project_id": "prj_0000000000000000", "save_to_project": True})
        root = project_root(project_id)
        root.mkdir(parents=True, exist_ok=True)
        outside = tmp_path / "outside.py"
        outside.write_text("secret", encoding="utf-8")
        with pytest.raises(ValueError):
            record_artifact(project_id, thread_id, "turn_fake", outside, "code")
        with pytest.raises(ValueError):
            project_root("../../escape")
        linked = root / "linked.py"
        linked.symlink_to(outside)
        with pytest.raises(ValueError):
            record_artifact(project_id, thread_id, "turn_fake", linked, "code")
        linked.unlink()
        root.rmdir()
        root.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ValueError):
            project_root(project_id)


def test_project_save_respects_agent_tool_policy():
    writer = {"sandbox_mode": "workspace-write", "builtin_tools": ["write_file"]}
    assert main._agent_can_save_project_files(writer)
    assert not main._agent_can_save_project_files({**writer, "sandbox_mode": "read-only"})
    assert not main._agent_can_save_project_files({**writer, "tool_policy": {"tools": {"write_file": "deny"}}})
    assert not main._agent_can_save_project_files({**writer, "builtin_tools": []})


def test_agent_question_answer_resumes_from_checkpoint(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    async def resumed(agent, history, content, **kwargs):
        assert kwargs["approval_decision"] == {
            "tool_call_id": "call_question", "decision": "approved", "reason": "现有项目",
        }
        return {"status": "completed", "content": "已收到选择", "events": [], "usage": {}, "runtime": {}, "sources": []}

    monkeypatch.setattr(main, "run_agent_isolated", resumed)
    with TestClient(main.app) as client:
        _register(client, "question@example.com")
        user_id = client.get("/api/auth/me").json()["user"]["id"]
        agent_id = client.post("/api/resources/agents", json={"name": "Questioner"}).json()["id"]
        thread_id = client.post("/api/threads", json={"agent_id": agent_id}).json()["id"]
        tenant = db.use_tenant(user_id)
        try:
            with db.connect() as connection:
                connection.execute(
                    "INSERT INTO approvals(id,thread_id,turn_id,tool_name,arguments,status,created_at,tool_call_id,resumable) VALUES(?,?,?,?,?,'pending',?,?,1)",
                    ("approval_question", thread_id, "turn_question", "ask_user", '{"question":"选择项目？"}', db.now(), "call_question"),
                )
                connection.execute(
                    "INSERT INTO turn_checkpoints(id,thread_id,turn_id,agent_id,status,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    ("checkpoint_question", thread_id, "turn_question", agent_id, "waiting", "{}", db.now(), db.now()),
                )
        finally:
            db.reset_tenant(tenant)
        assert client.post("/api/approvals/approval_question", json={"decision": "approved", "reason": " "}).status_code == 400
        response = client.post("/api/approvals/approval_question", json={"decision": "approved", "reason": "现有项目"})
        assert response.status_code == 200, response.text
        assert response.json()["content"] == "已收到选择"
        assert client.get(f"/api/threads/{thread_id}").json()["status"] == "idle"
