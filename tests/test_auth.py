from fastapi.testclient import TestClient

from backend.app import auth, db, main


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "true")
    monkeypatch.delenv("CODEZZN_ADMIN_KEY", raising=False)
    monkeypatch.delenv("CODEZZN_GITHUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("CODEZZN_GITHUB_CLIENT_SECRET", raising=False)
    db.init_db()
    return TestClient(main.app)


def test_registration_session_and_logout(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        blocked = client.get("/workbench.html", follow_redirects=False)
        assert blocked.status_code == 303
        assert blocked.headers["location"].startswith("/login")
        assert client.get("/login").status_code == 200

        created = client.post("/api/auth/register", json={
            "name": "Codezzn Tester", "email": "tester@example.com", "password": "correct-horse-42",
        })
        assert created.status_code == 200
        assert created.json()["user"]["email"] == "tester@example.com"
        assert auth.SESSION_COOKIE in created.cookies

        me = client.get("/api/auth/me").json()
        assert me["authenticated"] is True
        assert me["user"]["name"] == "Codezzn Tester"
        assert client.get("/workbench.html").status_code == 200

        logged_out = client.post("/api/auth/logout")
        assert logged_out.status_code == 200
        assert client.get("/workbench.html", follow_redirects=False).status_code == 303


def test_login_validation_and_duplicate_email(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        payload = {"name": "Test User", "email": "User@Example.com", "password": "a-long-password"}
        assert client.post("/api/auth/register", json=payload).status_code == 200
        client.post("/api/auth/logout")
        assert client.post("/api/auth/register", json=payload).status_code == 409
        assert client.post("/api/auth/login", json={"email": "user@example.com", "password": "wrong-password"}).status_code == 401
        assert client.post("/api/auth/login", json={"email": "user@example.com", "password": "a-long-password"}).status_code == 200


def test_github_button_has_clear_unconfigured_error(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/api/auth/github/start", follow_redirects=False)
        assert response.status_code == 503
        assert "GitHub 登录尚未配置" in response.json()["detail"]


def test_github_oauth_start_uses_state_and_safe_callback(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        monkeypatch.setenv("CODEZZN_GITHUB_CLIENT_ID", "client-id")
        monkeypatch.setenv("CODEZZN_GITHUB_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("CODEZZN_PUBLIC_URL", "http://127.0.0.1:8080")
        response = client.get("/api/auth/github/start?next=//evil.example/path", follow_redirects=False)
        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith("https://github.com/login/oauth/authorize?")
        assert "client_id=client-id" in location
        assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8080%2Fapi%2Fauth%2Fgithub%2Fcallback" in location
        with db.connect() as connection:
            row = connection.execute("SELECT next_path FROM oauth_states").fetchone()
        assert row["next_path"] == "/workbench.html"
