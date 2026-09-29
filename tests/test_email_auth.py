from fastapi.testclient import TestClient

from backend.app import db, email_auth, main


def _client(tmp_path, monkeypatch, *, configured=True):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "email-auth.db"))
    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "true")
    monkeypatch.delenv("CODEZZN_ADMIN_KEY", raising=False)
    monkeypatch.delenv("CODEZZN_LEGACY_OWNER_GITHUB_ID", raising=False)
    for key in ("CODEZZN_SMTP_HOST", "CODEZZN_SMTP_USER", "CODEZZN_SMTP_PASSWORD", "CODEZZN_SMTP_FROM"):
        monkeypatch.delenv(key, raising=False)
    if configured:
        monkeypatch.setenv("CODEZZN_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("CODEZZN_SMTP_USER", "sender@example.com")
        monkeypatch.setenv("CODEZZN_SMTP_PASSWORD", "test-app-password")
        monkeypatch.setenv("CODEZZN_SMTP_FROM", "sender@example.com")
    db.init_db()
    return TestClient(main.app)


def test_email_code_requires_smtp_configuration(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, configured=False) as client:
        assert client.get("/api/auth/me").json()["email_code_configured"] is False
        response = client.post("/api/auth/email/code", json={"email": "user@qq.com"})
        assert response.status_code == 503
        assert client.post("/api/auth/register", json={
            "name": "Old flow", "email": "user@qq.com", "password": "password-long-123",
        }).status_code == 200


def test_email_code_creates_user_and_is_single_use(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(email_auth, "_send_code", lambda address, code, settings: sent.append((address, code)))
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/api/auth/me").json()["email_code_configured"] is True
        response = client.post("/api/auth/email/code", json={"email": "Test.User+code@qq.com"})
        assert response.status_code == 200
        assert "code" not in response.json()
        assert sent[0][0] == "Test.User+code@qq.com"
        assert len(sent[0][1]) == 6
        assert client.post("/api/auth/email/code", json={"email": "Test.User+code@qq.com"}).status_code == 429
        verified = client.post("/api/auth/email/verify", json={"email": "Test.User+code@qq.com", "code": sent[0][1]})
        assert verified.status_code == 200
        assert verified.json()["user"]["email"] == "test.user+code@qq.com"
        assert client.get("/api/auth/me").json()["authenticated"] is True
        assert client.post("/api/auth/email/verify", json={"email": "Test.User+code@qq.com", "code": sent[0][1]}).status_code == 400
        with db.connect(global_db=True) as connection:
            assert connection.execute("SELECT count(*) FROM email_login_challenges").fetchone()[0] == 0


def test_email_code_accepts_internationalized_address_and_locks_after_five_attempts(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(email_auth, "_send_code", lambda address, code, settings: sent.append((address, code)))
    with _client(tmp_path, monkeypatch) as client:
        address = "用户@例子.公司"
        assert client.post("/api/auth/email/code", json={"email": address}).status_code == 200
        assert sent[0][0] == address
        wrong = "000000" if sent[0][1] != "000000" else "999999"
        for _ in range(5):
            assert client.post("/api/auth/email/verify", json={"email": address, "code": wrong}).status_code == 400
        assert client.post("/api/auth/email/verify", json={"email": address, "code": sent[0][1]}).status_code == 400


def test_email_code_logs_into_existing_local_user_but_not_external_only_account(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(email_auth, "_send_code", lambda address, code, settings: sent.append((address, code)))
    clock = [db.now()]
    monkeypatch.setattr(email_auth, "now", lambda: clock[0])
    with _client(tmp_path, monkeypatch) as client:
        assert client.post("/api/auth/register", json={
            "name": "Blocked", "email": "new@163.com", "password": "password-long-123",
        }).status_code == 403
        timestamp = db.now()
        with db.connect(global_db=True) as connection:
            connection.execute(
                "INSERT INTO users(id,email,name,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("usr_0000000000000001", "local@163.com", "Local", "legacy-password-hash", timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO users(id,email,name,google_id,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("usr_0000000000000002", "google@126.com", "Google", "google-sub", timestamp, timestamp),
            )
        assert client.post("/api/auth/email/code", json={"email": "local@163.com"}).status_code == 200
        result = client.post("/api/auth/email/verify", json={"email": "local@163.com", "code": sent[-1][1]})
        assert result.status_code == 200
        assert result.json()["user"]["id"] == "usr_0000000000000001"
        clock[0] += 61
        assert client.post("/api/auth/email/code", json={"email": "google@126.com"}).status_code == 200
        result = client.post("/api/auth/email/verify", json={"email": "google@126.com", "code": sent[-1][1]})
        assert result.status_code == 409
        assert client.get("/api/auth/me").json()["user"]["id"] == "usr_0000000000000001"


def test_email_delivery_failure_does_not_leave_usable_challenge(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("SMTP connection failed")

    monkeypatch.setattr(email_auth, "_send_code", fail)
    with _client(tmp_path, monkeypatch) as client:
        response = client.post("/api/auth/email/code", json={"email": "user@139.com"})
        assert response.status_code == 502
        with db.connect(global_db=True) as connection:
            assert connection.execute("SELECT count(*) FROM email_login_challenges").fetchone()[0] == 0
