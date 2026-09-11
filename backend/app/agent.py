import asyncio
import json
import os
import difflib
import shlex
from datetime import datetime, timezone
from pathlib import Path

from .db import new_id, resource_get
from .knowledge import format_retrieval_context, search
from .mcp import mcp_manager
from .model import chat_completion, stream_chat_completion


WORKSPACE = Path(os.getenv("CODEZZN_WORKSPACE", os.path.join(os.getcwd(), "workspace"))).resolve()


BUILTIN_SCHEMAS = {
    "knowledge_search": {"description": "搜索已选择的知识库", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}},
    "list_files": {"description": "列出工作区文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
    "read_file": {"description": "读取工作区内的文本文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    "write_file": {"description": "写入工作区内的文本文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    "apply_patch": {"description": "应用 unified diff 或精确 old/new 文件替换", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "patch": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["path"]}},
    "run_shell": {"description": "在工作区执行命令；仅在智能体允许 shell 时使用", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    "git_status": {"description": "读取工作区 Git 状态", "parameters": {"type": "object", "properties": {}}},
    "git_diff": {"description": "读取工作区未提交差异", "parameters": {"type": "object", "properties": {"staged": {"type": "boolean"}}}},
    "git_log": {"description": "读取最近 Git 提交记录", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    "review": {"description": "只读检查未提交差异并返回审查材料", "parameters": {"type": "object", "properties": {"staged": {"type": "boolean"}}}},
}

MAX_OUTPUT = 20000
MAX_INSTRUCTIONS = 50000
MAX_COMMAND_TIMEOUT = 60


def _event(event_type, **data):
    allowed = {"count", "name", "status", "content", "usage", "sources", "reason", "provider", "model", "round"}
    return {"id": new_id("evt"), "timestamp": datetime.now(timezone.utc).isoformat(), "type": event_type,
            **{key: value for key, value in data.items() if key in allowed}}


async def _emit(events, callback, event_type, **data):
    event = _event(event_type, **data)
    events.append(event)
    if callback:
        await callback(event)


def load_instructions(cwd=None, workspace=None, max_bytes=MAX_INSTRUCTIONS):
    root = (workspace or WORKSPACE).resolve()
    target = (root / (cwd or ".")).resolve()
    if target != root and root not in target.parents:
        raise ValueError("路径超出工作区")
    directories = list(reversed([root, *target.relative_to(root).parents])) if target != root else [root]
    directories = list(dict.fromkeys(directories + [target]))
    loaded, paths, total = [], [], 0
    for directory in directories:
        for filename in ("AGENTS.md", "AGENTS.override.md"):
            path = directory / filename
            if not path.is_file():
                continue
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
    return ["git", *args]


async def _run_git(args):
    process = await asyncio.create_subprocess_exec(*_git_command(args), cwd=str(WORKSPACE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=MAX_COMMAND_TIMEOUT)
    except asyncio.TimeoutError:
        process.kill()
        raise TimeoutError("Git command timed out")
    return {"command": _git_command(args), "exit_code": process.returncode, "output": stdout.decode(errors="replace")[-MAX_OUTPUT:]}


async def execute_tool(name, arguments, agent, routes):
    route = routes.get(name)
    if not route:
        raise ValueError(f"未知工具: {name}")
    auto_approve = agent.get("auto_approve") is True
    if route[0] == "mcp":
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
    if name in ("write_file", "apply_patch") and not auto_approve:
        return approval_required(name)
    if name == "write_file":
        target = safe_path(arguments["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(arguments["content"], encoding="utf-8")
        return {"written": str(target.relative_to(WORKSPACE)), "bytes": len(arguments["content"].encode())}
    if name == "apply_patch":
        target = safe_path(arguments["path"])
        original = target.read_text(encoding="utf-8") if target.exists() else ""
        if "old" in arguments:
            old, new = arguments.get("old", ""), arguments.get("new", "")
            if original.count(old) != 1:
                raise ValueError("old replacement must match exactly once")
            updated = original.replace(old, new, 1)
        else:
            patch = arguments.get("patch")
            if not patch:
                raise ValueError("patch or old/new is required")
            import tempfile
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
                handle.write(original)
                source = handle.name
            try:
                result = await asyncio.create_subprocess_exec("patch", "--batch", "--forward", source, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
                output, _ = await asyncio.wait_for(result.communicate(patch.encode()), timeout=MAX_COMMAND_TIMEOUT)
                if result.returncode != 0:
                    raise ValueError(output.decode(errors="replace")[-MAX_OUTPUT:])
                updated = Path(source).read_text(encoding="utf-8")
            finally:
                Path(source).unlink(missing_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(updated, encoding="utf-8")
        return {"path": str(target.relative_to(WORKSPACE)), "changed": original != updated, "diff": "".join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile=str(target), tofile=str(target)))}
    if name == "run_shell":
        if not agent.get("allow_shell", False):
            raise PermissionError("此智能体未启用 shell 权限")
        if not auto_approve:
            return approval_required(name)
        process = await asyncio.create_subprocess_shell(arguments["command"], cwd=str(WORKSPACE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=MAX_COMMAND_TIMEOUT)
        return {"exit_code": process.returncode, "output": stdout.decode(errors="replace")[-MAX_OUTPUT:]}
    if name == "git_status":
        return await _run_git(["status", "--short"])
    if name == "git_diff":
        return await _run_git(["diff", *( ["--cached"] if arguments.get("staged") else [])])
    if name == "git_log":
        return await _run_git(["log", f"-n{min(int(arguments.get('limit', 10)), 50)}", "--oneline", "--decorate"])
    if name == "review":
        return {"status": await _run_git(["status", "--short"]), "diff": await _run_git(["diff", *( ["--cached"] if arguments.get("staged") else [])])}
    raise ValueError(name)


async def run_agent(agent, history, user_message, on_event=None, streaming=False):
    provider = resource_get("providers", agent.get("provider_id"))
    if not provider:
        raise ValueError("智能体没有有效的模型提供方")
    selected_model = agent.get("model") or provider.get("default_model")
    messages = [{"role": "system", "content": await build_context(agent, provider, selected_model)}]
    messages.extend({"role": item["role"], "content": item["content"]} for item in history if item["role"] in ("user", "assistant"))
    events, sources = [], []
    await _emit(events, on_event, "turn_started")
    if agent.get("knowledge_ids"):
        await _emit(events, on_event, "knowledge_started")
        try:
            sources = await search(user_message, agent.get("knowledge_ids"), limit=6)
            context = format_retrieval_context(sources)
            if context:
                messages.append({"role": "system", "content": context})
                await _emit(events, on_event, "knowledge_completed", count=len(sources), sources=[
                    {"source": item.get("source"), "position": item.get("position"), "score": item.get("score"), "retrieval": item.get("retrieval")}
                    for item in sources
                ])
        except Exception as exc:
            await _emit(events, on_event, "knowledge_failed", reason=type(exc).__name__)
    messages.append({"role": "user", "content": user_message})
    tools, routes = await tool_specs(agent)
    total_usage = {}
    for round_number in range(int(agent.get("max_tool_rounds", 6)) + 1):
        if streaming:
            response, usage, content_parts, call_map = {"role": "assistant"}, {}, [], {}
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
        tool_calls = response.get("tool_calls") or []
        if not tool_calls:
            content = response.get("content") or ""
            await _emit(events, on_event, "assistant_status", status="completed")
            await _emit(events, on_event, "turn_completed", usage=total_usage)
            return {
                "content": content,
                "events": events,
                "usage": total_usage,
                "sources": [
                    {"source": item.get("source"), "position": item.get("position"), "score": item.get("score"), "retrieval": item.get("retrieval")}
                    for item in sources
                ],
                "runtime": {
                    "provider": provider.get("name", provider.get("type", "unknown")),
                    "provider_type": provider.get("type", "openai-compatible"),
                    "model": selected_model,
                },
            }
        messages.append(response)
        for call in tool_calls:
            name = call["function"]["name"]
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
                await _emit(events, on_event, "tool_started", name=name)
                result = await execute_tool(name, arguments, agent, routes)
                output = json.dumps(result, ensure_ascii=False, default=str)
                await _emit(events, on_event, "tool_completed", name=name, status="completed")
            except Exception as exc:
                output = json.dumps({"error": str(exc)}, ensure_ascii=False)
                await _emit(events, on_event, "tool_failed", name=name, reason=type(exc).__name__)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": output[:50000]})
    raise RuntimeError("达到最大工具调用轮次")
