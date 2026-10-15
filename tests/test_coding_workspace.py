"""Only temporary repositories/files; no models, network or live workspace."""
import asyncio
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app import coding_workspace as cw, db, workspace, worktrees


@pytest.fixture
def roots(tmp_path, monkeypatch):
    root = tmp_path / "tenant"
    root.mkdir()
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", root)
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "database.db"))
    token = workspace.use_workspace(root)
    tenant = db.use_tenant(None)
    async def no_git(*args, **kwargs):
        return {"exit_code": 128, "output": "not a git repository"}
    monkeypatch.setattr(cw, "run_command", no_git)
    yield root
    db.reset_tenant(tenant)
    workspace.reset_workspace(token)


def prepare(root, task="task-a", project=None, **kwargs):
    return asyncio.run(cw.prepare_coding_workspace(task_id=task, thread_id="same-thread", project_id=project, **kwargs))


def publish(item, paths=None):
    token = cw.use_coding_workspace(item)
    try:
        return cw.publish_coding_workspace(paths)
    finally:
        cw.reset_coding_workspace(token)


def test_non_git_tasks_are_isolated_and_resume_same_task(roots):
    (roots / "AGENTS.md").write_text("test project instructions")
    first = prepare(roots)
    child = prepare(roots, "child-task")
    assert first["mode"] == "snapshot"
    assert cw.workspace_path(first) != roots
    assert cw.workspace_path(first) != cw.workspace_path(child)
    assert (cw.workspace_path(first) / "AGENTS.md").read_text() == "test project instructions"
    (cw.workspace_path(first) / "code.py").write_text("first task")
    assert not (cw.workspace_path(child) / "code.py").exists()
    assert prepare(roots)["path"] == first["path"]


def test_publication_cas_preserves_external_edits_and_retains_task(roots):
    original = roots / "code.py"
    original.write_text("original")
    first = prepare(roots)
    (cw.workspace_path(first) / "code.py").write_text("task edit")
    original.write_text("user edit")
    with pytest.raises(cw.CodingWorkspaceConflict, match="拒绝覆盖"):
        publish(first)
    assert original.read_text() == "user edit"
    assert (cw.workspace_path(first) / "code.py").read_text() == "task edit"


def test_concurrent_new_file_collision_is_not_overwritten(roots):
    first, child = prepare(roots), prepare(roots, "child-task")
    (cw.workspace_path(first) / "code.py").write_text("parent")
    (cw.workspace_path(child) / "code.py").write_text("child")
    assert publish(first)["published"] == ["code.py"]
    with pytest.raises(cw.CodingWorkspaceConflict):
        publish(child)
    assert (roots / "code.py").read_text() == "parent"


def test_successful_publish_updates_baseline_and_keeps_original_backup(roots):
    (roots / "code.py").write_text("before")
    first = prepare(roots)
    copy = cw.workspace_path(first) / "code.py"
    copy.write_text("after")
    assert publish(first)["published"] == ["code.py"]
    copy.write_text("again")
    assert publish(first)["published"] == ["code.py"]
    assert publish(first)["published"] == []
    originals = list((roots / ".codezzn-coding").glob("*/revisions/*/originals/code.py"))
    assert {path.read_text() for path in originals} == {"before", "after"}


def test_delete_and_multi_file_conflict_preflight(roots):
    (roots / "delete.py").write_text("keep backup")
    (roots / "conflict.py").write_text("baseline")
    first = prepare(roots)
    (cw.workspace_path(first) / "delete.py").unlink()
    (cw.workspace_path(first) / "conflict.py").write_text("agent")
    (roots / "conflict.py").write_text("user")
    with pytest.raises(cw.CodingWorkspaceConflict):
        publish(first)
    assert (roots / "delete.py").exists()
    assert publish(first, ["delete.py"])["deleted"] == ["delete.py"]


def test_project_execution_root_does_not_change_canonical_files_root(roots):
    project = "prj_0123456789abcdef"
    canonical = cw.project_root(project)
    canonical.mkdir(parents=True)
    (canonical / "main.py").write_text("pass")
    first = prepare(roots, project=project)
    token = cw.use_coding_workspace(first)
    try:
        assert cw.execution_project_root(project) == cw.workspace_path(first)
        assert cw.project_root(project) == canonical
    finally:
        cw.reset_coding_workspace(token)
    assert cw.execution_project_root(project) == canonical


def test_inspect_workspace_is_readonly_and_filters_thread_turn(roots):
    assert cw.inspect_workspace("same-thread") is None
    assert not (roots / ".codezzn-coding").exists()
    first = prepare(roots, turn_id="first-turn")
    second = prepare(roots, "second", turn_id="second-turn")
    assert cw.inspect_workspace("same-thread")["path"] == second["path"]
    assert cw.inspect_workspace("same-thread", turn_id="first-turn")["path"] == first["path"]
    assert cw.inspect_workspace("another-thread") is None
    assert "baseline" not in cw.inspect_workspace("same-thread")


def test_logical_scope_is_stable_between_project_turns_and_distinct_for_projects(roots):
    from backend.app import engineering
    db.init_db()
    with db.connect() as connection:
        connection.execute("INSERT INTO threads(id,name,created_at,updated_at) VALUES('same-thread','Test',1,1)")
    project, other_project = "prj_0123456789abcdef", "prj_1111111111111111"
    canonical = cw.project_root(project)
    canonical.mkdir(parents=True)
    (canonical / "main.py").write_text("before\n")
    first = prepare(roots, "first", project, turn_id="turn-one")
    first_root = cw.workspace_path(first)
    checkpoint = asyncio.run(engineering.execute("task_checkpoint", {"paths": ["main.py"]}, {}, first_root, "same-thread", "turn-one"))
    asyncio.run(engineering.execute("plan_manage", {"action": "create", "steps": [{"content": "Review parser"}]}, {}, first_root, "same-thread", "turn-one"))
    asyncio.run(engineering.execute("hook_manage", {"action": "set", "hooks": [{"event": "Stop", "command": "python -m pytest -q"}]}, {}, first_root, "same-thread", "turn-one", approved=True))
    (first_root / "main.py").write_text("after\n")
    publish(first)
    second = prepare(roots, "second", project, turn_id="turn-two")
    second_root = cw.workspace_path(second)
    assert first_root != second_root
    assert cw.logical_root(first_root) == cw.logical_root(second_root) == canonical
    assert engineering.state(second_root, "same-thread")["plan"]["steps"][0]["content"] == "Review parser"
    assert engineering.state(second_root, "same-thread")["hooks"][0]["event"] == "Stop"
    difference = asyncio.run(engineering.execute("task_diff", {"checkpoint_id": checkpoint["checkpoint_id"]}, {}, second_root, "same-thread", "turn-two"))
    assert "-before" in difference["changes"][0]["diff"]
    assert "+after" in difference["changes"][0]["diff"]
    third = prepare(roots, "third", other_project, turn_id="turn-three")
    third_root = cw.workspace_path(third)
    assert engineering.state(third_root, "same-thread") == {}
    with pytest.raises(ValueError, match="不属于当前对话/工作区"):
        asyncio.run(engineering.execute("task_diff", {"checkpoint_id": checkpoint["checkpoint_id"]}, {}, third_root, "same-thread", "turn-three"))


def test_logical_scope_rejects_forged_manifest_and_other_tenant(roots):
    first = prepare(roots)
    metadata = roots / first["metadata"]
    import json
    manifest = json.loads(metadata.read_text(encoding="utf-8"))
    manifest["source"] = "projects/prj_0123456789abcdef"
    metadata.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="项目边界"):
        cw.logical_root(cw.workspace_path(first))
    token = db.use_tenant("usr_0123456789abcdef")
    try:
        with pytest.raises(PermissionError, match="其他用户"):
            cw.logical_root(roots / first["path"])
    finally:
        db.reset_tenant(token)


def test_publication_rejects_traversal_and_snapshot_limit(roots, monkeypatch):
    first = prepare(roots)
    with pytest.raises(ValueError):
        publish(first, ["../secret"])
    (roots / "large.py").write_bytes(b"12345")
    monkeypatch.setattr(cw, "MAX_BYTES", 4)
    with pytest.raises(ValueError, match="上限"):
        prepare(roots, "too-large")


def test_stale_lock_fails_closed(roots, monkeypatch):
    monkeypatch.setattr(cw, "PREPARE_LOCK_TIMEOUT", 0)
    with cw._lock(roots):
        with pytest.raises(cw.CodingWorkspaceConflict, match="正在初始化"):
            prepare(roots)


def test_parallel_task_preparation_serializes_briefly_not_shared(roots, monkeypatch):
    calls = []
    async def slow_probe(*args, **kwargs):
        calls.append(args)
        await asyncio.sleep(0.08)
        return {"exit_code": 128}
    monkeypatch.setattr(cw, "run_command", slow_probe)
    async def run():
        return await asyncio.gather(cw.prepare_coding_workspace(task_id="one"), cw.prepare_coding_workspace(task_id="two"))
    first, second = asyncio.run(run())
    assert first["path"] != second["path"]
    assert len(calls) == 2


def test_symlink_source_is_rejected(roots, tmp_path):
    external = tmp_path / "outside"
    external.write_text("not tenant content")
    try:
        (roots / "link").symlink_to(external)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(ValueError, match="符号链接"):
        prepare(roots)


def test_real_temporary_git_project_worktrees_include_dirty_files(roots, monkeypatch):
    project = "prj_0123456789abcdef"
    canonical = cw.project_root(project)
    canonical.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(canonical)], check=True)
    (canonical / "main.py").write_text("committed")
    subprocess.run(["git", "-C", str(canonical), "add", "main.py"], check=True)
    subprocess.run(["git", "-C", str(canonical), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial"], check=True)
    (canonical / "main.py").write_text("dirty source")
    (canonical / "new.py").write_text("untracked source")
    async def fake_broker(command, mode, cwd):
        if command.startswith("test -z"):
            return {"exit_code": 0, "output": "head"}
        parts = shlex.split(command)
        parts = [str(roots / value[len("/workspace/"):]) if value.startswith("/workspace/") else value for value in parts]
        result = subprocess.run(parts, cwd=roots / cwd, capture_output=True, text=True)
        return {"exit_code": result.returncode, "output": result.stdout + result.stderr}
    monkeypatch.setattr(cw, "run_command", fake_broker)
    first = prepare(roots, project=project)
    child = prepare(roots, "child-task", project)
    assert first["mode"] == child["mode"] == "git-worktree"
    assert first["path"] != child["path"]
    assert (cw.workspace_path(first) / "main.py").read_text() == "dirty source"
    assert (cw.workspace_path(first) / "new.py").read_text() == "untracked source"
    assert (cw.workspace_path(first) / ".git").is_file()
    (cw.workspace_path(first) / "new.py").write_text("published")
    assert publish(first)["published"] == ["new.py"]
    assert (canonical / "new.py").read_text() == "published"


def test_legacy_child_never_reuses_parent_thread_worktree(roots, monkeypatch):
    db.init_db()
    with db.connect() as connection:
        connection.execute("INSERT INTO worktrees(id,task_id,thread_id,path,branch,base_ref,status,created_at,updated_at) VALUES('wt_parent','parent','same-thread','.codezzn-worktrees/parent','branch','HEAD','active',1,1)")
    calls = []
    async def no_git(command, mode):
        calls.append(command)
        return {"exit_code": 128, "output": "no head"}
    monkeypatch.setattr(worktrees, "run_command", no_git)
    assert asyncio.run(worktrees.ensure_worktree(task_id="child", thread_id="same-thread")) is None
    assert calls


def test_legacy_remove_does_not_force_or_mark_failed_removal(roots, monkeypatch):
    db.init_db()
    with db.connect() as connection:
        connection.execute("INSERT INTO worktrees(id,task_id,thread_id,path,branch,base_ref,status,created_at,updated_at) VALUES('wt_dirty','task','thread','.codezzn-worktrees/dirty','branch','HEAD','active',1,1)")
    async def dirty(command, mode):
        assert "--force" not in command
        return {"exit_code": 128, "output": "contains modified or untracked files"}
    monkeypatch.setattr(worktrees, "run_command", dirty)
    with pytest.raises(RuntimeError, match="保留全部工作"):
        asyncio.run(worktrees.remove_worktree("wt_dirty"))
    with db.connect() as connection:
        assert connection.execute("SELECT status FROM worktrees WHERE id='wt_dirty'").fetchone()[0] == "active"


def test_lock_releases_on_process_crash_without_deleting_metadata(roots):
    script = "import os,sys; from pathlib import Path; from backend.app import workspace,coding_workspace as cw; workspace.BASE_WORKSPACE=Path(sys.argv[1]); manager=cw._lock(Path(sys.argv[1])); manager.__enter__(); os._exit(0)"
    subprocess.run([sys.executable, '-c', script, str(roots)], check=True, timeout=10)
    with cw._lock(roots):
        assert (roots / '.codezzn-coding' / 'locks').is_dir()
