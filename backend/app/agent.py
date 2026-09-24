import json
import os
import difflib
import shlex
import re
import tempfile
import base64
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from .capabilities import model_candidates, role_template, tool_policy_decision
from .db import connect, new_id, now, resource_get
from .knowledge import format_retrieval_context
from .knowledge_service import search
from .memory import memory_context, save_memory, search_memories
from .mcp import mcp_manager
from .model import ModelError, chat_completion, stream_chat_completion, uses_responses, response_completion, stream_response_completion
from .sandbox import run_command
from .tasks import enqueue_task, get_task
from .workspace import BASE_WORKSPACE, current_workspace, sandbox_cwd, tenant_workspace, use_workspace, reset_workspace
from .code_intelligence import rebuild_index, symbols as code_symbols, references as code_references, graph as code_graph
from .lsp import lsp_manager
from .browser import browser_manager
from .github_service import create_pr, ci_status, review_comment, auth_header_command
from .skill_packages import package_path, read_package_file, verify_package
from .projects import get_turn_project, project_root, record_artifact
from .domain_tools import (
    create_project_tool, create_workflow_draft, discard_workflow_draft,
    enqueue_workflow_run, get_workflow_draft, get_workflow_run,
    get_workflow_version, list_project_artifacts_tool, list_project_tools, list_workflow_tools, list_workflow_versions,
    save_workflow_draft, select_project_tool, update_workflow_draft,
)


WORKSPACE = Path(os.getenv("CODEZZN_WORKSPACE", os.path.join(os.getcwd(), "workspace"))).resolve()


def _workspace_root():
    """Return the task worktree, while preserving the legacy WORKSPACE test hook."""
    selected = current_workspace().resolve()
    return WORKSPACE.resolve() if selected == BASE_WORKSPACE.resolve() and WORKSPACE.resolve() != BASE_WORKSPACE.resolve() else selected


BUILTIN_SCHEMAS = {
    "ask_user": {"description": "需要用户决定重要选项或补充信息时暂停任务，并在对话中显示可选项及自由输入；等待用户回答后继续。不要用它代替写文件工具的审批。", "parameters": {"type": "object", "properties": {"question": {"type": "string"}, "options": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {"label": {"type": "string"}, "description": {"type": "string"}}, "required": ["label"]}}}, "required": ["question"]}},
    "project_list": {"description": "列出当前用户已有项目，供选择目标资产位置", "parameters": {"type": "object", "properties": {}}},
    "project_create": {"description": "经用户确认后创建当前用户的新项目；返回 project_id 并绑定本次对话", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}}, "required": ["name"]}},
    "project_select": {"description": "经用户确认后选择一个已有项目，允许本次对话的文件产物保存在该项目", "parameters": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]}},
    "project_artifacts": {"description": "列出当前用户指定项目中的已保存文件", "parameters": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]}},
    "workflow_list": {"description": "列出当前用户的 Workflow 和版本", "parameters": {"type": "object", "properties": {}}},
    "workflow_get": {"description": "读取一个已保存 Workflow 的完整定义", "parameters": {"type": "object", "properties": {"workflow_id": {"type": "string"}}, "required": ["workflow_id"]}},
    "workflow_versions": {"description": "列出一个 Workflow 的已保存历史版本", "parameters": {"type": "object", "properties": {"workflow_id": {"type": "string"}}, "required": ["workflow_id"]}},
    "workflow_version_get": {"description": "读取 Workflow 的指定历史版本定义", "parameters": {"type": "object", "properties": {"workflow_id": {"type": "string"}, "version": {"type": "integer"}}, "required": ["workflow_id", "version"]}},
    "workflow_draft_create": {"description": "创建或编辑 Workflow 草稿，不改变正式 Workflow；保存前先验证节点和连线", "parameters": {"type": "object", "properties": {"workflow_id": {"type": "string"}, "project_id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"}, "nodes": {"type": "array", "items": {"type": "object"}}, "edges": {"type": "array", "items": {"type": "object"}}, "max_parallel": {"type": "integer"}}, "required": ["name", "nodes", "edges"]}},
    "workflow_draft_update": {"description": "修改尚未保存的 Workflow 草稿；不会改变正式 Workflow", "parameters": {"type": "object", "properties": {"draft_id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"}, "nodes": {"type": "array", "items": {"type": "object"}}, "edges": {"type": "array", "items": {"type": "object"}}, "max_parallel": {"type": "integer"}}, "required": ["draft_id"]}},
    "workflow_draft_save": {"description": "经用户确认后将 Workflow 草稿正式保存；若源 Workflow 已改变则拒绝覆盖", "parameters": {"type": "object", "properties": {"draft_id": {"type": "string"}}, "required": ["draft_id"]}},
    "workflow_draft_discard": {"description": "丢弃 Workflow 草稿；正式 Workflow 不受影响", "parameters": {"type": "object", "properties": {"draft_id": {"type": "string"}}, "required": ["draft_id"]}},
    "workflow_run": {"description": "经用户确认后将已保存 Workflow 放入后台队列执行，返回可追踪的 run_id", "parameters": {"type": "object", "properties": {"workflow_id": {"type": "string"}, "input": {}}, "required": ["workflow_id"]}},
    "workflow_run_get": {"description": "查看 Workflow 后台运行的状态、输出和执行记录", "parameters": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]}},
    "knowledge_search": {"description": "搜索已选择的知识库", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}},
    "list_files": {"description": "列出工作区文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
    "read_file": {"description": "读取工作区内的文本文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    "write_file": {"description": "写入工作区内的文本文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    "apply_patch": {"description": "应用 unified diff，或对单个文件执行精确 old/new 替换；二者选一", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "精确替换时必填"}, "patch": {"type": "string", "description": "完整 unified diff"}, "old": {"type": "string"}, "new": {"type": "string"}}}},
    "run_shell": {"description": "在工作区执行命令；仅在智能体允许 shell 时使用", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    "git_status": {"description": "读取工作区 Git 状态", "parameters": {"type": "object", "properties": {}}},
    "git_diff": {"description": "读取工作区未提交差异", "parameters": {"type": "object", "properties": {"staged": {"type": "boolean"}}}},
    "git_log": {"description": "读取最近 Git 提交记录", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    "review": {"description": "只读检查 Git 变更并返回结构化审查材料", "parameters": {"type": "object", "properties": {"staged": {"type": "boolean"}, "base": {"type": "string"}, "range": {"type": "string"}}}},
    "search_code": {"description": "使用 ripgrep 在工作区搜索代码和文本", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"}}, "required": ["query"]}},
    "run_tests": {"description": "在隔离容器中运行测试命令并返回退出码和输出", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    "git_branch": {"description": "创建并切换 Git 分支", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "base": {"type": "string"}}, "required": ["name"]}},
    "git_stage": {"description": "将指定的工作区路径加入 Git 暂存区", "parameters": {"type": "object", "properties": {"paths": {"type": "array", "items": {"type": "string"}, "maxItems": 100}}, "required": ["paths"]}},
    "git_commit": {"description": "提交当前已暂存的 Git 变更", "parameters": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}},
    "restore_file": {"description": "从 Codezzn 自动备份恢复文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "backup": {"type": "string"}}, "required": ["path", "backup"]}},
    "memory_search": {"description": "搜索当前用户和项目的长期记忆", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}},
    "memory_save": {"description": "保存可跨会话使用的偏好、项目事实或经验", "parameters": {"type": "object", "properties": {"content": {"type": "string"}, "scope": {"type": "string", "enum": ["user", "project", "thread"]}, "kind": {"type": "string"}, "importance": {"type": "number"}}, "required": ["content"]}},
    "delegate_task": {"description": "把一个或多个独立任务委派给允许的子智能体并在后台并行执行", "parameters": {"type": "object", "properties": {"tasks": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {"task": {"type": "string"}, "agent_id": {"type": "string"}, "name": {"type": "string"}}, "required": ["task"]}}}, "required": ["tasks"]}},
    "task_status": {"description": "查询或等待后台任务完成", "parameters": {"type": "object", "properties": {"task_ids": {"type": "array", "items": {"type": "string"}}, "wait_seconds": {"type": "integer"}}, "required": ["task_ids"]}},
    "code_index": {"description": "重建工作区 AST/符号/调用/依赖索引", "parameters": {"type":"object","properties":{}}},
    "code_symbols": {"description": "按名称查询代码符号", "parameters": {"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer"}}}},
    "find_references": {"description": "查找符号在工作区中的所有引用", "parameters": {"type":"object","properties":{"symbol":{"type":"string"},"limit":{"type":"integer"}},"required":["symbol"]}},
    "call_graph": {"description": "读取函数调用图", "parameters": {"type":"object","properties":{"symbol":{"type":"string"},"limit":{"type":"integer"}}}},
    "dependency_graph": {"description": "读取模块导入依赖图", "parameters": {"type":"object","properties":{"symbol":{"type":"string"},"limit":{"type":"integer"}}}},
    "lsp_request": {"description": "调用已配置的 LSP 3.18 language server", "parameters": {"type":"object","properties":{"server_id":{"type":"string"},"method":{"type":"string"},"params":{"type":"object"}},"required":["server_id","method"]}},
    "git_clone": {"description": "在隔离容器中克隆 Git 仓库", "parameters": {"type":"object","properties":{"url":{"type":"string"},"path":{"type":"string"},"branch":{"type":"string"}},"required":["url","path"]}},
    "git_fetch": {"description": "从远端获取 Git refs", "parameters": {"type":"object","properties":{"remote":{"type":"string"},"prune":{"type":"boolean"}}}},
    "git_push": {"description": "推送当前分支到远端", "parameters": {"type":"object","properties":{"remote":{"type":"string"},"branch":{"type":"string"},"set_upstream":{"type":"boolean"}}}},
    "git_merge": {"description": "合并 ref 并返回冲突文件；冲突时保留工作树供后续解决", "parameters": {"type":"object","properties":{"ref":{"type":"string"}},"required":["ref"]}},
    "git_merge_abort": {"description": "中止当前 merge conflict 工作流", "parameters": {"type":"object","properties":{}}},
    "github_create_pr": {"description": "在 GitHub 创建 Pull Request", "parameters": {"type":"object","properties":{"title":{"type":"string"},"head":{"type":"string"},"base":{"type":"string"},"body":{"type":"string"},"draft":{"type":"boolean"}},"required":["title","head","base"]}},
    "github_ci_status": {"description": "查询 GitHub Checks 和 Actions 状态", "parameters": {"type":"object","properties":{"ref":{"type":"string"}},"required":["ref"]}},
    "github_review_comment": {"description": "向 GitHub PR 提交行级 review comment", "parameters": {"type":"object","properties":{"pull_number":{"type":"integer"},"body":{"type":"string"},"commit_id":{"type":"string"},"path":{"type":"string"},"line":{"type":"integer"},"side":{"type":"string"}},"required":["pull_number","body","commit_id","path","line"]}},
    "skill_read_file": {"description": "读取已安装 Skill 包中的 reference、asset 文本或脚本", "parameters": {"type":"object","properties":{"skill_id":{"type":"string"},"path":{"type":"string"}},"required":["skill_id","path"]}},
    "skill_run_script": {"description": "在隔离容器中执行 Skill 包 scripts/ 下的脚本", "parameters": {"type":"object","properties":{"skill_id":{"type":"string"},"path":{"type":"string"},"args":{"type":"array","items":{"type":"string"}}},"required":["skill_id","path"]}},
    "browser": {"description": "操作无头 Chromium：导航、DOM 检查、元素/坐标点击、输入、键盘、滚动、等待、截图和页面脚本", "parameters": {"type":"object","properties":{"action":{"type":"string","enum":["navigate","inspect","click","mouse_click","mouse_move","scroll","hover","type","press","wait","screenshot","evaluate"]},"session":{"type":"string"},"url":{"type":"string"},"selector":{"type":"string"},"text":{"type":"string"},"key":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"delta_x":{"type":"number"},"delta_y":{"type":"number"},"seconds":{"type":"number"},"path":{"type":"string"},"full_page":{"type":"boolean"},"script":{"type":"string"}},"required":["action"]}},
}

MAX_INSTRUCTIONS = 50000
SANDBOX_MODES = {"read-only", "workspace-write", "danger-full-access"}


def sandbox_mode(agent):
    mode = str(agent.get("sandbox_mode", "workspace-write"))
    if mode not in SANDBOX_MODES:
        raise ValueError(f"不支持的沙箱模式: {mode}")
    return mode


def _event(event_type, **data):
    allowed = {"count", "name", "status", "content", "usage", "sources", "reason", "provider", "model", "round", "approval_id", "turn_id"}
    return {"id": new_id("evt"), "timestamp": datetime.now(timezone.utc).isoformat(), "type": event_type,
            **{key: value for key, value in data.items() if key in allowed}}


async def _emit(events, callback, event_type, **data):
    event = _event(event_type, **data)
    events.append(event)
    if callback:
        await callback(event)


def persist_event(event, thread_id=None, turn_id=None, sequence=None):
    if not thread_id or not turn_id:
        return
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO turn_events(id,thread_id,turn_id,sequence,type,data,created_at) VALUES(?,?,?,?,?,?,?)", (event["id"], thread_id, turn_id, sequence or len(event.get("content", "")), event["type"], json.dumps(event, ensure_ascii=False), now()))


def load_instructions(cwd=None, workspace=None, max_bytes=MAX_INSTRUCTIONS):
    root = (workspace or _workspace_root()).resolve()
    target = (root / (cwd or ".")).resolve()
    if target != root and root not in target.parents:
        raise ValueError("路径超出工作区")
    relative_parts = target.relative_to(root).parts
    directories = [root]
    for index in range(1, len(relative_parts) + 1):
        directories.append(root.joinpath(*relative_parts[:index]))
    loaded, paths, total = [], [], 0
    for directory in directories:
        filenames = ("AGENTS.override.md",) if (directory / "AGENTS.override.md").is_file() else ("AGENTS.md",)
        for filename in filenames:
            path = directory / filename
            if not path.is_file():
                continue
            resolved = path.resolve()
            if path.is_symlink() or (resolved != root and root not in resolved.parents):
                raise PermissionError("Workspace instructions must not follow external paths or symlinks")
            remaining = max_bytes - total
            if remaining <= 0:
                return {"content": "\n\n".join(loaded), "paths": paths, "truncated": True}
            text = path.read_text(encoding="utf-8")[:remaining]
            loaded.append(text)
            paths.append(str(path))
            total += len(text.encode("utf-8"))
    return {"content": "\n\n".join(loaded), "paths": paths, "truncated": total >= max_bytes}


def safe_path(value="."):
    root = _workspace_root()
    target = (root / value).resolve()
    if target != root and root not in target.parents:
        raise ValueError("路径超出工作区")
    return target


def project_tool_path(value, agent):
    """Resolve chat file tools inside the selected, tenant-owned project."""
    project_id = agent.get("_project_id")
    if not project_id:
        return safe_path(value), _workspace_root()
    relative = Path(str(value))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("项目文件路径必须是项目内的相对路径")
    if len(relative.parts) >= 2 and relative.parts[0] == "projects":
        if relative.parts[1] != project_id:
            raise PermissionError("不能访问其他项目的文件")
        relative = Path(*relative.parts[2:])
    root = project_root(project_id).resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise PermissionError("项目文件路径超出当前项目")
    return target, root


def project_sandbox_cwd(agent):
    if agent.get("_project_id"):
        return project_root(agent["_project_id"]).relative_to(tenant_workspace()).as_posix()
    return sandbox_cwd()


def project_file_state(agent, limit=3000):
    """Cheap bounded change detection for artifacts produced by shell tools."""
    if not (agent.get("_project_save") and agent.get("_project_id")):
        return {}
    root = project_root(agent["_project_id"])
    if not root.exists():
        return {}
    state = {}
    for directory, names, files in os.walk(root):
        names[:] = [name for name in names if name not in {".git", ".venv", "__pycache__", ".codezzn-backups"}]
        for name in files:
            path = Path(directory) / name
            if path.is_symlink():
                continue
            stat = path.stat()
            state[path.relative_to(root).as_posix()] = (stat.st_mtime_ns, stat.st_size)
            if len(state) >= limit:
                return state
    return state


def record_changed_project_files(agent, before, thread_id, turn_id):
    if not (agent.get("_project_save") and agent.get("_project_id")):
        return []
    root = project_root(agent["_project_id"])
    changed = []
    for relative, fingerprint in project_file_state(agent).items():
        if before.get(relative) != fingerprint:
            record_artifact(agent["_project_id"], thread_id, turn_id, root / relative, "file")
            changed.append(relative)
    return changed


def snapshot_file(target):
    backup_root = _workspace_root() / ".codezzn-backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / f"{new_id('file')}.bak"
    if target.exists():
        backup.write_bytes(target.read_bytes())
        return backup
    backup.write_text("", encoding="utf-8")
    return backup


def atomic_write(target, content, sandbox_root=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if sandbox_root is not None:
        shared = Path(sandbox_root).resolve()
        relative_parent = target.parent.resolve().relative_to(shared)
        current = shared
        for part in (None, *relative_parent.parts):
            if part is not None:
                current = current / part
            os.chown(current, -1, 10001)
            os.chmod(current, 0o770)
    snapshot = snapshot_file(target)
    fd, temp_name = tempfile.mkstemp(prefix=".codezzn-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            if sandbox_root is not None:
                # The app may run as root on Windows bind mounts while the
                # isolated executor always runs as 10001:10001. Share with
                # that group, never with every host user.
                os.fchown(handle.fileno(), -1, 10001)
                os.fchmod(handle.fileno(), 0o660)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return snapshot


async def build_context(agent, provider=None, model=None, user_message="", thread_id=None):
    instructions = load_instructions(agent.get("workspace_cwd"))
    sections = [agent.get("system_prompt", "You are a helpful assistant.")]
    sections.append("When a material user choice or missing requirement prevents responsible progress, use ask_user with a concise question and up to four distinct options. It pauses the task until the user chooses or types an answer. Do not ask for choices that the user already specified, and do not treat a project choice as permission to bypass tool approval.")
    sections.append("Projects and Workflows are durable assets, not just prose. For requests to create or change them, inspect existing assets first, use the project/workflow tools, and show the resulting asset ID. If an active_project is supplied, reuse it; never create a duplicate project for the same request. If there is no project decision and a real file must be written, use project_list and ask_user to choose an existing or new project, then call project_select or project_create; their approval is the binding project choice. Stage Workflow edits with workflow_draft_create or workflow_draft_update, explain the proposed changes, then call workflow_draft_save only after the user approves that exact save. A draft must not be described as a saved Workflow. Use workflow_run only when execution is requested; inspect workflow_run_get for progress and errors. Never call a write tool after the user declined saving for this turn.")
    template = role_template(agent.get("role_template"))
    sections.append(f"\n<role_template name={json.dumps(agent.get('role_template', 'general'))}>\n{template['instructions']}\n</role_template>")
    if agent.get("_project_save") is True and agent.get("_project_id"):
        sections.append(
            "\n<active_project>\n"
            f"project_id: {agent['_project_id']}\n"
            "The user explicitly approved saving artifacts to this project. "
            "For any requested code or local deliverable, create an actual file with write_file or apply_patch before your final answer; "
            "a code block in the answer is not a saved artifact. File-tool paths are relative to this project's root. "
            "Mention the exact saved filename and summarize what was written. "
            "Never put files into a different project. Existing tool approval policies still apply.\n"
            "</active_project>"
        )
    elif agent.get("_project_save") is False:
        sections.append(
            "\n<project_write_decision>\nThe user declined saving artifacts for this turn. "
            + (f"The selected project is {agent['_project_id']}; you may read its existing files. " if agent.get("_project_id") else "")
            + "Answer the request without writing or modifying files. Do not claim a file was saved.\n"
            "</project_write_decision>"
        )
    if instructions["content"]:
        sections.append("\n<workspace_instructions>\n" + instructions["content"] + "\n</workspace_instructions>")
    if provider and model:
        runtime = {
            "platform": "Codezzn",
            "agent": agent.get("name", "Codezzn Agent"),
            "provider": provider.get("name", provider.get("type", "unknown")),
            "provider_type": provider.get("type", "openai-compatible"),
            "model": model,
            "workspace": str(_workspace_root()),
            "instruction_paths": instructions["paths"],
            "instructions_truncated": instructions["truncated"],
        }
        sections.append(
            "\n<runtime_configuration>\n"
            + json.dumps(runtime, ensure_ascii=False, indent=2)
            + "\nThis is the authoritative configuration used for the current response. "
              "When asked which underlying/current/actual model you are using, answer directly with the exact provider and model above. "
              "Do not claim that the model is unknown and never reveal credentials.\n"
              "</runtime_configuration>"
        )
    for skill_id in agent.get("skill_ids", []):
        skill = resource_get("skills", skill_id)
        if skill and skill.get("enabled"):
            package = {
                "id": skill_id,
                "name": skill.get("name"),
                "version": skill.get("version"),
                "scripts": skill.get("scripts") or [],
                "references": skill.get("references") or [],
                "assets": skill.get("assets") or [],
            }
            sections.append(
                "\n<skill_package>\n"
                + json.dumps(package, ensure_ascii=False, indent=2)
                + "\nUse this exact id when calling skill_read_file or skill_run_script.\n"
                + str(skill.get("content", ""))[:20000]
                + "\n</skill_package>"
            )
    lsp_configs = []
    for server_id in agent.get("lsp_server_ids", []):
        server = resource_get("lsp_servers", server_id)
        if server and server.get("enabled", True):
            lsp_configs.append({"id": server_id, "name": server.get("name"), "language": server.get("language")})
    if lsp_configs:
        sections.append(
            "\n<available_lsp_servers>\n"
            + json.dumps(lsp_configs, ensure_ascii=False, indent=2)
            + "\nUse the matching exact id as lsp_request.server_id.\n</available_lsp_servers>"
        )
    if agent.get("memory_enabled") and user_message:
        context, _ = memory_context(
            user_message,
            str(agent.get("memory_project_id") or "default"),
            str(agent.get("memory_user_id") or "default"),
            thread_id,
        )
        if context:
            sections.append(f"\n<long_term_memory>\n{context}\n</long_term_memory>")
    return "\n".join(sections)


async def tool_specs(agent):
    specs, routes = [], {}
    domain_tools = ("project_list", "project_create", "project_select", "project_artifacts", "workflow_list", "workflow_get", "workflow_versions", "workflow_version_get",
                    "workflow_draft_create", "workflow_draft_update", "workflow_draft_save",
                    "workflow_draft_discard", "workflow_run", "workflow_run_get")
    builtin_names = list(dict.fromkeys(["ask_user", *domain_tools, *(agent.get("builtin_tools", []))]))
    if agent.get("memory_enabled"):
        builtin_names.extend(name for name in ("memory_search", "memory_save") if name not in builtin_names)
    if agent.get("subagent_ids"):
        builtin_names.extend(name for name in ("delegate_task", "task_status") if name not in builtin_names)
    for name in builtin_names:
        if name == "knowledge_search" and not agent.get("knowledge_ids"):
            continue
        if name in BUILTIN_SCHEMAS:
            specs.append({"type": "function", "function": {"name": name, **BUILTIN_SCHEMAS[name]}})
            routes[name] = ("builtin", None)
    for server_id in agent.get("mcp_server_ids", []):
        server = resource_get("mcp_servers", server_id)
        if not server or not server.get("enabled"):
            continue
        try:
            for tool in await mcp_manager.list_tools(server):
                public_name = f"mcp__{server_id[-6:]}__{tool['name']}"
                specs.append({"type": "function", "function": {
                    "name": public_name, "description": f"MCP {server['name']}: {tool.get('description', '')}",
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
                }})
                routes[public_name] = ("mcp", (server, tool["name"]))
            capabilities = (mcp_manager.initialized.get(server_id) or {}).get("capabilities") or {}
            if "resources" in capabilities:
                for suffix, description, parameters, route_kind in (
                    ("list_resources", f"列出 MCP {server['name']} 暴露的资源", {"type": "object", "properties": {}}, "mcp_resources_list"),
                    ("read_resource", f"读取 MCP {server['name']} 的资源", {"type": "object", "properties": {"uri": {"type": "string"}}, "required": ["uri"]}, "mcp_resource_read"),
                ):
                    public_name = f"mcp__{server_id[-6:]}__{suffix}"
                    specs.append({"type": "function", "function": {"name": public_name, "description": description, "parameters": parameters}})
                    routes[public_name] = (route_kind, server)
            if "prompts" in capabilities:
                for suffix, description, parameters, route_kind in (
                    ("list_prompts", f"列出 MCP {server['name']} 暴露的提示模板", {"type": "object", "properties": {}}, "mcp_prompts_list"),
                    ("get_prompt", f"获取 MCP {server['name']} 的提示模板", {"type": "object", "properties": {"name": {"type": "string"}, "arguments": {"type": "object"}}, "required": ["name"]}, "mcp_prompt_get"),
                ):
                    public_name = f"mcp__{server_id[-6:]}__{suffix}"
                    specs.append({"type": "function", "function": {"name": public_name, "description": description, "parameters": parameters}})
                    routes[public_name] = (route_kind, server)
        except Exception as exc:
            routes[f"__error_{server_id}"] = ("error", str(exc))
    return specs, routes


def approval_required(operation):
    return {"error": {"code": "approval_required", "operation": operation, "message": f"Approval required for {operation}"}}


def domain_result(operation, function, *args, **kwargs):
    """Return recoverable domain errors to the model instead of aborting a turn."""
    try:
        return function(*args, **kwargs)
    except (ValueError, PermissionError) as exc:
        return {"error": {"code": f"{operation}_failed", "message": str(exc)}}


def _git_command(args):
    return ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "diff.external=", "-c", "safe.directory=*", *args]


async def _run_git(args, mode="read-only"):
    if args[0] == "diff":
        args = ["diff", "--no-ext-diff", "--no-textconv", *args[1:]]
    command = _git_command(args)
    result = await run_command(shlex.join(command), mode, sandbox_cwd())
    return {**result, "command": command}


def _git_revision(value):
    if not isinstance(value, str) or value.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./~^@-]*", value):
        raise ValueError("Invalid Git revision; use a ref, commit, or revision range without options or special characters")
    return value


async def execute_tool(name, arguments, agent, routes, approved=False, thread_id=None, turn_id=None, depth=0, current_task_id=None):
    route = routes.get(name)
    if not route:
        raise ValueError(f"未知工具: {name}")
    if name == "ask_user":
        if not approved:
            return approval_required(name)
        return {"answer": str(agent.get("_user_answer") or "")[:4000]}
    if agent.get("_project_save") is False and name in {
        "write_file", "apply_patch", "git_branch", "git_stage", "git_commit", "restore_file",
        "git_clone", "git_fetch", "git_push", "git_merge", "git_merge_abort",
        "project_create", "project_select", "workflow_draft_create", "workflow_draft_update", "workflow_draft_save", "workflow_run",
    }:
        return {"error": {"code": "project_write_declined", "message": "用户已选择本次不保存或修改项目文件"}}
    if agent.get("_project_save") is False and name == "browser" and arguments.get("action") == "screenshot":
        return {"error": {"code": "project_write_declined", "message": "用户已选择本次不保存截图"}}
    mode = sandbox_mode(agent)
    if agent.get("_project_save") is False:
        mode = "read-only"
    auto_approve = agent.get("auto_approve") is True or approved
    policy = tool_policy_decision(agent, name)
    if policy == "deny":
        raise PermissionError(f"工具策略禁止调用 {name}")
    if policy == "allow":
        auto_approve = True
    elif policy == "ask" and not auto_approve:
        return approval_required(name)
    if route[0] == "mcp":
        if mode == "read-only" and not auto_approve:
            return approval_required("mcp")
        if not auto_approve:
            return approval_required("mcp")
        server, actual_name = route[1]
        return await mcp_manager.call_tool(server, actual_name, arguments)
    if route[0] == "mcp_resources_list":
        if not auto_approve and policy != "allow": return approval_required("mcp")
        return {"resources": await mcp_manager.list_resources(route[1])}
    if route[0] == "mcp_resource_read":
        if not auto_approve and policy != "allow": return approval_required("mcp")
        return await mcp_manager.read_resource(route[1], arguments["uri"])
    if route[0] == "mcp_prompts_list":
        return {"prompts": await mcp_manager.list_prompts(route[1])}
    if route[0] == "mcp_prompt_get":
        return await mcp_manager.get_prompt(route[1], arguments["name"], arguments.get("arguments"))
    if name == "project_list":
        return {"projects": list_project_tools()}
    if name == "project_artifacts":
        result = domain_result(name, list_project_artifacts_tool, arguments["project_id"])
        return result if "error" in result else {"artifacts": result}
    if name == "project_create":
        if mode == "read-only":
            raise PermissionError("只读智能体不能创建项目")
        if agent.get("_project_save") and agent.get("_project_id"):
            return {"error": {"code": "project_already_selected", "message": "本次任务已选择项目；请复用当前项目，不要重复创建"}}
        if not approved:
            return approval_required(name)
        project = domain_result(name, create_project_tool, arguments["name"], arguments.get("description", ""), thread_id=thread_id, turn_id=turn_id)
        if "error" in project:
            return project
        agent["_project_id"], agent["_project_save"] = project["id"], True
        agent["memory_project_id"] = project["id"]
        return project
    if name == "project_select":
        if mode == "read-only":
            raise PermissionError("只读智能体不能选择可写项目")
        if agent.get("_project_save") and agent.get("_project_id") and arguments.get("project_id") != agent["_project_id"]:
            return {"error": {"code": "project_scope_mismatch", "message": "本次任务已确认另一个项目，不能擅自切换"}}
        if not approved:
            return approval_required(name)
        project = domain_result(name, select_project_tool, arguments["project_id"], thread_id=thread_id, turn_id=turn_id)
        if "error" in project:
            return project
        agent["_project_id"], agent["_project_save"] = project["id"], True
        agent["memory_project_id"] = project["id"]
        return project
    if name == "workflow_list":
        return {"workflows": list_workflow_tools()}
    if name == "workflow_get":
        workflow = resource_get("workflows", arguments["workflow_id"])
        if not workflow:
            return {"error": {"code": "workflow_not_found", "message": "Workflow 不存在"}}
        return workflow
    if name == "workflow_versions":
        versions = list_workflow_versions(arguments["workflow_id"])
        return {"versions": versions} if versions is not None else {"error": {"code": "workflow_not_found", "message": "Workflow 不存在"}}
    if name == "workflow_version_get":
        version = get_workflow_version(arguments["workflow_id"], int(arguments["version"]))
        return version if version is not None else {"error": {"code": "workflow_version_not_found", "message": "Workflow 版本不存在"}}
    if name == "workflow_run_get":
        return domain_result(name, get_workflow_run, arguments["run_id"])
    if name in {"workflow_draft_create", "workflow_draft_update", "workflow_draft_save", "workflow_draft_discard", "workflow_run"}:
        if mode == "read-only":
            raise PermissionError("只读智能体不能修改或执行 Workflow")
        if name in {"workflow_draft_save", "workflow_run"} and not approved:
            return approval_required(name)
        if name == "workflow_draft_create":
            values = dict(arguments)
            if agent.get("_project_id") and values.get("project_id") not in (None, agent["_project_id"]):
                return {"error": {"code": "project_scope_mismatch", "message": "Workflow 草稿只能关联本次选择的项目"}}
            if not values.get("project_id"):
                values["project_id"] = agent.get("_project_id")
            return domain_result(name, create_workflow_draft, values, thread_id=thread_id, turn_id=turn_id)
        if name == "workflow_draft_update":
            draft = get_workflow_draft(arguments["draft_id"])
            if agent.get("_project_id") and draft and draft.get("project_id") != agent["_project_id"]:
                return {"error": {"code": "project_scope_mismatch", "message": "不能修改其他项目的 Workflow 草稿"}}
            return domain_result(name, update_workflow_draft, arguments["draft_id"], arguments)
        if name == "workflow_draft_save":
            draft = get_workflow_draft(arguments["draft_id"])
            if not draft or draft["thread_id"] != thread_id:
                return {"error": {"code": "workflow_draft_scope", "message": "只能保存当前对话创建的 Workflow 草稿"}}
            if agent.get("_project_id") and draft.get("project_id") != agent["_project_id"]:
                return {"error": {"code": "project_scope_mismatch", "message": "不能把 Workflow 保存到其他项目"}}
            return domain_result(name, save_workflow_draft, arguments["draft_id"], thread_id=thread_id, turn_id=turn_id)
        if name == "workflow_draft_discard":
            return domain_result(name, discard_workflow_draft, arguments["draft_id"])
        return domain_result(name, enqueue_workflow_run, arguments["workflow_id"], arguments.get("input", ""), thread_id=thread_id, turn_id=turn_id)
    if name == "knowledge_search":
        return await search(arguments["query"], agent.get("knowledge_ids", []), min(int(arguments.get("limit", 5)), 10))
    if name == "list_files":
        target, root = project_tool_path(arguments.get("path", "."), agent)
        return [{"name": p.name, "path": str(p.relative_to(root)), "directory": p.is_dir()} for p in list(target.iterdir())[:200]]
    if name == "read_file":
        target, _ = project_tool_path(arguments["path"], agent)
        return {"content": target.read_text(encoding="utf-8")[:100000]}
    if name == "search_code":
        path = str(safe_path(arguments.get("path", ".")).relative_to(_workspace_root())) or "."
        command = ["rg", "--line-number", "--hidden", "--glob", "!.git/**"]
        if arguments.get("glob"):
            command.extend(["--glob", str(arguments["glob"])])
        command.extend(["--", str(arguments["query"]), path])
        return await run_command(shlex.join(command), "read-only", sandbox_cwd())
    if name in ("write_file", "apply_patch"):
        if thread_id and turn_id and agent.get("_project_save") is None:
            return {"error": {"code": "project_choice_required", "message": "本次对话尚未确认项目；请先列出项目并让用户选择，再调用 project_select 或 project_create"}}
        if mode == "read-only":
            return approval_required(name)
        if not auto_approve:
            return approval_required(name)
    if name == "write_file":
        target, root = project_tool_path(arguments["path"], agent)
        if target == root:
            raise ValueError("必须提供文件名")
        backup = atomic_write(target, arguments["content"], sandbox_root=root if agent.get("_project_id") and agent.get("_project_save") else None)
        if agent.get("_project_id") and agent.get("_project_save"):
            record_artifact(agent["_project_id"], thread_id, turn_id, target, "file")
        return {"written": str(target.relative_to(root)), "project_id": agent.get("_project_id") if agent.get("_project_save") else None, "bytes": len(arguments["content"].encode()), "backup": str(backup.relative_to(_workspace_root()))}
    if name == "apply_patch":
        if "patch" in arguments:
            patch = str(arguments.get("patch") or "")
            paths = re.findall(r"^\+\+\+\s+(?:b/)?([^\t\r\n]+)", patch, re.MULTILINE)
            if not paths or any(path == "/dev/null" or ".." in Path(path).parts for path in paths):
                raise ValueError("补丁必须包含工作区内的安全目标路径")
            backups = []
            for path in paths:
                target, _ = project_tool_path(path, agent)
                backups.append(str(snapshot_file(target).relative_to(_workspace_root())))
            encoded = base64.b64encode(patch.encode()).decode()
            script = f"echo {shlex.quote(encoded)} | base64 -d > /tmp/codezzn.patch && git apply --check /tmp/codezzn.patch && git apply /tmp/codezzn.patch"
            result = await run_command(script, "workspace-write", project_sandbox_cwd(agent))
            if result.get("exit_code"):
                raise RuntimeError(result.get("stderr") or result.get("stdout") or "git apply failed")
            if agent.get("_project_id") and agent.get("_project_save"):
                for path in paths:
                    target, _ = project_tool_path(path, agent)
                    record_artifact(agent["_project_id"], thread_id, turn_id, target, "file")
            return {"changed": True, "paths": paths, "backups": backups, "result": result}
        target, root = project_tool_path(arguments["path"], agent)
        original = target.read_text(encoding="utf-8") if target.exists() else ""
        if "old" in arguments:
            old, new = arguments.get("old", ""), arguments.get("new", "")
            if original.count(old) != 1:
                raise ValueError("old replacement must match exactly once")
            updated = original.replace(old, new, 1)
        else:
            raise ValueError("Unified diff patches are not supported; use exact old/new replacements")
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = atomic_write(target, updated, sandbox_root=root if agent.get("_project_id") and agent.get("_project_save") else None)
        if agent.get("_project_id") and agent.get("_project_save"):
            record_artifact(agent["_project_id"], thread_id, turn_id, target, "file")
        return {"path": str(target.relative_to(root)), "project_id": agent.get("_project_id") if agent.get("_project_save") else None, "changed": original != updated, "backup": str(backup.relative_to(_workspace_root())), "diff": "".join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile=str(target), tofile=str(target)))}
    if name == "run_shell":
        if not agent.get("allow_shell", False):
            raise PermissionError("此智能体未启用 shell 权限")
        if mode == "danger-full-access":
            raise PermissionError("danger-full-access is not supported; use read-only or workspace-write")
        if not auto_approve:
            return approval_required(name)
        before = project_file_state(agent)
        result = await run_command(arguments["command"], mode, project_sandbox_cwd(agent))
        changed = record_changed_project_files(agent, before, thread_id, turn_id)
        return {**result, "project_artifacts": changed} if changed else result
    if name == "run_tests":
        if not agent.get("allow_shell", False):
            raise PermissionError("此智能体未启用 shell 权限")
        if not auto_approve:
            return approval_required(name)
        before = project_file_state(agent)
        result = await run_command(arguments["command"], mode, project_sandbox_cwd(agent))
        changed = record_changed_project_files(agent, before, thread_id, turn_id)
        return {**result, "project_artifacts": changed} if changed else result
    if name == "git_status":
        return await _run_git(["status", "--short"])
    if name == "git_diff":
        return await _run_git(["diff", *( ["--cached"] if arguments.get("staged") else [])])
    if name == "git_log":
        return await _run_git(["log", f"-n{min(int(arguments.get('limit', 10)), 50)}", "--oneline", "--decorate"])
    if name == "review":
        if arguments.get("range"):
            diff_args = ["diff", _git_revision(arguments["range"]), "--"]
        elif arguments.get("base"):
            diff_args = ["diff", f"{_git_revision(arguments['base'])}...HEAD", "--"]
        else:
            diff_args = ["diff", *( ["--cached"] if arguments.get("staged") else [])]
        diff = await _run_git(diff_args)
        return {"status": await _run_git(["status", "--short"]), "diff": diff, "findings": [], "schema_version": "1"}
    if name == "git_branch":
        if mode != "workspace-write" or not auto_approve:
            return approval_required(name)
        branch = _git_revision(arguments["name"])
        base = arguments.get("base")
        return await _run_git(["switch", "-c", branch, *([_git_revision(base)] if base else [])], "workspace-write")
    if name == "git_stage":
        if mode != "workspace-write" or not auto_approve:
            return approval_required(name)
        paths = arguments.get("paths") or []
        if not paths:
            raise ValueError("至少选择一个暂存路径")
        safe = []
        for value in paths[:100]:
            target = safe_path(str(value))
            safe.append(str(target.relative_to(_workspace_root())) or ".")
        return await _run_git(["add", "--", *safe], "workspace-write")
    if name == "git_commit":
        if mode != "workspace-write" or not auto_approve:
            return approval_required(name)
        message = str(arguments["message"]).strip()
        if not message or len(message) > 500:
            raise ValueError("提交说明不能为空且最多 500 字符")
        return await _run_git(["commit", "-m", message], "workspace-write")
    if name == "restore_file":
        if mode == "read-only" or not auto_approve:
            return approval_required(name)
        target = safe_path(arguments["path"])
        backup = safe_path(arguments["backup"])
        backup_root = (_workspace_root() / ".codezzn-backups").resolve()
        if backup_root not in backup.parents:
            raise ValueError("只能使用 Codezzn 自动备份")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(backup.read_bytes())
        return {"restored": str(target.relative_to(_workspace_root())), "backup": str(backup.relative_to(_workspace_root()))}
    if name == "memory_search":
        scopes = [("project", str(agent.get("memory_project_id") or "default")), ("user", str(agent.get("memory_user_id") or "default"))]
        if thread_id: scopes.append(("thread", thread_id))
        return {"memories": search_memories(arguments["query"], scopes, min(int(arguments.get("limit", 6)), 20))}
    if name == "memory_save":
        scope = arguments.get("scope", "project")
        scope_id = thread_id if scope == "thread" else str(agent.get("memory_user_id") or "default") if scope == "user" else str(agent.get("memory_project_id") or "default")
        return save_memory(scope, scope_id, arguments["content"], arguments.get("kind", "experience"), arguments.get("importance", 0.6), {"agent_id": agent.get("id"), "turn_id": turn_id})
    if name == "delegate_task":
        if depth >= int(agent.get("max_subagent_depth", 2)):
            raise RuntimeError("已达到最大子智能体深度")
        allowed = list(dict.fromkeys(agent.get("subagent_ids") or []))
        requested = arguments.get("tasks") or []
        if not allowed:
            raise RuntimeError("当前智能体没有配置可委派的子智能体")
        if len(requested) > int(agent.get("max_concurrent_subagents", 4)):
            raise ValueError("超过当前智能体允许的并行子任务数量")
        created = []
        for index, item in enumerate(requested):
            child_id = item.get("agent_id") or allowed[index % len(allowed)]
            if child_id not in allowed or not resource_get("agents", child_id):
                raise ValueError("选择了未授权的子智能体")
            run_id, timestamp = new_id("sub"), now()
            name_value = str(item.get("name") or f"子任务 {index + 1}")
            with connect() as db:
                db.execute("INSERT INTO subagent_runs(id,parent_task_id,parent_thread_id,parent_turn_id,agent_id,name,task,status,depth,created_at,updated_at) VALUES(?,?,?,?,?,?,?,'queued',?,?,?)", (run_id, current_task_id, thread_id, turn_id, child_id, name_value, str(item["task"]), depth + 1, timestamp, timestamp))
            queued = enqueue_task("subagent", name_value, {"subagent_run_id": run_id, "agent_id": child_id, "task": str(item["task"]), "thread_id": thread_id, "turn_id": turn_id, "depth": depth + 1}, parent_task_id=current_task_id)
            created.append({"subagent_run_id": run_id, "task_id": queued["id"], "agent_id": child_id, "name": name_value})
        return {"tasks": created}
    if name == "task_status":
        task_ids = list(dict.fromkeys(arguments.get("task_ids") or []))[:20]
        wait_seconds = min(max(int(arguments.get("wait_seconds", 0)), 0), 60)
        deadline = asyncio.get_running_loop().time() + wait_seconds
        while True:
            values = [get_task(task_id) for task_id in task_ids]
            if all(value and value["status"] in {"completed", "failed", "cancelled"} for value in values) or asyncio.get_running_loop().time() >= deadline:
                return {"tasks": values}
            await asyncio.sleep(0.35)
    if name == "code_index":
        return await asyncio.to_thread(rebuild_index, _workspace_root())
    if name == "code_symbols":
        return {"symbols": await asyncio.to_thread(code_symbols, _workspace_root(), arguments.get("query", ""), arguments.get("limit", 100))}
    if name == "find_references":
        return {"references": await asyncio.to_thread(code_references, _workspace_root(), str(arguments["symbol"]), arguments.get("limit", 200))}
    if name in ("call_graph", "dependency_graph"):
        return {"edges": await asyncio.to_thread(code_graph, _workspace_root(), "call" if name == "call_graph" else "import", arguments.get("symbol", ""), arguments.get("limit", 300))}
    if name == "lsp_request":
        server_id = str(arguments["server_id"])
        if server_id not in (agent.get("lsp_server_ids") or []): raise PermissionError("未授权的 LSP 服务")
        server = resource_get("lsp_servers", server_id)
        if not server or not server.get("enabled", True): raise ValueError("LSP 服务不存在或未启用")
        return {"result": await lsp_manager.request(server, _workspace_root(), str(arguments["method"]), arguments.get("params") or {})}
    if name == "git_clone":
        if mode != "workspace-write" or not auto_approve: return approval_required(name)
        url = str(arguments["url"]); target = safe_path(arguments["path"])
        if not re.match(r"^(https://|ssh://|git@)[^\s]+$", url): raise ValueError("仅支持 HTTPS/SSH Git URL")
        relative = target.relative_to(_workspace_root()).as_posix()
        args = ["clone", *( ["--branch", str(arguments["branch"])] if arguments.get("branch") else []), "--", url, relative]
        return await run_command(shlex.join(["git", *auth_header_command(), *args]), "workspace-write", sandbox_cwd(), network=True)
    if name in ("git_fetch", "git_push"):
        if mode != "workspace-write" or not auto_approve: return approval_required(name)
        remote = _git_revision(str(arguments.get("remote") or "origin"))
        if name == "git_fetch": args = ["fetch", *( ["--prune"] if arguments.get("prune", True) else []), remote]
        else:
            branch = _git_revision(str(arguments.get("branch") or "HEAD")); args = ["push", *( ["--set-upstream"] if arguments.get("set_upstream") else []), remote, branch]
        command = ["git", *auth_header_command(), "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "safe.directory=*", *args]
        result = await run_command(shlex.join(command), "workspace-write", sandbox_cwd(), network=True)
        return {key:value for key,value in result.items() if key != "command"}
    if name == "git_merge":
        if mode != "workspace-write" or not auto_approve: return approval_required(name)
        result = await _run_git(["merge", "--no-commit", "--no-ff", _git_revision(arguments["ref"])], "workspace-write")
        conflicts = await _run_git(["diff", "--name-only", "--diff-filter=U"])
        return {"merge":result,"conflicts":conflicts.get("output", "").splitlines(),"requires_resolution":bool(conflicts.get("output", "").strip())}
    if name == "git_merge_abort":
        if mode != "workspace-write" or not auto_approve: return approval_required(name)
        return await _run_git(["merge", "--abort"], "workspace-write")
    if name.startswith("github_"):
        if not auto_approve and name != "github_ci_status": return approval_required(name)
        remote_result = await _run_git(["remote", "get-url", "origin"]); remote = remote_result.get("output", "").strip()
        if name == "github_create_pr": return await create_pr(remote, arguments["title"], arguments["head"], arguments["base"], arguments.get("body", ""), arguments.get("draft", False))
        if name == "github_ci_status": return await ci_status(remote, arguments["ref"])
        return await review_comment(remote, arguments["pull_number"], arguments["body"], arguments["commit_id"], arguments["path"], arguments["line"], arguments.get("side", "RIGHT"))
    if name == "skill_read_file":
        skill = resource_get("skills", arguments["skill_id"])
        if not skill or arguments["skill_id"] not in (agent.get("skill_ids") or []): raise PermissionError("未授权的 Skill 包")
        return read_package_file(skill, arguments["path"])
    if name == "skill_run_script":
        if not auto_approve: return approval_required(name)
        skill = resource_get("skills", arguments["skill_id"])
        if not skill or arguments["skill_id"] not in (agent.get("skill_ids") or []): raise PermissionError("未授权的 Skill 包")
        verify_package(skill)
        relative = str(arguments["path"])
        if not relative.startswith("scripts/") or relative not in (skill.get("scripts") or []): raise PermissionError("只能执行 manifest 中的 scripts 文件")
        path = package_path(skill, relative); extension = path.suffix.lower()
        runner = {".py":"python", ".sh":"sh"}.get(extension)
        if not runner: raise ValueError("只允许执行 .py 或 .sh Skill 脚本")
        args = [str(value) for value in (arguments.get("args") or [])]
        package_relative = path.relative_to(tenant_workspace()).as_posix()
        return await run_command(shlex.join([runner, package_relative, *args]), mode, ".")
    if name == "browser":
        if not agent.get("allow_browser", False): raise PermissionError("当前智能体未启用浏览器能力")
        if not auto_approve and arguments.get("action") in {"click","mouse_click","mouse_move","scroll","hover","type","press","evaluate"}: return approval_required(name)
        values = dict(arguments); action = values.pop("action"); session = values.pop("session", thread_id or "default")
        if action == "screenshot" and agent.get("_project_save") and agent.get("_project_id"):
            root = project_root(agent["_project_id"])
            token = use_workspace(root)
            try:
                result = await browser_manager.execute(action, session, **values)
            finally:
                reset_workspace(token)
            record_artifact(agent["_project_id"], thread_id, turn_id, root / result["path"], "screenshot")
            return {**result, "project_id": agent["_project_id"]}
        return await browser_manager.execute(action, session, **values)
    raise ValueError(name)


SIDE_EFFECT_TOOLS = {
    "write_file", "apply_patch", "run_shell", "run_tests", "git_branch", "git_stage", "git_commit",
    "restore_file", "memory_save", "delegate_task", "git_clone", "git_fetch", "git_push", "git_merge",
    "git_merge_abort", "github_create_pr", "github_review_comment", "skill_run_script", "browser",
    "project_create", "project_select", "workflow_draft_create", "workflow_draft_update", "workflow_draft_save",
    "workflow_draft_discard", "workflow_run",
}


async def execute_tool_once(call_id, name, arguments, agent, routes, **kwargs):
    """Checkpoint tool results and avoid replaying ambiguous external side effects after a crash."""
    if not call_id:
        return await execute_tool(name, arguments, agent, routes, **kwargs)
    with connect() as db:
        row = db.execute("SELECT * FROM tool_executions WHERE call_id=?", (call_id,)).fetchone()
    if row and row["status"] == "completed":
        return json.loads(row["result"] or "null")
    if row and row["status"] in {"running", "failed"} and name in SIDE_EFFECT_TOOLS:
        return {"error": {"code": "interrupted_tool_execution", "message": "该副作用工具在进程中断前已开始，系统不会自动重放；请检查外部状态后重新发起。"}}
    timestamp = now()
    with connect() as db:
        db.execute("INSERT INTO tool_executions(call_id,turn_id,tool_name,arguments,status,created_at,updated_at) VALUES(?,?,?,?, 'running',?,?) ON CONFLICT(call_id) DO UPDATE SET status='running',error=NULL,updated_at=excluded.updated_at", (call_id, kwargs.get("turn_id"), name, json.dumps(arguments, ensure_ascii=False, default=str), timestamp, timestamp))
    try:
        result = await execute_tool(name, arguments, agent, routes, **kwargs)
        if isinstance(result, dict) and (result.get("error") or {}).get("code") == "approval_required":
            with connect() as db: db.execute("DELETE FROM tool_executions WHERE call_id=?", (call_id,))
            return result
        with connect() as db: db.execute("UPDATE tool_executions SET status='completed',result=?,updated_at=? WHERE call_id=?", (json.dumps(result, ensure_ascii=False, default=str), now(), call_id))
        return result
    except BaseException as exc:
        with connect() as db: db.execute("UPDATE tool_executions SET status='failed',error=?,updated_at=? WHERE call_id=?", (str(exc)[:4000], now(), call_id))
        raise


def _public_sources(sources):
    return [
        {"source": item.get("source"), "position": item.get("position"), "score": item.get("score"), "retrieval": item.get("retrieval")}
        for item in sources
    ]


def compact_chat_messages(messages, max_chars=120000, keep_recent=16):
    """Bound Chat Completions context without splitting recent tool-call exchanges."""
    max_chars = max(8000, int(max_chars or 120000))
    total = sum(len(str(item.get("content") or "")) + len(json.dumps(item.get("tool_calls") or [])) for item in messages)
    if total <= max_chars or len(messages) <= keep_recent + 1:
        return messages
    system = [messages[0]] if messages and messages[0].get("role") == "system" else []
    start = max(len(system), len(messages) - keep_recent)
    # Do not begin in the middle of an assistant tool-call + tool-output exchange.
    while start > len(system) and messages[start].get("role") == "tool":
        start -= 1
    older = messages[len(system):start]
    notes = []
    for item in older:
        if item.get("role") in {"user", "assistant"} and item.get("content"):
            text = re.sub(r"\s+", " ", str(item["content"])).strip()
            notes.append(f"{item['role']}: {text[:500]}")
    summary = {"role": "system", "content": "Earlier conversation was locally compacted. Salient transcript excerpts:\n" + "\n".join(notes[-20:])}
    result = [*system, summary, *messages[start:]]
    while sum(len(str(item.get("content") or "")) for item in result) > max_chars and len(result) > 4:
        del result[2]
    return result


def _save_checkpoint(thread_id, turn_id, agent_id, state):
    if not thread_id or not turn_id:
        return
    timestamp = now()
    with connect() as db:
        db.execute(
            "INSERT INTO turn_checkpoints(id,thread_id,turn_id,agent_id,status,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(turn_id) DO UPDATE SET agent_id=excluded.agent_id,status='waiting',state=excluded.state,updated_at=excluded.updated_at",
            (new_id("checkpoint"), thread_id, turn_id, agent_id, "waiting", json.dumps(state, ensure_ascii=False), timestamp, timestamp),
        )
        db.execute("UPDATE threads SET status='waiting_for_approval',updated_at=? WHERE id=?", (timestamp, thread_id))


def save_agent_run(agent, state, status="running", thread_id=None, turn_id=None, task_id=None, response_id=None, error=None):
    if not turn_id and not task_id:
        return None
    timestamp = now(); run_id = state.get("agent_run_id")
    with connect() as db:
        if not run_id:
            row = db.execute("SELECT id FROM agent_runs WHERE ((task_id IS NOT NULL AND task_id=?) OR (turn_id IS NOT NULL AND turn_id=?)) AND status IN ('running','waiting') ORDER BY created_at DESC LIMIT 1", (task_id, turn_id)).fetchone()
            run_id = row["id"] if row else new_id("arun"); state["agent_run_id"] = run_id
        db.execute("INSERT INTO agent_runs(id,task_id,thread_id,turn_id,agent_id,status,state,response_id,error,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,state=excluded.state,response_id=excluded.response_id,error=excluded.error,updated_at=excluded.updated_at", (run_id, task_id, thread_id, turn_id, agent["id"], status, json.dumps(state, ensure_ascii=False, default=str), response_id, error, timestamp, timestamp))
    return run_id


def load_agent_run(task_id=None, turn_id=None):
    with connect() as db:
        row = db.execute("SELECT * FROM agent_runs WHERE ((task_id IS NOT NULL AND task_id=?) OR (turn_id IS NOT NULL AND turn_id=?)) AND status IN ('running','waiting','recovering','failed') ORDER BY created_at DESC LIMIT 1", (task_id, turn_id)).fetchone()
    if not row: return None
    item = dict(row); item["state"] = json.loads(item["state"] or "{}"); return item


async def _run_responses_agent(agent, provider, selected_model, candidates, history, user_message, on_event, streaming, thread_id, turn_id, resume_state, approval_decision, depth, current_task_id):
    tools, routes = await tool_specs(agent); events, sources, total_usage = [], [], {}
    state = dict(resume_state or {})
    user_message = state.get("user_message") or user_message
    instructions = await build_context(agent, provider, selected_model, user_message, thread_id)
    previous_response_id = state.get("previous_response_id")
    pending = state.get("pending_tool_calls") or []
    next_input = state.get("next_input") or []
    round_number = int(state.get("round", 0))
    if not resume_state:
        await _emit(events, on_event, "turn_started", turn_id=turn_id)
        await _emit(events, on_event, "model_selected", provider=provider.get("name", provider.get("type", "unknown")), model=selected_model)
        if agent.get("knowledge_ids"):
            await _emit(events, on_event, "knowledge_started")
            try:
                sources = await search(user_message, agent.get("knowledge_ids"), limit=6)
                retrieval = format_retrieval_context(sources)
                if retrieval: instructions += "\n" + retrieval
                await _emit(events, on_event, "knowledge_completed", count=len(sources), sources=_public_sources(sources))
            except Exception as exc: await _emit(events, on_event, "knowledge_failed", reason=type(exc).__name__)
        if thread_id:
            with connect() as db: rows = db.execute("SELECT response_id,state FROM agent_runs WHERE thread_id=? AND agent_id=? AND status='completed' AND response_id IS NOT NULL ORDER BY updated_at DESC LIMIT 1", (thread_id, agent["id"])).fetchall()
            if rows:
                prior = json.loads(rows[0]["state"] or "{}");
                if prior.get("model") == selected_model and prior.get("provider_id") == provider.get("id"): previous_response_id = rows[0]["response_id"]
        if previous_response_id: next_input = [{"role":"user","content":user_message}]
        else: next_input = [{"role":item["role"],"content":item["content"]} for item in history if item["role"] in ("user","assistant")][-20:] + [{"role":"user","content":user_message}]
    else:
        events = state.get("events", []); sources = state.get("sources", []); total_usage = state.get("usage", {})
        await _emit(events, on_event, "turn_resumed", turn_id=turn_id)
    max_rounds = int(agent.get("max_tool_rounds", 8))
    state.update({"mode":"responses","previous_response_id":previous_response_id,"pending_tool_calls":pending,"next_input":next_input,"events":events,"sources":sources,"usage":total_usage,"round":round_number,"model":selected_model,"provider_id":provider.get("id"),"user_message":user_message})
    save_agent_run(agent, state, thread_id=thread_id, turn_id=turn_id, task_id=current_task_id, response_id=previous_response_id)
    runtime_index = 0
    while round_number <= max_rounds:
        if not pending:
            while True:
                try:
                    if streaming:
                        response, usage, response_id = {"content":"","tool_calls":[]}, {}, None
                        async for event in stream_response_completion(provider, selected_model, next_input, tools, instructions, previous_response_id, agent.get("reasoning_effort")):
                            if event["type"] == "assistant_delta": response["content"] += event["content"]; await _emit(events, on_event, "assistant_delta", content=event["content"])
                            elif event["type"] == "finish": response, usage, response_id = event["response"], event["usage"], event["response_id"]
                    else:
                        response, usage, response_id, _ = await response_completion(provider, selected_model, next_input, tools, instructions, previous_response_id, agent.get("reasoning_effort"))
                    break
                except ModelError as exc:
                    if runtime_index + 1 >= len(candidates): raise
                    runtime_index += 1; provider, selected_model = candidates[runtime_index]; previous_response_id = None
                    instructions = await build_context(agent, provider, selected_model, user_message, thread_id)
                    await _emit(events, on_event, "model_fallback", provider=provider.get("name", provider.get("type", "unknown")), model=selected_model, reason=str(exc)[:300])
            previous_response_id = response_id
            for key, value in usage.items():
                if isinstance(value, (int,float)): total_usage[key] = total_usage.get(key, 0) + value
            pending = list(response.get("tool_calls") or [])
            # previous_response_id already carries the model input and function calls;
            # the next request must contain only function_call_output items.
            next_input = []
            state = {"mode":"responses","previous_response_id":previous_response_id,"pending_tool_calls":pending,"next_input":[],"events":events,"sources":sources,"usage":total_usage,"round":round_number,"model":selected_model,"provider_id":provider.get("id"),"user_message":user_message}
            save_agent_run(agent, state, thread_id=thread_id, turn_id=turn_id, task_id=current_task_id, response_id=previous_response_id)
            if not pending:
                content = response.get("content") or ""
                if agent.get("memory_enabled") and agent.get("auto_memory") and content:
                    save_memory(
                        "project", str(agent.get("memory_project_id") or "default"),
                        f"任务：{user_message[:1000]}\n结果：{content[:2000]}", "experience", 0.55,
                        {"agent_id": agent.get("id"), "thread_id": thread_id, "turn_id": turn_id},
                    )
                await _emit(events, on_event, "assistant_status", status="completed"); await _emit(events, on_event, "turn_completed", usage=total_usage)
                save_agent_run(agent, state, "completed", thread_id, turn_id, current_task_id, previous_response_id)
                return {"status":"completed","content":content,"events":events,"usage":total_usage,"sources":_public_sources(sources),"runtime":{"provider":provider.get("name", provider.get("type","unknown")),"provider_type":provider.get("type","openai-compatible"),"model":selected_model,"api":"responses","response_id":previous_response_id}}

        async def invoke(call):
            name = call["function"]["name"]; arguments = json.loads(call["function"].get("arguments") or "{}")
            await _emit(events, on_event, "tool_started", name=name)
            approved = bool(approval_decision and approval_decision.get("tool_call_id") == call["id"] and approval_decision.get("decision") == "approved")
            denied = bool(approval_decision and approval_decision.get("tool_call_id") == call["id"] and approval_decision.get("decision") == "denied")
            tool_agent = {**agent, "_user_answer": approval_decision.get("reason", "")} if approved and name == "ask_user" else agent
            result = {"error":{"code":"approval_denied","message":approval_decision.get("reason") or "Approval denied"}} if denied else await execute_tool_once(call.get("id"), name, arguments, tool_agent, routes, approved=approved, thread_id=thread_id, turn_id=turn_id, depth=depth, current_task_id=current_task_id)
            return call, name, arguments, result
        completed = await asyncio.gather(*(invoke(call) for call in pending), return_exceptions=True) if agent.get("parallel_tools", True) and agent.get("auto_approve") else [await invoke(call) for call in pending]
        outputs = list(next_input)
        for index, item in enumerate(completed):
            if isinstance(item, Exception): raise item
            call, name, arguments, result = item
            if isinstance(result, dict) and (result.get("error") or {}).get("code") == "approval_required":
                if not thread_id or not turn_id: result = {"error":{"code":"approval_unavailable","message":"后台调用没有审批会话"}}
                else:
                    approval_id = new_id("approval")
                    with connect() as db: db.execute("INSERT INTO approvals(id,thread_id,turn_id,tool_name,arguments,status,created_at,tool_call_id,resumable) VALUES(?,?,?,?,?,'pending',?,?,1)", (approval_id,thread_id,turn_id,name,json.dumps(arguments,ensure_ascii=False),now(),call["id"]))
                    state.update({"pending_tool_calls":pending[index:],"next_input":outputs}); save_agent_run(agent,state,"waiting",thread_id,turn_id,current_task_id,previous_response_id); _save_checkpoint(thread_id,turn_id,agent["id"],state)
                    await _emit(events,on_event,"approval_required",name=name,status="pending",approval_id=approval_id,turn_id=turn_id)
                    return {"status":"waiting_for_approval","content":"","events":events,"usage":total_usage,"sources":_public_sources(sources),"approval_id":approval_id}
            outputs.append({"type":"function_call_output","call_id":call["id"],"output":json.dumps(result,ensure_ascii=False,default=str)[:100000]})
            await _emit(events,on_event,"tool_completed",name=name)
        pending = []; next_input = outputs; round_number += 1
        state.update({"pending_tool_calls":[],"next_input":next_input,"round":round_number,"events":events,"usage":total_usage}); save_agent_run(agent,state,thread_id=thread_id,turn_id=turn_id,task_id=current_task_id,response_id=previous_response_id)
    raise RuntimeError("达到最大工具调用轮次")


async def run_agent(agent, history, user_message, on_event=None, streaming=False, thread_id=None, turn_id=None, resume_state=None, approval_decision=None, depth=0, current_task_id=None):
    project_choice = get_turn_project(turn_id) if turn_id else None
    if project_choice is not None:
        agent = dict(agent)
        agent["_project_save"] = bool(project_choice["save_to_project"])
        agent["_project_id"] = project_choice.get("project_id")
        if agent["_project_id"]:
            agent["memory_project_id"] = agent["_project_id"]
    if agent.get("team_id"):
        team = resource_get("agent_teams", agent["team_id"])
        if team and team.get("enabled", True):
            agent = dict(agent)
            agent["subagent_ids"] = list(dict.fromkeys([*(agent.get("subagent_ids") or []), *(team.get("member_ids") or [])]))
            agent["max_concurrent_subagents"] = int(team.get("max_concurrency", agent.get("max_concurrent_subagents", 4)))
            agent["max_subagent_depth"] = int(team.get("max_depth", agent.get("max_subagent_depth", 2)))
    if agent.get("model_routes") or agent.get("fallback_models"):
        candidates = model_candidates(agent, user_message)
        if not candidates:
            raise ValueError("动态模型路由没有找到可用模型")
        provider, selected_model = candidates[0]
    else:
        provider = resource_get("providers", agent.get("provider_id"))
        if not provider:
            raise ValueError("智能体没有有效的模型提供方")
        selected_model = agent.get("model") or provider.get("default_model")
        candidates = [(provider, selected_model)]
    if uses_responses(provider) or (resume_state or {}).get("mode") == "responses":
        return await _run_responses_agent(agent, provider, selected_model, candidates, history, user_message, on_event, streaming, thread_id, turn_id, resume_state, approval_decision, depth, current_task_id)
    runtime_index = 0
    tools, routes = await tool_specs(agent)
    pending_tool_calls = None
    if resume_state:
        messages = resume_state["messages"]
        events = resume_state.get("events", [])
        sources = resume_state.get("sources", [])
        total_usage = resume_state.get("usage", {})
        round_number = int(resume_state.get("round", 0))
        pending_tool_calls = resume_state.get("pending_tool_calls") or []
        await _emit(events, on_event, "turn_resumed", turn_id=turn_id)
    else:
        messages = [{"role": "system", "content": await build_context(agent, provider, selected_model, user_message, thread_id)}]
        messages.extend({"role": item["role"], "content": item["content"]} for item in history if item["role"] in ("user", "assistant"))
        events, sources, total_usage, round_number = [], [], {}, 0
        await _emit(events, on_event, "turn_started", turn_id=turn_id)
        await _emit(events, on_event, "model_selected", provider=provider.get("name", provider.get("type", "unknown")), model=selected_model)
        if agent.get("knowledge_ids"):
            await _emit(events, on_event, "knowledge_started")
            try:
                sources = await search(user_message, agent.get("knowledge_ids"), limit=6)
                context = format_retrieval_context(sources)
                if context:
                    messages.append({"role": "system", "content": context})
                    await _emit(events, on_event, "knowledge_completed", count=len(sources), sources=_public_sources(sources))
            except Exception as exc:
                await _emit(events, on_event, "knowledge_failed", reason=type(exc).__name__)
        messages.append({"role": "user", "content": user_message})

    save_agent_run(agent, {"messages":messages,"pending_tool_calls":pending_tool_calls or [],"events":events,"usage":total_usage,"sources":sources,"round":round_number,"user_message":user_message,"model":selected_model,"provider_id":provider.get("id")}, thread_id=thread_id, turn_id=turn_id, task_id=current_task_id)

    max_rounds = int(agent.get("max_tool_rounds", 6))
    while round_number <= max_rounds:
        if pending_tool_calls is None:
            messages = compact_chat_messages(messages, agent.get("chat_context_chars", 120000), agent.get("chat_keep_recent", 16))
            if streaming:
                response, usage, content_parts = {"role": "assistant"}, {}, []
                while True:
                    emitted = False
                    try:
                        async for item in stream_chat_completion(provider, selected_model, messages, tools, agent.get("temperature", 0.2)):
                            if item["type"] == "assistant_delta":
                                emitted = True
                                content_parts.append(item["content"])
                                await _emit(events, on_event, "assistant_delta", content=item["content"])
                            elif item["type"] == "usage":
                                usage = item["usage"]
                            elif item["type"] == "finish":
                                response["tool_calls"] = item.get("tool_calls") or []
                        break
                    except ModelError as exc:
                        if emitted or runtime_index + 1 >= len(candidates):
                            raise
                        runtime_index += 1
                        provider, selected_model = candidates[runtime_index]
                        messages[0] = {"role": "system", "content": await build_context(agent, provider, selected_model, user_message, thread_id)}
                        await _emit(events, on_event, "model_fallback", provider=provider.get("name", provider.get("type", "unknown")), model=selected_model, reason=str(exc)[:300])
                response["content"] = "".join(content_parts)
            else:
                while True:
                    try:
                        response, usage = await chat_completion(provider, selected_model, messages, tools, agent.get("temperature", 0.2))
                        break
                    except ModelError as exc:
                        if runtime_index + 1 >= len(candidates):
                            raise
                        runtime_index += 1
                        provider, selected_model = candidates[runtime_index]
                        messages[0] = {"role": "system", "content": await build_context(agent, provider, selected_model, user_message, thread_id)}
                        await _emit(events, on_event, "model_fallback", provider=provider.get("name", provider.get("type", "unknown")), model=selected_model, reason=str(exc)[:300])
            total_usage = {key: total_usage.get(key, 0) + value for key, value in usage.items() if isinstance(value, (int, float))}
            # Keep the message history immutable while consuming tool calls below.
            # Reusing the same list and popping from it would mutate
            # response["tool_calls"] to [], which OpenAI-compatible providers such
            # as Bailian reject on the following completion request.
            pending_tool_calls = list(response.get("tool_calls") or [])
            if not pending_tool_calls:
                content = response.get("content") or ""
                if agent.get("memory_enabled") and agent.get("auto_memory") and content:
                    save_memory(
                        "project",
                        str(agent.get("memory_project_id") or "default"),
                        f"任务：{user_message[:1000]}\n结果：{content[:2000]}",
                        "experience",
                        0.55,
                        {"agent_id": agent.get("id"), "thread_id": thread_id, "turn_id": turn_id},
                    )
                await _emit(events, on_event, "assistant_status", status="completed")
                await _emit(events, on_event, "turn_completed", usage=total_usage)
                save_agent_run(agent, {"messages":messages,"pending_tool_calls":[],"events":events,"usage":total_usage,"sources":sources,"round":round_number,"user_message":user_message,"model":selected_model,"provider_id":provider.get("id")}, "completed", thread_id, turn_id, current_task_id)
                return {
                    "status": "completed", "content": content, "events": events, "usage": total_usage,
                    "sources": _public_sources(sources),
                    "runtime": {"provider": provider.get("name", provider.get("type", "unknown")), "provider_type": provider.get("type", "openai-compatible"), "model": selected_model},
                }
            messages.append(response)
            save_agent_run(agent, {"messages":messages,"pending_tool_calls":pending_tool_calls,"events":events,"usage":total_usage,"sources":sources,"round":round_number,"user_message":user_message,"model":selected_model,"provider_id":provider.get("id")}, thread_id=thread_id, turn_id=turn_id, task_id=current_task_id)

        while pending_tool_calls:
            call = pending_tool_calls[0]
            name = call["function"]["name"]
            arguments = json.loads(call["function"].get("arguments") or "{}")
            try:
                await _emit(events, on_event, "tool_started", name=name)
                approved = bool(approval_decision and approval_decision.get("tool_call_id") == call["id"] and approval_decision.get("decision") == "approved")
                denied = bool(approval_decision and approval_decision.get("tool_call_id") == call["id"] and approval_decision.get("decision") == "denied")
                if denied:
                    result = {"error": {"code": "approval_denied", "message": approval_decision.get("reason") or "Approval denied"}}
                    approval_decision = None
                    await _emit(events, on_event, "tool_failed", name=name, reason="approval_denied")
                else:
                    tool_agent = {**agent, "_user_answer": approval_decision.get("reason", "")} if approved and name == "ask_user" else agent
                    result = await execute_tool_once(call.get("id"), name, arguments, tool_agent, routes, approved=approved, thread_id=thread_id, turn_id=turn_id, depth=depth, current_task_id=current_task_id)
                    if approved:
                        approval_decision = None
                    if isinstance(result, dict) and isinstance(result.get("error"), dict) and result["error"].get("code") == "approval_required":
                        if not thread_id or not turn_id:
                            output = json.dumps(result, ensure_ascii=False, default=str)
                            messages.append({"role": "tool", "tool_call_id": call["id"], "content": output[:50000]})
                            pending_tool_calls.pop(0)
                            await _emit(events, on_event, "tool_failed", name=name, reason="approval_unavailable")
                            continue
                        approval_id = new_id("approval")
                        state = {"messages": messages, "pending_tool_calls": pending_tool_calls, "events": events, "usage": total_usage, "sources": sources, "round": round_number}
                        with connect() as db:
                            db.execute(
                                "INSERT INTO approvals(id,thread_id,turn_id,tool_name,arguments,status,created_at,tool_call_id,resumable) VALUES(?,?,?,?,?,'pending',?,?,1)",
                                (approval_id, thread_id, turn_id, name, json.dumps(arguments, ensure_ascii=False), now(), call["id"]),
                            )
                        _save_checkpoint(thread_id, turn_id, agent["id"], state)
                        save_agent_run(agent, state, "waiting", thread_id, turn_id, current_task_id)
                        await _emit(events, on_event, "approval_required", name=name, status="pending", approval_id=approval_id, turn_id=turn_id)
                        return {
                            "status": "waiting_for_approval", "content": response.get("content", "") if 'response' in locals() else "",
                            "events": events, "usage": total_usage, "sources": _public_sources(sources), "approval_id": approval_id,
                            "runtime": {"provider": provider.get("name", provider.get("type", "unknown")), "provider_type": provider.get("type", "openai-compatible"), "model": selected_model},
                        }
                    await _emit(events, on_event, "tool_completed", name=name, status="completed")
                output = json.dumps(result, ensure_ascii=False, default=str)
            except Exception as exc:
                output = json.dumps({"error": str(exc)}, ensure_ascii=False)
                await _emit(events, on_event, "tool_failed", name=name, reason=type(exc).__name__)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": output[:50000]})
            pending_tool_calls.pop(0)
            save_agent_run(agent, {"messages":messages,"pending_tool_calls":pending_tool_calls,"events":events,"usage":total_usage,"sources":sources,"round":round_number,"user_message":user_message,"model":selected_model,"provider_id":provider.get("id")}, thread_id=thread_id, turn_id=turn_id, task_id=current_task_id)
        pending_tool_calls = None
        round_number += 1
    raise RuntimeError("达到最大工具调用轮次")
