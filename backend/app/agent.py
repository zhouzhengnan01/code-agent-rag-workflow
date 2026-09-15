import json
import os
import difflib
import shlex
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .db import connect, new_id, now, resource_get
from .knowledge import format_retrieval_context
from .knowledge_service import search
from .mcp import mcp_manager
from .model import chat_completion, stream_chat_completion
from .sandbox import run_command


WORKSPACE = Path(os.getenv("CODEZZN_WORKSPACE", os.path.join(os.getcwd(), "workspace"))).resolve()


BUILTIN_SCHEMAS = {
    "knowledge_search": {"description": "搜索已选择的知识库", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}},
    "list_files": {"description": "列出工作区文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
    "read_file": {"description": "读取工作区内的文本文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    "write_file": {"description": "写入工作区内的文本文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    "apply_patch": {"description": "Apply an exact old/new file replacement; unified diffs are not supported", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "patch": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["path"]}},
    "run_shell": {"description": "在工作区执行命令；仅在智能体允许 shell 时使用", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    "git_status": {"description": "读取工作区 Git 状态", "parameters": {"type": "object", "properties": {}}},
    "git_diff": {"description": "读取工作区未提交差异", "parameters": {"type": "object", "properties": {"staged": {"type": "boolean"}}}},
    "git_log": {"description": "读取最近 Git 提交记录", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    "review": {"description": "只读检查 Git 变更并返回结构化审查材料", "parameters": {"type": "object", "properties": {"staged": {"type": "boolean"}, "base": {"type": "string"}, "range": {"type": "string"}}}},
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


async def build_context(agent, provider=None, model=None):
    instructions = load_instructions(agent.get("workspace_cwd"))
    sections = [agent.get("system_prompt", "You are a helpful assistant.")]
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
    return "\n".join(sections)


async def tool_specs(agent):
    specs, routes = [], {}
    for name in agent.get("builtin_tools", []):
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
        except Exception as exc:
            routes[f"__error_{server_id}"] = ("error", str(exc))
    return specs, routes


def approval_required(operation):
    return {"error": {"code": "approval_required", "operation": operation, "message": f"Approval required for {operation}"}}


def _git_command(args):
    return ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "diff.external=", "-c", "safe.directory=/workspace", *args]


async def _run_git(args):
    if args[0] == "diff":
        args = ["diff", "--no-ext-diff", "--no-textconv", *args[1:]]
    command = _git_command(args)
    result = await run_command(shlex.join(command), "read-only")
    return {**result, "command": command}


def _git_revision(value):
    if not isinstance(value, str) or value.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./~^@-]*", value):
        raise ValueError("Invalid Git revision; use a ref, commit, or revision range without options or special characters")
    return value


async def execute_tool(name, arguments, agent, routes, approved=False):
    route = routes.get(name)
    if not route:
        raise ValueError(f"未知工具: {name}")
    mode = sandbox_mode(agent)
    auto_approve = agent.get("auto_approve") is True or approved
    if route[0] == "mcp":
        if mode == "read-only" and not auto_approve:
            return approval_required("mcp")
        if not auto_approve:
            return approval_required("mcp")
        server, actual_name = route[1]
        return await mcp_manager.call_tool(server, actual_name, arguments)
    if name == "knowledge_search":
        return await search(arguments["query"], agent.get("knowledge_ids", []), min(int(arguments.get("limit", 5)), 10))
    if name == "list_files":
        target = safe_path(arguments.get("path", "."))
        return [{"name": p.name, "path": str(p.relative_to(WORKSPACE)), "directory": p.is_dir()} for p in list(target.iterdir())[:200]]
    if name == "read_file":
        return {"content": safe_path(arguments["path"]).read_text(encoding="utf-8")[:100000]}
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
            raise ValueError("Unified diff patches are not supported; use exact old/new replacements")
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


async def run_agent(agent, history, user_message, on_event=None, streaming=False, thread_id=None, turn_id=None, resume_state=None, approval_decision=None):
    provider = resource_get("providers", agent.get("provider_id"))
    if not provider:
        raise ValueError("智能体没有有效的模型提供方")
    selected_model = agent.get("model") or provider.get("default_model")
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
        messages = [{"role": "system", "content": await build_context(agent, provider, selected_model)}]
        messages.extend({"role": item["role"], "content": item["content"]} for item in history if item["role"] in ("user", "assistant"))
        events, sources, total_usage, round_number = [], [], {}, 0
        await _emit(events, on_event, "turn_started", turn_id=turn_id)
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
                async for item in stream_chat_completion(provider, selected_model, messages, tools, agent.get("temperature", 0.2)):
                    if item["type"] == "assistant_delta":
                        content_parts.append(item["content"])
                        await _emit(events, on_event, "assistant_delta", content=item["content"])
                    elif item["type"] == "usage":
                        usage = item["usage"]
                    elif item["type"] == "finish":
                        response["tool_calls"] = item.get("tool_calls") or []
                response["content"] = "".join(content_parts)
            else:
                response, usage = await chat_completion(provider, selected_model, messages, tools, agent.get("temperature", 0.2))
            total_usage = {key: total_usage.get(key, 0) + value for key, value in usage.items() if isinstance(value, (int, float))}
            pending_tool_calls = response.get("tool_calls") or []
            if not pending_tool_calls:
                content = response.get("content") or ""
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
                    result = await execute_tool(name, arguments, agent, routes, approved=approved)
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
