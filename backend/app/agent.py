import asyncio
import json
import os
import shlex
from pathlib import Path

from .db import resource_get
from .knowledge import format_retrieval_context, search
from .mcp import mcp_manager
from .model import chat_completion


WORKSPACE = Path(os.getenv("CODEZZN_WORKSPACE", os.path.join(os.getcwd(), "workspace"))).resolve()


BUILTIN_SCHEMAS = {
    "knowledge_search": {"description": "搜索已选择的知识库", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}},
    "list_files": {"description": "列出工作区文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
    "read_file": {"description": "读取工作区内的文本文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    "write_file": {"description": "写入工作区内的文本文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    "run_shell": {"description": "在工作区执行命令；仅在智能体允许 shell 时使用", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
}


def safe_path(value="."):
    target = (WORKSPACE / value).resolve()
    if target != WORKSPACE and WORKSPACE not in target.parents:
        raise ValueError("路径超出工作区")
    return target


async def build_context(agent, provider=None, model=None):
    sections = [agent.get("system_prompt", "You are a helpful assistant.")]
    if provider and model:
        runtime = {
            "platform": "Codezzn",
            "agent": agent.get("name", "Codezzn Agent"),
            "provider": provider.get("name", provider.get("type", "unknown")),
            "provider_type": provider.get("type", "openai-compatible"),
            "model": model,
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


async def execute_tool(name, arguments, agent, routes):
    route = routes.get(name)
    if not route:
        raise ValueError(f"未知工具: {name}")
    if route[0] == "mcp":
        server, actual_name = route[1]
        return await mcp_manager.call_tool(server, actual_name, arguments)
    if name == "knowledge_search":
        return await search(arguments["query"], agent.get("knowledge_ids", []), min(int(arguments.get("limit", 5)), 10))
    if name == "list_files":
        target = safe_path(arguments.get("path", "."))
        return [{"name": p.name, "path": str(p.relative_to(WORKSPACE)), "directory": p.is_dir()} for p in list(target.iterdir())[:200]]
    if name == "read_file":
        return {"content": safe_path(arguments["path"]).read_text(encoding="utf-8")[:100000]}
    if name == "write_file":
        target = safe_path(arguments["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(arguments["content"], encoding="utf-8")
        return {"written": str(target.relative_to(WORKSPACE)), "bytes": len(arguments["content"].encode())}
    if name == "run_shell":
        if not agent.get("allow_shell", False):
            raise PermissionError("此智能体未启用 shell 权限")
        process = await asyncio.create_subprocess_shell(
            arguments["command"], cwd=str(WORKSPACE), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=60)
        return {"exit_code": process.returncode, "output": stdout.decode(errors="replace")[-20000:]}
    raise ValueError(name)


async def run_agent(agent, history, user_message):
    provider = resource_get("providers", agent.get("provider_id"))
    if not provider:
        raise ValueError("智能体没有有效的模型提供方")
    selected_model = agent.get("model") or provider.get("default_model")
    messages = [{"role": "system", "content": await build_context(agent, provider, selected_model)}]
    messages.extend({"role": item["role"], "content": item["content"]} for item in history if item["role"] in ("user", "assistant"))
    events, sources = [], []
    if agent.get("knowledge_ids"):
        try:
            sources = await search(user_message, agent.get("knowledge_ids"), limit=6)
            context = format_retrieval_context(sources)
            if context:
                messages.append({"role": "system", "content": context})
                events.append({"type": "knowledge_retrieved", "count": len(sources), "sources": [
                    {"source": item.get("source"), "position": item.get("position"), "score": item.get("score"), "retrieval": item.get("retrieval")}
                    for item in sources
                ]})
        except Exception as exc:
            events.append({"type": "knowledge_failed", "error": str(exc)})
    messages.append({"role": "user", "content": user_message})
    tools, routes = await tool_specs(agent)
    total_usage = {}
    for round_number in range(int(agent.get("max_tool_rounds", 6)) + 1):
        response, usage = await chat_completion(provider, selected_model, messages, tools, agent.get("temperature", 0.2))
        total_usage = {key: total_usage.get(key, 0) + value for key, value in usage.items() if isinstance(value, (int, float))}
        tool_calls = response.get("tool_calls") or []
        if not tool_calls:
            content = response.get("content") or ""
            events.append({"type": "assistant", "content": content})
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
                events.append({"type": "tool_started", "name": name, "arguments": arguments})
                result = await execute_tool(name, arguments, agent, routes)
                output = json.dumps(result, ensure_ascii=False, default=str)
                events.append({"type": "tool_completed", "name": name, "result": result})
            except Exception as exc:
                output = json.dumps({"error": str(exc)}, ensure_ascii=False)
                events.append({"type": "tool_failed", "name": name, "error": str(exc)})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": output[:50000]})
    raise RuntimeError("达到最大工具调用轮次")
