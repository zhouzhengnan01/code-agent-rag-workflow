from fastapi.testclient import TestClient

from backend.app import db, main, tasks, tenant_migration, workspace
from backend.app.workspace import tenant_workspace


def test_accounts_cannot_see_or_modify_each_others_data(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "shared.db"))
    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "true")
    monkeypatch.delenv("CODEZZN_ADMIN_KEY", raising=False)
    db.init_db()

    with TestClient(main.app) as client:
        first = client.post("/api/auth/register", json={
            "name": "First User", "email": "first@example.com", "password": "password-first-123",
        })
        assert first.status_code == 200
        first_user = first.json()["user"]["id"]
        first_cookie = first.cookies["codezzn_session"]

        agent = client.post("/api/resources/agents", json={"name": "Private agent"})
        assert agent.status_code == 200
        agent_id = agent.json()["id"]
        thread = client.post("/api/threads", json={"name": "Private chat", "agent_id": agent_id})
        assert thread.status_code == 200
        thread_id = thread.json()["id"]
        memory = client.post("/api/memories", json={"scope": "user", "scope_id": "default", "content": "private fact"})
        assert memory.status_code == 200
        memory_id = memory.json()["id"]
        first_root = tenant_workspace(first_user)
        first_root.mkdir(parents=True, exist_ok=True)
        (first_root / "secret.txt").write_text("only first", encoding="utf-8")

        second = client.post("/api/auth/register", json={
            "name": "Second User", "email": "second@example.com", "password": "password-second-123",
        })
        assert second.status_code == 200
        second_cookie = second.cookies["codezzn_session"]
        assert second.json()["user"]["id"] != first_user
        assert tenant_workspace(second.json()["user"]["id"]) != first_root

        assert agent_id not in {item["id"] for item in client.get("/api/resources/agents").json()["data"]}
        assert client.get(f"/api/resources/agents/{agent_id}").status_code == 404
        assert client.put(f"/api/resources/agents/{agent_id}", json={"name": "Hijacked"}).status_code == 404
        assert client.get("/api/threads").json()["data"] == []
        assert client.get(f"/api/threads/{thread_id}").status_code == 404
        assert client.patch(f"/api/threads/{thread_id}", json={"name": "Hijacked"}).status_code == 404
        assert client.get("/api/memories").json()["data"] == []
        assert client.delete(f"/api/memories/{memory_id}").status_code == 404
        assert client.get("/api/artifacts", params={"path": "secret.txt"}).status_code == 404
        assert client.get("/api/artifacts", params={"path": f"../{first_user}/secret.txt"}).status_code == 404

        client.cookies.set("codezzn_session", first_cookie)
        assert client.get(f"/api/resources/agents/{agent_id}").status_code == 200
        assert client.get(f"/api/threads/{thread_id}").status_code == 200
        assert client.get("/api/artifacts", params={"path": "secret.txt"}).text == "only first"

        client.cookies.set("codezzn_session", second_cookie)
        assert client.get(f"/api/resources/agents/{agent_id}").status_code == 404


def test_shared_legacy_records_are_not_copied_to_new_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "shared.db"))
    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "true")
    monkeypatch.delenv("CODEZZN_ADMIN_KEY", raising=False)
    db.init_db()
    legacy = db.resource_save("knowledge", {"name": "Legacy shared knowledge"})

    with TestClient(main.app) as client:
        created = client.post("/api/auth/register", json={
            "name": "New User", "email": "new@example.com", "password": "password-new-123",
        })
        assert created.status_code == 200
        assert client.get(f"/api/resources/knowledge/{legacy['id']}").status_code == 404
        assert all(item["id"] != legacy["id"] for item in client.get("/api/resources/knowledge").json()["data"])

    assert db.resource_get("knowledge", legacy["id"])["name"] == "Legacy shared knowledge"


def test_legacy_data_is_assigned_only_to_selected_github_account(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "shared.db"))
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", tmp_path / "workspace")
    monkeypatch.setattr(tenant_migration, "BASE_WORKSPACE", tmp_path / "workspace")
    workspace.BASE_WORKSPACE.mkdir()
    (workspace.BASE_WORKSPACE / "legacy.txt").write_text("private legacy file", encoding="utf-8")
    db.init_db()
    owner_id, other_id = db.new_id("usr"), db.new_id("usr")
    with db.connect(global_db=True) as connection:
        for user_id, github_id in ((owner_id, "274968378"), (other_id, "123456")):
            connection.execute(
                "INSERT INTO users(id,email,name,github_id,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (user_id, f"{github_id}@example.com", github_id, github_id, db.now(), db.now()),
            )
    legacy = db.resource_save("knowledge", {"name": "Owner knowledge"})
    monkeypatch.setenv("CODEZZN_LEGACY_OWNER_GITHUB_ID", "274968378")

    assert tenant_migration.migrate_legacy_owner("274968378") == owner_id
    assert None not in tasks._active_tenants()
    assert tenant_migration.migrate_legacy_owner("274968378") == owner_id
    assert (tenant_workspace(owner_id) / "legacy.txt").read_text(encoding="utf-8") == "private legacy file"
    assert (workspace.BASE_WORKSPACE / "legacy.txt").exists()
    with db.connect(global_db=True) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 2
    owner = db.use_tenant(owner_id)
    try:
        assert db.resource_get("knowledge", legacy["id"])["name"] == "Owner knowledge"
        with db.connect() as connection:
            assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 0
    finally:
        db.reset_tenant(owner)
    db.ensure_tenant(other_id)
    other = db.use_tenant(other_id)
    try:
        assert db.resource_get("knowledge", legacy["id"]) is None
        assert not (tenant_workspace() / "legacy.txt").exists()
    finally:
        db.reset_tenant(other)
