import asyncio
import io
import json
import zipfile

import httpx
import pytest

from backend.app import db, coding_collaboration as collaboration, github_service as github


@pytest.fixture
def team(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    token = db.use_tenant(None)
    db.init_db()
    for identity in ("leader", "member", "stranger"):
        db.resource_save("agents", {"name": identity, "subagent_ids": ["member"] if identity == "leader" else []}, identity)
    with db.connect() as connection:
        connection.execute("INSERT INTO threads(id,name,agent_id,created_at,updated_at) VALUES('thread','Test','leader',1,1)")
    yield
    db.reset_tenant(token)


def call(name, args, identity="leader", task=None, thread="thread"):
    return asyncio.run(collaboration.execute(name, args, db.resource_get("agents", identity), thread, "turn", task))


def test_messages_persist_without_launching_tasks_and_mark_read(team):
    result = call("team_send", {"agent_id": "member", "message": "Review parser changes"})
    assert result["task_created"] is False
    with db.connect() as connection:
        assert connection.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
    received = call("team_receive", {}, "member")
    assert received["messages"][0]["content"] == "Review parser changes"
    assert call("team_receive", {}, "member")["count"] == 0
    assert call("team_receive", {"unread_only": False}, "member")["messages"][0]["read_at"] is not None


def test_unauthorized_agent_thread_and_target_rejected(team):
    with pytest.raises(PermissionError):
        call("team_send", {"agent_id": "stranger", "message": "no"})
    with pytest.raises(PermissionError):
        call("team_receive", {}, "stranger")
    with pytest.raises(PermissionError):
        call("team_send", {"agent_id": "member", "message": "no"}, thread="another-thread")
    with pytest.raises(ValueError):
        call("team_send", {"agent_id": "member", "message": "a" * 16001})


def test_team_resource_and_same_parent_tasks_are_authorized(team):
    db.resource_save("agent_teams", {"name": "Dev", "member_ids": ["stranger"]}, "dev-team")
    db.resource_save("agents", {"name": "leader", "team_id": "dev-team"}, "leader")
    assert call("team_send", {"agent_id": "stranger", "message": "assigned team"})["delivered"]
    db.resource_save("agents", {"name": "leader", "team_id": None}, "leader")
    with db.connect() as connection:
        for task_id, identity, parent in (("parent", "leader", None), ("child", "stranger", "parent")):
            connection.execute("INSERT INTO tasks(id,kind,name,status,payload,parent_task_id,available_at,created_at,updated_at) VALUES(?,?,?,'running',?,?,1,1,1)", (task_id, "subagent", identity, json.dumps({"agent_id": identity, "thread_id": "thread"}), parent))
    assert call("team_send", {"agent_id": "leader", "message": "family"}, "stranger", "child")["delivered"]
    with pytest.raises(PermissionError):
        call("team_send", {"agent_id": "leader", "message": "spoofed"}, "member", "child")


def test_tenant_mailbox_cannot_read_other_tenants(team):
    call("team_send", {"agent_id": "member", "message": "private"})
    token = db.use_tenant("usr_0123456789abcdef")
    try:
        db.init_db()
        db.resource_save("agents", {"name": "leader", "subagent_ids": ["member"]}, "leader")
        db.resource_save("agents", {"name": "member"}, "member")
        with db.connect() as connection:
            connection.execute("INSERT INTO threads(id,name,agent_id,created_at,updated_at) VALUES('thread','Test','leader',1,1)")
        assert call("team_receive", {}, "member")["messages"] == []
    finally:
        db.reset_tenant(token)


def test_tenant_github_credentials_do_not_fallback_to_global(monkeypatch):
    monkeypatch.setenv("CODEZZN_GITHUB_TOKEN", "global-secret-test-only")
    monkeypatch.setenv("CODEZZN_GITHUB_USER_TOKENS", json.dumps({"usr_0123456789abcdef": "tenant-test-only"}))
    monkeypatch.delenv("CODEZZN_GITHUB_ALLOW_SHARED_TOKEN", raising=False)
    token = db.use_tenant(None)
    try:
        assert github.configured_token() == "global-secret-test-only"
        first = db.use_tenant("usr_0123456789abcdef")
        assert github.configured_token() == "tenant-test-only"
        db.reset_tenant(first)
        second = db.use_tenant("usr_1111111111111111")
        try:
            assert github.configured_token() == ""
            assert github.auth_header_command() == []
            monkeypatch.setenv("CODEZZN_GITHUB_ALLOW_SHARED_TOKEN", "true")
            assert github.configured_token() == "global-secret-test-only"
        finally:
            db.reset_tenant(second)
    finally:
        db.reset_tenant(token)


def test_github_remote_validation_rejects_lookalikes():
    assert github.parse_repo("https://github.com/org/repo.git") == ("org", "repo")
    assert github.parse_repo("git@github.com:org/repo.git") == ("org", "repo")
    for value in ("https://evilgithub.com/org/repo", "https://github.com/org/repo?token=bad", "https://github.com/../repo", "https://user:secret@github.com/org/repo"):
        with pytest.raises(github.GitHubError):
            github.parse_repo(value)


def test_pr_read_and_ci_rerun_are_explicit_endpoints(monkeypatch):
    requests = []
    async def fake_request(method, remote, path, payload=None):
        requests.append((method, path, payload))
        return {} if path == "pulls/7" else []
    monkeypatch.setattr(github, "request", fake_request)
    result = asyncio.run(github.read_pr("https://github.com/org/repo", 7))
    assert "review_comments" in result
    assert requests[1][1] == "pulls/7/files?per_page=100"
    asyncio.run(github.rerun_ci("https://github.com/org/repo", 99))
    assert requests[-1][:2] == ("POST", "actions/runs/99/rerun-failed-jobs")


def test_ci_log_signed_download_strips_token_and_caps_output(monkeypatch):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("job/step.txt", "x" * 5000)
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.host == "api.github.com":
            assert request.headers["authorization"] == "Bearer test-only-token"
            return httpx.Response(302, headers={"location": "https://results.blob.core.windows.net/logs/signed"})
        assert "authorization" not in request.headers
        return httpx.Response(200, content=archive.getvalue())
    real_client = httpx.AsyncClient
    monkeypatch.setattr(github, "configured_token", lambda: "test-only-token")
    monkeypatch.setattr(github.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(github.ci_logs("https://github.com/org/repo", 4, max_bytes=1024))
    assert result["bytes"] == 1024 and result["truncated"]
    assert len(requests) == 2


def test_ci_log_rejects_untrusted_redirect(monkeypatch):
    def handler(request):
        return httpx.Response(302, headers={"location": "https://attacker.example/logs"})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(github, "configured_token", lambda: "test-only-token")
    monkeypatch.setattr(github.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(github.GitHubError, match="受信任"):
        asyncio.run(github.ci_logs("https://github.com/org/repo", 4))
