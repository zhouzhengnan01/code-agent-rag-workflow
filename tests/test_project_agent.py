import asyncio
import stat

import pytest

from backend.app import agent


def test_approved_project_write_creates_real_file_and_records_artifact(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = workspace / "projects" / "prj_example"
    project.mkdir(parents=True)
    monkeypatch.setattr(agent, "WORKSPACE", workspace)
    monkeypatch.setattr(agent, "project_root", lambda _project_id: project)
    recorded = []
    monkeypatch.setattr(agent, "record_artifact", lambda *args: recorded.append(args))

    settings = {"sandbox_mode": "workspace-write", "auto_approve": True,
                "_project_save": True, "_project_id": "prj_example"}
    result = asyncio.run(agent.execute_tool(
        "write_file", {"path": "quicksort.py", "content": "print('sorted')\n"},
        settings, {"write_file": ("builtin",)}, thread_id="thread_1", turn_id="turn_1",
    ))

    assert (project / "quicksort.py").read_text(encoding="utf-8") == "print('sorted')\n"
    assert stat.S_IMODE((project / "quicksort.py").stat().st_mode) == 0o660
    assert (project / "quicksort.py").stat().st_gid == 10001
    assert not (workspace / "quicksort.py").exists()
    assert result["project_id"] == "prj_example"
    assert result["written"] == "quicksort.py"
    assert recorded == [("prj_example", "thread_1", "turn_1", project / "quicksort.py", "file")]


def test_project_file_path_cannot_escape_selected_project(tmp_path, monkeypatch):
    project = tmp_path / "projects" / "prj_selected"
    project.mkdir(parents=True)
    monkeypatch.setattr(agent, "project_root", lambda _project_id: project)
    settings = {"_project_save": True, "_project_id": "prj_selected"}

    with pytest.raises((ValueError, PermissionError)):
        agent.project_tool_path("../other/secret.py", settings)
    with pytest.raises((ValueError, PermissionError)):
        agent.project_tool_path("projects/prj_other/secret.py", settings)


def test_declining_project_save_blocks_file_write(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(agent, "WORKSPACE", workspace)
    settings = {"sandbox_mode": "workspace-write", "auto_approve": True, "_project_save": False}

    result = asyncio.run(agent.execute_tool(
        "write_file", {"path": "quicksort.py", "content": "not saved"},
        settings, {"write_file": ("builtin",)}, thread_id="thread_1", turn_id="turn_1",
    ))

    assert result["error"]["code"] == "project_write_declined"
    assert not (workspace / "quicksort.py").exists()


def test_agent_can_pause_for_a_user_choice_without_auto_approval():
    specs, routes = asyncio.run(agent.tool_specs({"builtin_tools": [], "auto_approve": True}))
    assert any(item["function"]["name"] == "ask_user" for item in specs)
    pending = asyncio.run(agent.execute_tool(
        "ask_user", {"question": "保存在哪里？", "options": [{"label": "新项目"}]},
        {"auto_approve": True}, routes,
    ))
    assert pending["error"]["code"] == "approval_required"
    answered = asyncio.run(agent.execute_tool(
        "ask_user", {"question": "保存在哪里？"},
        {"_user_answer": "新项目"}, routes, approved=True,
    ))
    assert answered == {"answer": "新项目"}
