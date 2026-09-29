import asyncio
import sqlite3
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from backend.app import auth, db, main


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "true")
    monkeypatch.delenv("CODEZZN_ADMIN_KEY", raising=False)
    monkeypatch.delenv("CODEZZN_LEGACY_OWNER_GITHUB_ID", raising=False)
    monkeypatch.delenv("CODEZZN_GITHUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("CODEZZN_GITHUB_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CODEZZN_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("CODEZZN_GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CODEZZN_GOOGLE_REDIRECT_URI", raising=False)
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


@pytest.mark.parametrize("identity_column,identity_value", [("github_id", "111"), ("google_id", "google-111")])
def test_github_login_email_collision_returns_clear_error(tmp_path, monkeypatch, identity_column, identity_value):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "auth.db"))
    db.init_db()
    timestamp = db.now()
    with db.connect(global_db=True) as connection:
        connection.execute(
            f"INSERT INTO users(id,email,name,{identity_column},created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (db.new_id("usr"), "shared@example.com", "Existing", identity_value, timestamp, timestamp),
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


def _google_test_client(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("CODEZZN_GOOGLE_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("CODEZZN_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("CODEZZN_PUBLIC_URL", "http://127.0.0.1:8080")
    return client


def test_google_start_uses_oidc_pkce_nonce_and_browser_state(tmp_path, monkeypatch):
    with _google_test_client(tmp_path, monkeypatch) as client:
        assert client.get("/api/auth/me").json()["google_configured"] is True
        response = client.get("/api/auth/google/start?next=//evil.example/path", follow_redirects=False)
        assert response.status_code == 303
        params = parse_qs(urlparse(response.headers["location"]).query)
        assert params["scope"] == ["openid email profile"]
        assert params["code_challenge_method"] == ["S256"]
        assert params["nonce"] and params["code_challenge"]
        assert params["redirect_uri"] == ["http://127.0.0.1:8080/api/auth/google/callback"]
        assert params["prompt"] == ["select_account"]
        assert auth.OAUTH_STATE_COOKIE in response.cookies
        with db.connect(global_db=True) as connection:
            saved = connection.execute("SELECT * FROM oauth_states WHERE provider='google'").fetchone()
        assert saved["next_path"] == "/workbench.html"
        assert saved["nonce_hash"] == auth._digest(params["nonce"][0])
        assert saved["code_verifier"]
        client.cookies.delete(auth.OAUTH_STATE_COOKIE)
        rejected = client.get("/api/auth/google/callback", params={"code": "test", "state": params["state"][0]}, follow_redirects=False)
        assert rejected.headers["location"] == "/login?error=google_invalid"


def test_google_callback_creates_isolated_user_and_rejects_replay(tmp_path, monkeypatch):
    with _google_test_client(tmp_path, monkeypatch) as client:
        params = parse_qs(urlparse(client.get("/api/auth/google/start", follow_redirects=False).headers["location"]).query)
        nonce, state = params["nonce"][0], params["state"][0]

        class Response:
            def raise_for_status(self): pass
            def json(self): return {"id_token": "signed-google-token"}

        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, *args, **kwargs):
                assert kwargs["data"]["code_verifier"]
                return Response()

        monkeypatch.setattr(auth.httpx, "AsyncClient", Client)
        monkeypatch.setattr(auth, "_verify_google_id_token", lambda token, audience: {
            "sub": "google-sub-123", "email": "google@example.com", "email_verified": True,
            "name": "Google User", "nonce": nonce,
        })
        response = client.get("/api/auth/google/callback", params={"code": "test", "state": state}, follow_redirects=False)
        assert response.headers["location"] == "/workbench.html"
        me = client.get("/api/auth/me").json()
        assert me["user"]["provider"] == "google"
        with db.connect(global_db=True) as connection:
            assert connection.execute("SELECT google_id FROM users WHERE email='google@example.com'").fetchone()[0] == "google-sub-123"
        replay = client.get("/api/auth/google/callback", params={"code": "test", "state": state}, follow_redirects=False)
        assert replay.headers["location"] == "/login?error=google_invalid"


def test_google_does_not_merge_existing_email_or_accept_wrong_nonce(tmp_path, monkeypatch):
    with _google_test_client(tmp_path, monkeypatch) as client:
        existing = client.post("/api/auth/register", json={"name": "Existing", "email": "same@example.com", "password": "long-password-123"})
        old_id = existing.json()["user"]["id"]
        client.post("/api/auth/logout")

        class Response:
            def raise_for_status(self): pass
            def json(self): return {"id_token": "signed-google-token"}

        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, *args, **kwargs): return Response()

        monkeypatch.setattr(auth.httpx, "AsyncClient", Client)
        nonce = "wrong-nonce"
        monkeypatch.setattr(auth, "_verify_google_id_token", lambda *args: {
            "sub": "google-sub-456", "email": "same@example.com", "email_verified": True, "nonce": nonce,
        })
        params = parse_qs(urlparse(client.get("/api/auth/google/start", follow_redirects=False).headers["location"]).query)
        denied = client.get("/api/auth/google/callback", params={"code": "test", "state": params["state"][0]}, follow_redirects=False)
        assert denied.headers["location"] == "/login?error=google_400"

        nonce = parse_qs(urlparse(client.get("/api/auth/google/start", follow_redirects=False).headers["location"]).query)["nonce"][0]
        with db.connect(global_db=True) as connection:
            state_row = connection.execute("SELECT state_hash FROM oauth_states WHERE nonce_hash=?", (auth._digest(nonce),)).fetchone()
        state = client.cookies.get(auth.OAUTH_STATE_COOKIE)
        assert state_row[0] == auth._digest(state)
        denied = client.get("/api/auth/google/callback", params={"code": "test", "state": state}, follow_redirects=False)
        assert denied.headers["location"] == "/login?error=google_409"
        with db.connect(global_db=True) as connection:
            row = connection.execute("SELECT id,google_id FROM users WHERE email='same@example.com'").fetchone()
            assert row["id"] == old_id and row["google_id"] is None


def test_google_requires_https_for_nonlocal_redirect(tmp_path, monkeypatch):
    with _google_test_client(tmp_path, monkeypatch) as client:
        monkeypatch.setenv("CODEZZN_PUBLIC_URL", "http://192.168.32.95:8080")
        response = client.get("/api/auth/google/start", follow_redirects=False)
        assert response.status_code == 503


def test_existing_auth_database_gains_google_columns(tmp_path, monkeypatch):
    path = tmp_path / "legacy-auth.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE users(id TEXT PRIMARY KEY,email TEXT NOT NULL UNIQUE,name TEXT NOT NULL,password_hash TEXT,avatar_url TEXT NOT NULL DEFAULT '',github_id TEXT UNIQUE,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL)")
        connection.execute("CREATE TABLE oauth_states(state_hash TEXT PRIMARY KEY,provider TEXT NOT NULL,next_path TEXT NOT NULL,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL)")
    monkeypatch.setattr(db, "DB_PATH", str(path))
    db.init_db()
    with db.connect(global_db=True) as connection:
        assert "google_id" in {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
        assert {"nonce_hash", "code_verifier"} <= {row["name"] for row in connection.execute("PRAGMA table_info(oauth_states)")}
        assert "idx_users_google_id" in {row["name"] for row in connection.execute("PRAGMA index_list(users)")}
