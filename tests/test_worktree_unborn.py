import asyncio
import subprocess

from backend.app import db, worktrees, workspace


def test_unborn_git_head_falls_back_without_creating_worktree(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    root = tmp_path / "workspace"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)

    commands = []

    async def sandbox_command(command, mode):
        commands.append((command, mode))
        result = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True)
        return {"exit_code": result.returncode, "output": result.stdout + result.stderr}

    monkeypatch.setattr(worktrees, "run_command", sandbox_command)
    assert asyncio.run(worktrees.ensure_worktree(thread_id="unborn")) is None
    assert len(commands) == 1
    assert commands[0][1] == "read-only"
    assert not (root / ".codezzn-worktrees").exists()
    with db.connect() as connection:
        assert connection.execute("SELECT count(*) FROM worktrees").fetchone()[0] == 0


def test_committed_git_head_still_creates_isolated_worktree(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "commit", "--allow-empty", "-m", "initial"], check=True, capture_output=True,
    )

    async def sandbox_command(command, mode):
        result = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True)
        return {"exit_code": result.returncode, "output": result.stdout + result.stderr}

    monkeypatch.setattr(worktrees, "run_command", sandbox_command)
    item = asyncio.run(worktrees.ensure_worktree(thread_id="committed"))
    assert item["status"] == "active"
    assert (root / item["path"] / ".git").exists()
