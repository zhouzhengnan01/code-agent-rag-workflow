from fastapi.testclient import TestClient
import pytest
import sqlite3
import zipfile
from io import BytesIO

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
        archive = client.get(f"/api/projects/{project_id}/artifacts/archive")
        assert archive.status_code == 200
        assert archive.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(BytesIO(archive.content)) as bundle:
            assert bundle.namelist() == ["quicksort.py"]
            assert bundle.read("quicksort.py") == b"print('sort')\n"

        second_cookie = _register(client, "project-second@example.com")
        assert second_cookie != first_cookie
        assert client.get("/api/projects").json()["data"] == []
        assert client.get(f"/api/projects/{project_id}").status_code == 404
        assert client.get(f"/api/projects/{project_id}/artifacts").status_code == 404
        assert client.get(f"/api/projects/{project_id}/artifacts/archive").status_code == 404
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


def test_project_folder_archive_only_contains_registered_subtree(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        _register(client, "folder-archive@example.com")
        user_id = client.get("/api/auth/me").json()["user"]["id"]
        project_id = client.post("/api/projects", json={"name": "Sorting Project"}).json()["id"]
        thread_id = client.post("/api/threads", json={}).json()["id"]
        token = db.use_tenant(user_id)
        try:
            root = project_root(project_id)
            for relative in ("algorithms/quick.py", "algorithms/nested/bubble.py", "README.md"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(relative, encoding="utf-8")
                record_artifact(project_id, thread_id, "turn_folder", target, "code")
        finally:
            db.reset_tenant(token)
        archive = client.get(f"/api/projects/{project_id}/artifacts/archive", params={"prefix": "algorithms"})
        assert archive.status_code == 200
        with zipfile.ZipFile(BytesIO(archive.content)) as bundle:
            assert sorted(bundle.namelist()) == ["algorithms/nested/bubble.py", "algorithms/quick.py"]
        assert client.get(f"/api/projects/{project_id}/artifacts/archive", params={"prefix": "missing"}).status_code == 404
        for invalid in ("../algorithms", "/algorithms", "algorithms/", "algorithms//nested", "algorithms\\nested"):
            assert client.get(f"/api/projects/{project_id}/artifacts/archive", params={"prefix": invalid}).status_code == 400


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


def test_project_switch_from_chat_does_not_grant_file_write(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        first_cookie = _register(client, "switch-first@example.com")
        first = client.post("/api/projects", json={"name": "0929-dev-01"}).json()
        target = client.post("/api/projects", json={"name": "0929-dev"}).json()
        thread_id = client.post("/api/threads", json={}).json()["id"]
        assert client.patch(f"/api/threads/{thread_id}", json={"active_project_id": first["id"]}).status_code == 200

        switched = client.post(f"/api/threads/{thread_id}/project-switch", json={
            "content": "切换到0929-dev项目", "project_name": "0929-dev",
        })
        assert switched.status_code == 200, switched.text
        assert switched.json()["project"]["id"] == target["id"]
        thread = client.get(f"/api/threads/{thread_id}").json()
        assert thread["active_project_id"] == target["id"]
        assert [message["role"] for message in thread["messages"]] == ["user", "assistant"]
        assert "不授权写入文件" in thread["messages"][-1]["content"]
        with db.connect() as connection:
            assert connection.execute("SELECT count(*) FROM turn_projects").fetchone()[0] == 0

        assert client.post(f"/api/threads/{thread_id}/project-switch", json={
            "content": "切换到不存在的项目", "project_name": "不存在",
        }).status_code == 404
        compound = client.post(f"/api/threads/{thread_id}/project-switch", json={
            "content": "切换到0929-dev-01项目，并写一份冒泡排序的python文件", "project_name": "0929-dev-01",
        })
        assert compound.status_code == 400
        assert len(client.get(f"/api/threads/{thread_id}").json()["messages"]) == 2
        _register(client, "switch-second@example.com")
        assert client.post(f"/api/threads/{thread_id}/project-switch", json={
            "content": "切换到0929-dev项目", "project_name": "0929-dev",
        }).status_code == 404
        client.cookies.set("codezzn_session", first_cookie)
        assert client.get(f"/api/threads/{thread_id}").status_code == 200


def test_compound_project_switch_and_file_creation_reaches_correct_project(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    instruction = "帮我切换到0929-dev-01项目，并写一份冒泡排序的python文件"

    async def fake_agent(agent, history, content, **kwargs):
        assert content == instruction
        assert get_turn_project(kwargs["turn_id"]) == {"project_id": target_id, "save_to_project": True}
        root = project_root(target_id)
        root.mkdir(parents=True, exist_ok=True)
        file = root / "bubble_sort.py"
        file.write_text("def bubble_sort(items):\n    return sorted(items)\n", encoding="utf-8")
        record_artifact(target_id, kwargs["thread_id"], kwargs["turn_id"], file, "code")
        return {"status": "completed", "content": "已创建 bubble_sort.py", "events": [], "usage": {}, "runtime": {}, "sources": []}

    monkeypatch.setattr(main, "run_agent_isolated", fake_agent)
    with TestClient(main.app) as client:
        _register(client, "compound@example.com")
        agent_id = client.post("/api/resources/agents", json={
            "name": "Coding", "role_template": "coding", "sandbox_mode": "workspace-write", "builtin_tools": ["write_file"],
        }).json()["id"]
        other_id = client.post("/api/projects", json={"name": "0929-dev"}).json()["id"]
        target_id = client.post("/api/projects", json={"name": "0929-dev-01"}).json()["id"]
        thread_id = client.post("/api/threads", json={"agent_id": agent_id}).json()["id"]
        client.patch(f"/api/threads/{thread_id}", json={"active_project_id": other_id})
        intent_response = client.post("/api/agent/intent", json={
            "content": instruction, "agent_id": agent_id, "thread_id": thread_id,
        })
        assert intent_response.status_code == 200, intent_response.text
        intent = intent_response.json()
        assert intent["requires_project"] is True and intent["kind"] == "file"
        assert intent["target_project_id"] == target_id and not intent["project_switch_only"]
        streamed = client.post(f"/api/threads/{thread_id}/turns/stream", json={
            "agent_id": agent_id, "content": instruction, "project_id": target_id,
            "save_to_project": True, "intent_kind": "file",
        })
        assert streamed.status_code == 200 and '"status": "completed"' in streamed.text
        thread = client.get(f"/api/threads/{thread_id}").json()
        assert thread["active_project_id"] == target_id
        assert thread["messages"][-1]["project_artifacts"][0]["path"] == "bubble_sort.py"
        assert client.get(f"/api/projects/{other_id}/artifacts").json()["data"] == []


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


def test_legacy_approval_can_be_retired_and_retried_without_running_tool(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        _register(client, "legacy-approval@example.com")
        user_id = client.get("/api/auth/me").json()["user"]["id"]
        agent_id = client.post("/api/resources/agents", json={"name": "Writer"}).json()["id"]
        thread_id = client.post("/api/threads", json={"agent_id": agent_id}).json()["id"]
        token = db.use_tenant(user_id)
        try:
            with db.connect() as connection:
                connection.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,created_at) VALUES(?,?,?,?,?,?)", ("msg_legacy", thread_id, "turn_legacy", "user", "帮我写一份冒泡排序代码", db.now()))
                connection.execute("INSERT INTO approvals(id,thread_id,turn_id,tool_name,arguments,status,created_at,resumable) VALUES(?,?,?,?,?,'pending',?,0)", ("approval_legacy", thread_id, "turn_legacy", "write_file", '{"path":"bubble_sort.py"}', db.now()))
        finally:
            db.reset_tenant(token)
        inbox = client.get(f"/api/threads/{thread_id}/approvals/inbox").json()["data"]
        assert len(inbox) == 1 and inbox[0]["resumable"] is False
        assert client.post("/api/approvals/approval_legacy", json={"decision": "approved"}).status_code == 409
        retry = client.post("/api/approvals/approval_legacy/dismiss")
        assert retry.status_code == 200
        assert retry.json()["content"] == "帮我写一份冒泡排序代码"
        assert client.get(f"/api/threads/{thread_id}/approvals/inbox").json()["data"] == []
        assert client.post("/api/approvals/approval_legacy/dismiss").status_code == 409
