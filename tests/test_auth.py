import asyncio
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
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
        client.cookies.set(auth.SESSION_COOKIE, created.cookies[auth.SESSION_COOKIE])
        assert client.get("/api/auth/me").json()["authenticated"] is False


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
        assert parse_qs(urlparse(location).query)["prompt"] == ["select_account"]
        assert auth.OAUTH_STATE_COOKIE in response.cookies
        assert "httponly" in response.headers["set-cookie"].lower()
        assert response.headers["cache-control"] == "no-store"
        with db.connect() as connection:
            row = connection.execute("SELECT next_path FROM oauth_states").fetchone()
        assert row["next_path"] == "/workbench.html"


def test_github_login_email_collision_returns_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "auth.db"))
    db.init_db()
    timestamp = db.now()
    with db.connect(global_db=True) as connection:
        connection.execute(
            "INSERT INTO users(id,email,name,github_id,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (db.new_id("usr"), "shared@example.com", "Existing", "111", timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO oauth_states(state_hash,provider,next_path,created_at,expires_at) VALUES(?,?,?,?,?)",
            (auth._digest("state-a"), "github", "/workbench.html", timestamp, timestamp + 600),
        )

    class Response:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data

    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return Response({"access_token": "test-token"})
        async def get(self, *args, **kwargs): return Response({"id": 222, "email": "shared@example.com", "login": "Other"})

    monkeypatch.setattr(auth.httpx, "AsyncClient", Client)
    try:
        asyncio.run(auth.github_callback("unused-code", "state-a"))
        assert False, "A different linked GitHub account must not take over this user"
    except HTTPException as exc:
        assert exc.status_code == 409


def test_github_callback_requires_same_browser_state(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        monkeypatch.setenv("CODEZZN_GITHUB_CLIENT_ID", "client-id")
        monkeypatch.setenv("CODEZZN_GITHUB_CLIENT_SECRET", "client-secret")
        location = client.get("/api/auth/github/start", follow_redirects=False).headers["location"]
        state = parse_qs(urlparse(location).query)["state"][0]
        client.cookies.delete(auth.OAUTH_STATE_COOKIE)
        result = client.get("/api/auth/github/callback", params={"code": "unused", "state": state}, follow_redirects=False)
        assert result.status_code == 303
        assert result.headers["location"] == "/login?error=github_invalid"
        with db.connect(global_db=True) as connection:
            assert connection.execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == 0


def test_github_timeout_returns_login_error_instead_of_500(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        monkeypatch.setenv("CODEZZN_GITHUB_CLIENT_ID", "client-id")
        monkeypatch.setenv("CODEZZN_GITHUB_CLIENT_SECRET", "client-secret")
        location = client.get("/api/auth/github/start", follow_redirects=False).headers["location"]
        state = parse_qs(urlparse(location).query)["state"][0]

        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, *args, **kwargs): raise auth.httpx.ConnectTimeout("timed out")

        monkeypatch.setattr(auth.httpx, "AsyncClient", Client)
        response = client.get(
            "/api/auth/github/callback", params={"code": "unused-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/login?error=github_504"


def test_invalid_github_proxy_returns_login_error(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        monkeypatch.setenv("CODEZZN_GITHUB_CLIENT_ID", "client-id")
        monkeypatch.setenv("CODEZZN_GITHUB_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("CODEZZN_GITHUB_PROXY_URL", "localhost:7897")
        location = client.get("/api/auth/github/start", follow_redirects=False).headers["location"]
        state = parse_qs(urlparse(location).query)["state"][0]
        response = client.get(
            "/api/auth/github/callback", params={"code": "unused-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/login?error=github_502"


def test_github_callback_switches_from_existing_account(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        monkeypatch.setenv("CODEZZN_GITHUB_CLIENT_ID", "client-id")
        monkeypatch.setenv("CODEZZN_GITHUB_CLIENT_SECRET", "client-secret")
        first = client.post("/api/auth/register", json={
            "name": "First User", "email": "first@example.com", "password": "password-first-123",
        })
        assert first.status_code == 200
        location = client.get("/api/auth/github/start", follow_redirects=False).headers["location"]
        state = parse_qs(urlparse(location).query)["state"][0]

        class Response:
            def __init__(self, data): self.data = data
            def raise_for_status(self): pass
            def json(self): return self.data

        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, *args, **kwargs): return Response({"access_token": "test-token"})
            async def get(self, *args, **kwargs):
                return Response({"id": 222, "email": "second@example.com", "login": "Second"})

        monkeypatch.setattr(auth.httpx, "AsyncClient", Client)
        response = client.get(
            "/api/auth/github/callback", params={"code": "unused-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/workbench.html"
        assert client.get("/api/auth/me").json()["user"]["email"] == "second@example.com"
        with db.connect(global_db=True) as connection:
            assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 2
            assert connection.execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == 1


def test_session_last_seen_is_throttled(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post("/api/auth/register", json={
            "name": "Test User", "email": "test@example.com", "password": "password-test-123",
        })
        assert created.status_code == 200
        with db.connect(global_db=True) as connection:
            initial = connection.execute("SELECT last_seen_at FROM auth_sessions").fetchone()[0]

        monkeypatch.setattr(auth, "now", lambda: initial + 30)
        assert client.get("/api/auth/me").status_code == 200
        with db.connect(global_db=True) as connection:
            assert connection.execute("SELECT last_seen_at FROM auth_sessions").fetchone()[0] == initial

        monkeypatch.setattr(auth, "now", lambda: initial + 61)
        assert client.get("/api/auth/me").status_code == 200
        with db.connect(global_db=True) as connection:
            assert connection.execute("SELECT last_seen_at FROM auth_sessions").fetchone()[0] == initial + 61
