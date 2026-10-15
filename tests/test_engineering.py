import asyncio
import json
from pathlib import Path

import pytest

from backend.app import db, engineering as eng


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.sqlite"))
    # Only the required table: no application startup, network or existing data.
    with db.connect() as conn:
        conn.execute("CREATE TABLE threads(id TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO threads VALUES(?)", [("thread-a",), ("thread-b",)])
    root = tmp_path / "project"
    root.mkdir()
    return root


def call(root, name, args=None, **kwargs):
    return run(eng.execute(name, args or {}, {"allow_shell": True}, root, thread_id="thread-a", **kwargs))


def test_review_real_python_syntax_conflict_and_secret(fixture):
    (fixture / "broken.py").write_text("def wrong(:\n  pass\n# <<<<<<< feature\nkey='sk-" + "a" * 30 + "'\n", encoding="utf-8")
    result = call(fixture, "engineering_review", {"paths": ["broken.py"]})
    assert result["status"] == "partial"
    assert {f["source"] for f in result["findings"]} == {"python_ast", "conflict_marker", "secret_pattern"}
    assert "sk-" not in json.dumps(result)
    assert result["tests_executed"] is False
    assert "model_reviewer_not_configured" in result["errors"][0]


def test_review_two_independent_passes_and_verification_filter(fixture):
    (fixture / "calc.py").write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")
    calls = []
    async def reviewer(persona, prompt):
        calls.append(persona)
        if persona == "verification":
            return {"accepted_indices": [0]}
        return {"findings": [
            {"path": "calc.py", "line": 2, "title": "Possible zero divisor", "severity": "warning", "evidence": "return a / b"},
            {"path": "../../outside.py", "line": 1, "severity": "error", "evidence": "bad", "title": "Fake"},
            {"path": "calc.py", "line": 99, "severity": "error", "evidence": "invented", "title": "Fake"},
        ]}
    result = call(fixture, "engineering_review", {"paths": ["calc.py"]}, reviewer=reviewer)
    assert calls == ["correctness", "security_and_tests", "verification"]
    assert result["status"] == "changes_requested"
    assert result["finding_count"] == 1
    assert result["findings"][0]["validated"]
    assert result["rejected_count"] == 5


def test_review_model_failure_is_partial_and_no_diff_failure_is_pass(fixture):
    (fixture / "valid.py").write_text("x = 1\n")
    async def broken(*args):
        raise RuntimeError("provider unavailable")
    result = call(fixture, "engineering_review", {"paths": ["valid.py"]}, reviewer=broken)
    assert result["status"] == "partial" and len(result["errors"]) == 2
    result = call(fixture, "engineering_review", {"git_error": "not a repository"})
    assert result["status"] == "failed"


def test_review_index_snapshot_is_not_confused_with_worktree(fixture):
    (fixture / "version.py").write_text("pass\n")
    diff = "--- a/version.py\n+++ b/version.py\n@@ -1 +1 @@\n-pass\n+def broken(:\n"
    result = call(fixture, "engineering_review", {"staged": True, "diff": diff, "source_files": {"version.py": "def broken(:\n"}})
    assert result["source_basis"] == "git_snapshot"
    assert result["findings"][0]["source"] == "python_ast"
    assert (fixture / "version.py").read_text() == "pass\n"
    missing = call(fixture, "engineering_review", {"staged": True, "diff": diff})
    assert missing["status"] == "partial"
    assert any("git_snapshot_unavailable" in error for error in missing["errors"])


def test_discover_does_not_execute_untrusted_repo_scripts(fixture):
    (fixture / "package.json").write_text(json.dumps({"scripts": {"test": "rm -rf /", "lint": "evil"}}))
    result = call(fixture, "quality_discover")
    assert [item["command"] for item in result["checks"]] == ["npm run lint", "npm run test"]
    assert all(item["requires_approval"] for item in result["checks"])
    assert result["automatic_execution"] is False


def test_approved_quality_and_plan_gate_with_stale_check_detection(fixture):
    (fixture / "a.py").write_text("a=1\n")
    plan = {"action": "create", "steps": [{"content": "Implement", "status": "completed"}], "required_checks": ["test"]}
    assert call(fixture, "plan_manage", plan)["status"] == "proposed"
    assert call(fixture, "plan_manage", {"action": "approve", "expected_revision": 1})["requires_approval"]
    call(fixture, "plan_manage", {"action": "approve", "expected_revision": 1}, approved=True)
    checks = {"checks": [{"name": "test", "command": "python -m pytest -q"}]}
    observed = []
    async def sandbox(command):
        observed.append(command)
        return {"exit_code": 0, "stdout": "1 passed"}
    assert call(fixture, "quality_run", checks, runner=sandbox)["requires_approval"]
    assert observed == []
    assert call(fixture, "quality_run", checks, runner=sandbox, approved=True)["status"] == "passed"
    assert run(eng.completion_gate({"allow_shell": True}, fixture, "thread-a"))["allowed"]
    (fixture / "a.py").write_text("a=2\n")
    assert "quality_results_stale" in run(eng.completion_gate({"allow_shell": True}, fixture, "thread-a"))["blockers"]
    plan["steps"][0]["content"] = "Different plan"
    assert call(fixture, "plan_manage", plan)["status"] == "proposed"
    with pytest.raises(ValueError, match="计划版本"):
        call(fixture, "plan_manage", {"action": "approve", "expected_revision": 1}, approved=True)


def test_checks_must_report_valid_exit_and_cannot_bypass_shell_permission(fixture):
    async def bad(command):
        return {"stdout": "pretend passed"}
    checks = {"checks": [{"name": "test", "command": "true"}]}
    assert call(fixture, "quality_run", checks, runner=bad, approved=True)["status"] == "failed"
    with pytest.raises(PermissionError):
        run(eng.execute("quality_run", checks, {"allow_shell": False}, fixture, "thread-a", approved=True, runner=bad))


def test_quality_baseline_comparison_does_not_mistake_it_for_final_verification(fixture):
    checks = {"checks": [{"name": "test", "command": "test-command"}, {"name": "lint", "command": "lint-command"}]}
    async def baseline(command):
        return {"exit_code": 0 if command == "test-command" else 1}
    assert call(fixture, "quality_run", {**checks, "baseline": True}, runner=baseline, approved=True)["baseline_saved"]
    assert "quality" not in eng.state(fixture, "thread-a")
    async def after(command):
        return {"exit_code": 1}
    result = call(fixture, "quality_run", checks, runner=after, approved=True)
    assert result["baseline_comparison"]["new_failures"] == ["test"]
    assert result["baseline_comparison"]["existing_failures"] == ["lint"]
    assert result["status"] == "failed"


def test_hooks_need_explicit_approval_and_failure_blocks_completion(fixture):
    body = {"action": "set", "hooks": [{"event": "Stop", "command": "python -m pytest -q"}, {"event": "PreToolUse", "tool": "write_file", "command": "check-policy"}]}
    assert call(fixture, "hook_manage", body)["requires_approval"]
    call(fixture, "hook_manage", body, approved=True)
    seen = []
    async def sandbox(command):
        seen.append(command)
        return {"exit_code": 1, "stderr": "failed"}
    assert run(eng.lifecycle("PreToolUse", {"allow_shell": True}, fixture, "thread-a", tool_name="read_file", runner=sandbox))["allowed"]
    assert seen == []
    assert not run(eng.lifecycle("PreToolUse", {"allow_shell": True}, fixture, "thread-a", tool_name="write_file", runner=sandbox))["allowed"]
    assert "stop_hook_failed" in run(eng.completion_gate({"allow_shell": True}, fixture, "thread-a", runner=sandbox))["blockers"]


def test_checkpoint_real_bytes_diff_rewind_and_user_edit_cas(fixture):
    initial = b"x=1\r\n"
    (fixture / "existing.py").write_bytes(initial)
    checkpoint = call(fixture, "task_checkpoint", {"paths": ["existing.py", "new.py"]})
    (fixture / "existing.py").write_bytes(b"x=2\n")
    (fixture / "new.py").write_bytes(b"pass\n")
    snapshot = call(fixture, "task_diff", checkpoint)
    assert len(snapshot["changes"]) == 2
    args = {**checkpoint, "expected_hashes": snapshot["expected_hashes"]}
    assert call(fixture, "task_rewind", args)["requires_approval"]
    (fixture / "existing.py").write_bytes(b"user edited after preview\n")
    assert call(fixture, "task_rewind", args, approved=True)["status"] == "conflict"
    assert (fixture / "new.py").exists()  # Full preflight prevents partial rollback.
    fresh = call(fixture, "task_diff", checkpoint)
    result = call(fixture, "task_rewind", {**checkpoint, "expected_hashes": fresh["expected_hashes"]}, approved=True)
    assert result["status"] == "restored"
    assert (fixture / "existing.py").read_bytes() == initial
    assert not (fixture / "new.py").exists()


def test_state_and_checkpoints_are_bound_to_thread_and_root(fixture):
    checkpoint = call(fixture, "task_checkpoint", {"paths": ["new.py"]})
    with pytest.raises(ValueError):
        run(eng.execute("task_diff", checkpoint, {}, fixture, "thread-b"))
    different = fixture / "other"
    different.mkdir()
    with pytest.raises(ValueError):
        call(different, "task_diff", checkpoint)
    with pytest.raises(ValueError):
        run(eng.execute("plan_manage", {"action": "get"}, {}, fixture, "unknown"))


@pytest.mark.parametrize("path", ["../outside", ".git/config", ".codezzn/secrets", ".", "C:/Windows/system.ini"])
def test_checkpoint_rejects_unsafe_paths(fixture, path):
    with pytest.raises(ValueError):
        call(fixture, "task_checkpoint", {"paths": [path]})


def test_tenant_data_is_not_shared(fixture, monkeypatch):
    # A distinct database simulates the existing tenant routing, not global state.
    checkpoint = call(fixture, "task_checkpoint", {"paths": ["a.py"]})
    monkeypatch.setattr(db, "DB_PATH", str(fixture.parent / "other.sqlite"))
    with db.connect() as conn:
        conn.execute("CREATE TABLE threads(id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO threads VALUES('thread-a')")
    with pytest.raises(ValueError):
        call(fixture, "task_diff", checkpoint)


def test_thread_delete_cascades_engineering_state(fixture):
    call(fixture, "task_checkpoint", {"paths": ["a.py"]})
    call(fixture, "plan_manage", {"action": "create", "steps": [{"content": "Implement"}]})
    with db.connect() as conn:
        conn.execute("DELETE FROM threads WHERE id='thread-a'")
        assert conn.execute("SELECT count(*) FROM engineering_checkpoints").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM engineering_state").fetchone()[0] == 0
