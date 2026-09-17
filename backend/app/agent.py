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
from .model import ModelError, chat_completion, stream_chat_completion
from .sandbox import run_command
from .tasks import enqueue_task, get_task


WORKSPACE = Path(os.getenv("CODEZZN_WORKSPACE", os.path.join(os.getcwd(), "workspace"))).resolve()


BUILTIN_SCHEMAS = {
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
    root = (workspace or WORKSPACE).resolve()
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
    target = (WORKSPACE / value).resolve()
    if target != WORKSPACE and WORKSPACE not in target.parents:
        raise ValueError("路径超出工作区")
    return target


def snapshot_file(target):
    backup_root = WORKSPACE / ".codezzn-backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / f"{new_id('file')}.bak"
    if target.exists():
        backup.write_bytes(target.read_bytes())
        return backup
    backup.write_text("", encoding="utf-8")
    return backup


def atomic_write(target, content):
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_file(target)
    fd, temp_name = tempfile.mkstemp(prefix=".codezzn-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
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
    template = role_template(agent.get("role_template"))
    sections.append(f"\n<role_template name={json.dumps(agent.get('role_template', 'general'))}>\n{template['instructions']}\n</role_template>")
    if instructions["content"]:
        sections.append("\n<workspace_instructions>\n" + instructions["content"] + "\n</workspace_instructions>")
    if provider and model:
        runtime = {
            "platform": "Codezzn",
            "agent": agent.get("name", "Codezzn Agent"),
            "provider": provider.get("name", provider.get("type", "unknown")),
            "provider_type": provider.get("type", "openai-compatible"),
            "model": model,
            "workspace": str(WORKSPACE),
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
            sections.append(f"\n<skill name={json.dumps(skill['name'], ensure_ascii=False)}>\n{skill.get('content', '')[:20000]}\n</skill>")
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
    builtin_names = list(dict.fromkeys(agent.get("builtin_tools", [])))
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


def _git_command(args):
    return ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "diff.external=", "-c", "safe.directory=/workspace", *args]


async def _run_git(args, mode="read-only"):
    if args[0] == "diff":
        args = ["diff", "--no-ext-diff", "--no-textconv", *args[1:]]
    command = _git_command(args)
    result = await run_command(shlex.join(command), mode)
    return {**result, "command": command}


def _git_revision(value):
    if not isinstance(value, str) or value.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./~^@-]*", value):
        raise ValueError("Invalid Git revision; use a ref, commit, or revision range without options or special characters")
    return value


async def execute_tool(name, arguments, agent, routes, approved=False, thread_id=None, turn_id=None, depth=0, current_task_id=None):
    route = routes.get(name)
    if not route:
        raise ValueError(f"未知工具: {name}")
    mode = sandbox_mode(agent)
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
    if name == "knowledge_search":
        return await search(arguments["query"], agent.get("knowledge_ids", []), min(int(arguments.get("limit", 5)), 10))
    if name == "list_files":
        target = safe_path(arguments.get("path", "."))
        return [{"name": p.name, "path": str(p.relative_to(WORKSPACE)), "directory": p.is_dir()} for p in list(target.iterdir())[:200]]
    if name == "read_file":
        return {"content": safe_path(arguments["path"]).read_text(encoding="utf-8")[:100000]}
    if name == "search_code":
        path = str(safe_path(arguments.get("path", ".")).relative_to(WORKSPACE)) or "."
        command = ["rg", "--line-number", "--hidden", "--glob", "!.git/**"]
        if arguments.get("glob"):
            command.extend(["--glob", str(arguments["glob"])])
        command.extend(["--", str(arguments["query"]), path])
        return await run_command(shlex.join(command), "read-only")
    if name in ("write_file", "apply_patch"):
        if mode == "read-only":
            return approval_required(name)
        if not auto_approve:
            return approval_required(name)
    if name == "write_file":
        target = safe_path(arguments["path"])
        backup = atomic_write(target, arguments["content"])
        return {"written": str(target.relative_to(WORKSPACE)), "bytes": len(arguments["content"].encode()), "backup": str(backup.relative_to(WORKSPACE))}
    if name == "apply_patch":
        if "patch" in arguments:
            patch = str(arguments.get("patch") or "")
            paths = re.findall(r"^\+\+\+\s+(?:b/)?([^\t\r\n]+)", patch, re.MULTILINE)
            if not paths or any(path == "/dev/null" or ".." in Path(path).parts for path in paths):
                raise ValueError("补丁必须包含工作区内的安全目标路径")
            backups = []
            for path in paths:
                target = safe_path(path)
                backups.append(str(snapshot_file(target).relative_to(WORKSPACE)))
            encoded = base64.b64encode(patch.encode()).decode()
            script = f"echo {shlex.quote(encoded)} | base64 -d > /tmp/codezzn.patch && git apply --check /tmp/codezzn.patch && git apply /tmp/codezzn.patch"
            result = await run_command(script, "workspace-write")
            if result.get("exit_code"):
                raise RuntimeError(result.get("stderr") or result.get("stdout") or "git apply failed")
            return {"changed": True, "paths": paths, "backups": backups, "result": result}
        target = safe_path(arguments["path"])
        original = target.read_text(encoding="utf-8") if target.exists() else ""
        if "old" in arguments:
            old, new = arguments.get("old", ""), arguments.get("new", "")
            if original.count(old) != 1:
                raise ValueError("old replacement must match exactly once")
            updated = original.replace(old, new, 1)
        else:
            raise ValueError("Unified diff patches are not supported; use exact old/new replacements")
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = atomic_write(target, updated)
        return {"path": str(target.relative_to(WORKSPACE)), "changed": original != updated, "backup": str(backup.relative_to(WORKSPACE)), "diff": "".join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile=str(target), tofile=str(target)))}
    if name == "run_shell":
        if not agent.get("allow_shell", False):
            raise PermissionError("此智能体未启用 shell 权限")
        if mode == "danger-full-access":
            raise PermissionError("danger-full-access is not supported; use read-only or workspace-write")
        if not auto_approve:
            return approval_required(name)
        return await run_command(arguments["command"], mode)
    if name == "run_tests":
        if not agent.get("allow_shell", False):
            raise PermissionError("此智能体未启用 shell 权限")
        if not auto_approve:
            return approval_required(name)
        return await run_command(arguments["command"], mode)
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
            safe.append(str(target.relative_to(WORKSPACE)) or ".")
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
        backup_root = (WORKSPACE / ".codezzn-backups").resolve()
        if backup_root not in backup.parents:
            raise ValueError("只能使用 Codezzn 自动备份")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(backup.read_bytes())
        return {"restored": str(target.relative_to(WORKSPACE)), "backup": str(backup.relative_to(WORKSPACE))}
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
    raise ValueError(name)


def _public_sources(sources):
    return [
        {"source": item.get("source"), "position": item.get("position"), "score": item.get("score"), "retrieval": item.get("retrieval")}
        for item in sources
    ]


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


async def run_agent(agent, history, user_message, on_event=None, streaming=False, thread_id=None, turn_id=None, resume_state=None, approval_decision=None, depth=0, current_task_id=None):
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

    max_rounds = int(agent.get("max_tool_rounds", 6))
    while round_number <= max_rounds:
        if pending_tool_calls is None:
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
                return {
                    "status": "completed", "content": content, "events": events, "usage": total_usage,
                    "sources": _public_sources(sources),
                    "runtime": {"provider": provider.get("name", provider.get("type", "unknown")), "provider_type": provider.get("type", "openai-compatible"), "model": selected_model},
                }
            messages.append(response)

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
                    result = await execute_tool(name, arguments, agent, routes, approved=approved, thread_id=thread_id, turn_id=turn_id, depth=depth, current_task_id=current_task_id)
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
        pending_tool_calls = None
        round_number += 1
    raise RuntimeError("达到最大工具调用轮次")
