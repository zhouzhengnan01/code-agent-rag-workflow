from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.app import auth, cli_auth, db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("CODEZZN_PUBLIC_URL", "http://testserver")
    db.init_db()
    cli_auth.init_cli_auth_tables()
    app = FastAPI()
    app.include_router(cli_auth.router)
    with TestClient(app) as result:
        yield result


def _user(client, email="owner@example.com"):
    user = auth.register_user("CLI Tester", email, "test-password-123")
    cookie, _ = auth.create_session(user["id"])
    client.cookies.set(auth.SESSION_COOKIE, cookie)
    return user, cookie


def _device(client):
    response = client.post("/api/auth/cli/device", json={"name": "My Windows CLI"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["expires_in"] == 600
    assert result["interval"] == 3
    assert "device_code" not in result["verification_uri_complete"]
    return result


def _consent(client, device, decision="approved"):
    info = client.get("/api/auth/cli/device-info", params={"user_code": device["user_code"]})
    assert info.status_code == 200
    assert "device_code" not in info.json()
    assert "access_token" not in info.json()
    return client.post("/api/auth/cli/approve", json={"user_code": device["user_code"], "decision": decision},
                       headers={"Origin": "http://testserver", "X-CLI-CSRF": info.json()["csrf_token"]})


def _redeem(client, device):
    response = client.post("/api/auth/cli/token", json={"device_code": device["device_code"]})
    assert response.status_code == 200
    return response.json()


def _request(headers=None, cookie=None):
    items = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    if cookie:
        items.append((b"cookie", f"{auth.SESSION_COOKIE}={cookie}".encode()))
    return Request({"type": "http", "headers": items, "method": "GET", "path": "/", "scheme": "http",
                    "server": ("testserver", 80), "query_string": b""})


def test_cli_browser_consent_requires_cookie_not_admin_or_bearer(client, monkeypatch):
    monkeypatch.setenv("CODEZZN_ADMIN_KEY", "admin-test")
    device = _device(client)
    for headers in ({}, {"X-Admin-Key": "admin-test"}, {"Authorization": "Bearer admin-test"}):
        info = client.get("/api/auth/cli/device-info", params={"user_code": device["user_code"]}, headers=headers)
        assert info.status_code == 401
        response = client.post("/api/auth/cli/approve", json={"user_code": device["user_code"], "decision": "approved"}, headers=headers)
        assert response.status_code == 401
    owner, _ = _user(client)
    assert _consent(client, device).status_code == 200
    token = _redeem(client, device)
    assert token["user"]["id"] == owner["id"]
    client.cookies.clear()
    other = _device(client)
    assert client.get("/api/auth/cli/device-info", params={"user_code": other["user_code"]},
                      headers={"Authorization": "Bearer " + token["access_token"]}).status_code == 401


def test_cli_pending_interval_denial_and_expiry(client, monkeypatch):
    clock = [1000000]
    monkeypatch.setattr(cli_auth, "now", lambda: clock[0])
    device = _device(client)
    first = client.post("/api/auth/cli/token", json={"device_code": device["device_code"]})
    assert first.status_code == 202
    assert first.json()["error"] == "authorization_pending"
    fast = client.post("/api/auth/cli/token", json={"device_code": device["device_code"]})
    assert fast.status_code == 429
    assert fast.headers["retry-after"] == "3"
    _user(client)
    assert _consent(client, device, "denied").status_code == 200
    denied = client.post("/api/auth/cli/token", json={"device_code": device["device_code"]})
    assert denied.status_code == 403
    assert denied.json()["error"] == "access_denied"
    clock[0] += 600
    assert client.post("/api/auth/cli/token", json={"device_code": device["device_code"]}).status_code == 410
    assert client.get("/api/auth/cli/device-info", params={"user_code": device["user_code"]}).status_code == 410


def test_cli_csrf_origin_and_browser_session_binding(client):
    device = _device(client)
    _user(client)
    info = client.get("/api/auth/cli/device-info", params={"user_code": device["user_code"]}).json()
    payload = {"user_code": device["user_code"], "decision": "approved"}
    for headers in ({}, {"Origin": "http://testserver"},
                    {"Origin": "http://testserver", "X-CLI-CSRF": "invalid"},
                    {"Origin": "https://evil.example", "X-CLI-CSRF": info["csrf_token"]},
                    {"Origin": "null", "X-CLI-CSRF": info["csrf_token"]},
                    {"Origin": "http://testserver", "X-CLI-CSRF": info["csrf_token"], "Sec-Fetch-Site": "cross-site"}):
        assert client.post("/api/auth/cli/approve", json=payload, headers=headers).status_code == 403
    _user(client, "second@example.com")
    assert client.post("/api/auth/cli/approve", json=payload,
                       headers={"Origin": "http://testserver", "X-CLI-CSRF": info["csrf_token"]}).status_code == 403
    assert _consent(client, device).status_code == 200


def test_cli_token_hash_only_replay_expiry_and_revocation(client, monkeypatch):
    user, cookie = _user(client)
    device = _device(client)
    assert _consent(client, device).status_code == 200
    token = _redeem(client, device)
    bearer = {"Authorization": "Bearer " + token["access_token"]}
    assert token["expires_at"] - cli_auth.now() >= 30 * 86400 - 2
    assert client.get("/api/auth/cli/status", headers=bearer).json()["user"]["id"] == user["id"]
    with db.connect(global_db=True) as connection:
        stored = dict(connection.execute("SELECT * FROM cli_tokens").fetchone())
        saved_device = dict(connection.execute("SELECT * FROM cli_devices").fetchone())
    assert token["access_token"] not in str(stored)
    assert device["device_code"] not in str(saved_device)
    assert device["user_code"] not in str(saved_device)
    assert client.post("/api/auth/cli/token", json={"device_code": device["device_code"]}).status_code == 409
    assert _consent_if_processed(client, device) == 409
    assert auth.request_user(_request(bearer))["id"] == user["id"]
    with monkeypatch.context() as clock_patch:
        clock_patch.setattr(cli_auth, "now", lambda: token["expires_at"])
        assert client.get("/api/auth/cli/status", headers=bearer).status_code == 401


def _consent_if_processed(client, device):
    return client.get("/api/auth/cli/device-info", params={"user_code": device["user_code"]}).status_code


def test_cli_logout_revokes_only_cli_token_and_invalid_bearer_never_falls_back(client):
    user, cookie = _user(client)
    device = _device(client)
    assert _consent(client, device).status_code == 200
    token = _redeem(client, device)
    bearer = {"Authorization": "Bearer " + token["access_token"]}
    assert client.post("/api/auth/cli/logout", headers=bearer).status_code == 200
    assert client.get("/api/auth/cli/status", headers=bearer).status_code == 401
    assert auth.request_user(_request(cookie=cookie))["id"] == user["id"]
    assert cli_auth.resolve_cli_user(_request()) is None
    for headers in (bearer, {"Authorization": "Bearer invalid"}, {"Authorization": "Basic something"}, {"Authorization": ""}):
        with pytest.raises(HTTPException) as error:
            auth.request_user(_request(headers, cookie))
        assert error.value.status_code == 401


def test_cli_tenant_isolation_and_cross_user_approval_cannot_replace_owner(client):
    first, first_cookie = _user(client)
    device = _device(client)
    assert _consent(client, device).status_code == 200
    second, second_cookie = _user(client, "second@example.com")
    assert _consent_if_processed(client, device) == 409
    # Knowing the browser-visible code cannot turn an approved device into another account.
    response = client.post("/api/auth/cli/approve", json={"user_code": device["user_code"], "decision": "approved"},
                           headers={"Origin": "http://testserver", "X-CLI-CSRF": cli_auth._csrf_token(second_cookie, cli_auth._user_code(device["user_code"]))})
    assert response.status_code == 409
    token = _redeem(client, device)
    identity = cli_auth.resolve_cli_user(_request({"Authorization": "Bearer " + token["access_token"]}))
    assert identity["id"] == first["id"]
    for user, value in ((first, "first private"), (second, "second private")):
        db.ensure_tenant(user["id"])
        tenant = db.use_tenant(user["id"])
        try:
            with db.connect() as connection:
                connection.execute("INSERT INTO threads(id,name,created_at,updated_at) VALUES(?,?,?,?)",
                                   ("private-thread", value, db.now(), db.now()))
        finally:
            db.reset_tenant(tenant)
    tenant = db.use_tenant(identity["id"])
    try:
        with db.connect() as connection:
            assert connection.execute("SELECT name FROM threads WHERE id='private-thread'").fetchone()["name"] == "first private"
        assert cli_auth.resolve_cli_user(_request({"Authorization": "Bearer " + token["access_token"]}))["id"] == first["id"]
    finally:
        db.reset_tenant(tenant)


def test_cli_concurrent_redemption_is_one_shot(client):
    _user(client)
    device = _device(client)
    assert _consent(client, device).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: client.post("/api/auth/cli/token", json={"device_code": device["device_code"]}), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    with db.connect(global_db=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM cli_tokens").fetchone()[0] == 1


def test_cli_start_limit_cleanup_canonical_server_and_page(client, monkeypatch):
    for _ in range(10):
        _device(client)
    assert client.post("/api/auth/cli/device", json={}).status_code == 429
    assert client.get("/cli/authorize").status_code == 200
    assert client.get("/cli/authorize").headers["x-frame-options"] == "DENY"
    monkeypatch.setenv("CODEZZN_PUBLIC_URL", "http://192.168.1.10:8080")
    mismatch = client.post("/api/auth/cli/device", json={})
    assert mismatch.status_code == 409
    assert mismatch.json()["canonical_server"] == "http://192.168.1.10:8080"
    monkeypatch.setenv("CODEZZN_PUBLIC_URL", "http://testserver")
    with db.connect(global_db=True) as connection:
        connection.execute("UPDATE cli_devices SET expires_at=?", (cli_auth.now() - 86401,))
        connection.execute("UPDATE cli_rate_limits SET window_start=?", (cli_auth.now() - 601,))
    _device(client)
    with db.connect(global_db=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM cli_devices").fetchone()[0] == 1


def test_cli_real_app_middleware_uses_token_tenant_and_rejects_fallback(client, tmp_path, monkeypatch):
    from backend.app import main, workspace

    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CODEZZN_ADMIN_KEY", "test-admin-key")
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", tmp_path / "workspace")
    first, first_cookie = _user(client)
    device = _device(client)
    assert _consent(client, device).status_code == 200
    token = _redeem(client, device)
    second, second_cookie = _user(client, "other@example.com")
    # No context manager: avoid unrelated application background workers in this integration check.
    api = TestClient(main.app)
    try:
        api.cookies.set(auth.SESSION_COOKIE, first_cookie)
        created = api.post("/api/threads", json={"name": "owner conversation"})
        assert created.status_code == 200
        thread_id = created.json()["id"]
        api.cookies.set(auth.SESSION_COOKIE, second_cookie)
        assert api.get("/api/threads/" + thread_id).status_code == 404
        bearer = {"Authorization": "Bearer " + token["access_token"]}
        assert api.get("/api/threads/" + thread_id, headers=bearer).status_code == 200
        assert api.get("/api/auth/me", headers=bearer).json()["user"]["id"] == first["id"]
        invalid = {"Authorization": "Bearer invalid", "X-Codezzn-Key": "test-admin-key"}
        assert api.get("/api/threads", headers=invalid).status_code == 401
        assert api.post("/api/auth/cli/logout", headers=bearer).status_code == 200
        assert api.get("/api/threads", headers=bearer).status_code == 401
        assert api.get("/api/threads").status_code == 200
    finally:
        api.close()
