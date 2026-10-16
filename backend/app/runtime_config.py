"""Tenant-local conversational defaults, layered settings and lazy Skill discovery.

This is application configuration, not permission granted by model-generated text.
Existing custom agents remain opt-in profiles with their original security limits.
"""
import re

from fastapi import HTTPException

from .db import resource_get, resource_list, resource_save

DEFAULT_AGENT_ID = "agt_codezzn_default"
PERMISSION_MODES = {"default", "acceptEdits", "plan"}
SETTING_KEYS = {"provider_id", "model", "permission_mode", "skill_discovery", "disabled_skill_ids"}
EDIT_TOOLS = {"write_file", "apply_patch"}


def ensure_default_agent():
    existing = resource_get("agents", DEFAULT_AGENT_ID)
    if existing:
        return existing
    providers = [p for p in resource_list("providers") if p.get("enabled", True)]
    provider = next((p for p in providers if p.get("api_key")), providers[0] if providers else {})
    return resource_save("agents", {
        "name": "Codezzn", "description": "直接聊天，按需调用工具与技能，无需先组装智能体",
        "managed_default": True, "role_template": "coding",
        "provider_id": provider.get("id"), "model": provider.get("default_model"),
        "system_prompt": "你是 Codezzn，用户可以直接与你聊天或提出任务。按目标选择工具；读取和检索可直接执行，写入和命令由运行时按策略审批。技能按描述匹配，先读取 SKILL.md 再使用。不要要求用户先配置智能体或勾选技能。",
        "builtin_tools": ["list_files", "read_file", "search_code", "write_file", "apply_patch", "run_shell", "skill_read_file", "skill_run_script"],
        "skill_ids": [], "mcp_server_ids": [], "knowledge_ids": [],
        "skill_discovery": "auto", "lazy_skills": True, "permission_mode": "default",
        "sandbox_mode": "workspace-write", "allow_shell": True, "allow_browser": False,
        "auto_approve": False, "max_tool_rounds": 30, "temperature": 0.2,
    }, DEFAULT_AGENT_ID)


def validate_settings(value):
    if not isinstance(value, dict) or set(value) - SETTING_KEYS:
        raise HTTPException(400, "运行配置包含不支持的字段")
    if "permission_mode" in value and (not isinstance(value["permission_mode"], str) or value["permission_mode"] not in PERMISSION_MODES):
        raise HTTPException(400, "权限模式必须为 default、acceptEdits 或 plan")
    if "skill_discovery" in value and (not isinstance(value["skill_discovery"], str) or value["skill_discovery"] not in {"auto", "off"}):
        raise HTTPException(400, "skill_discovery 必须为 auto 或 off")
    if "disabled_skill_ids" in value:
        ids = value["disabled_skill_ids"]
        if not isinstance(ids, list) or len(ids) > 100 or any(not isinstance(i, str) for i in ids):
            raise HTTPException(400, "disabled_skill_ids 必须为最多 100 个 ID 的数组")
        if any(not resource_get("skills", i) for i in ids):
            raise HTTPException(400, "Skill 不存在")
    if "provider_id" in value:
        if not isinstance(value['provider_id'], str):
            raise HTTPException(400, '模型提供方 ID 无效')
        provider = resource_get("providers", value["provider_id"])
        if not provider or not provider.get("enabled", True):
            raise HTTPException(400, "模型提供方不可用")
    if "model" in value and (not isinstance(value["model"], str) or not 1 <= len(value["model"]) <= 200):
        raise HTTPException(400, "模型名称无效")
    return dict(value)


def settings(scope="user", project_id=None):
    key = "user" if scope == "user" else "project_" + str(project_id)
    return {k: v for k, v in (resource_get("runtime_settings", key) or {}).items() if k in SETTING_KEYS}


def save_settings(value, project_id=None):
    if project_id:
        from .projects import get_project
        try:
            project = get_project(project_id)
        except ValueError:
            project = None
        if not project:
            raise HTTPException(404, "项目不存在")
    value = validate_settings(value)
    key = "project_" + project_id if project_id else "user"
    resource_save("runtime_settings", {"name": key, **value}, key)
    return settings("project" if project_id else "user", project_id)


def resolve_settings(agent, overrides=None):
    result = dict(agent)
    overrides = overrides if overrides is not None else agent.get('_runtime_overrides', {})
    # Do not silently migrate or broaden an existing custom agent.
    if agent.get("id") == DEFAULT_AGENT_ID:
        base = agent.get('_runtime_base') or {k: v for k, v in agent.items() if k in SETTING_KEYS}
        for key in SETTING_KEYS:
            result.pop(key, None)
        result.update(base)
        result['_runtime_base'] = base
        result['_runtime_overrides'] = dict(overrides or {})
        result['_runtime_sandbox_mode'] = agent.get('_runtime_sandbox_mode', agent.get('sandbox_mode', 'read-only'))
        result['sandbox_mode'] = result['_runtime_sandbox_mode']
        result.update(settings())
        if agent.get("_project_id"):
            result.update(settings("project", agent["_project_id"]))
        provider = resource_get("providers", result.get("provider_id"))
        if not provider or not provider.get("enabled", True):
            providers = [p for p in resource_list("providers") if p.get("enabled", True)]
            provider = next((p for p in providers if p.get("api_key")), providers[0] if providers else {})
            result.update(provider_id=provider.get("id"), model=provider.get("default_model"))
    for key in ("permission_mode", "skill_discovery"):
        if key in (overrides or {}):
            result[key] = overrides[key]
    if result.get('permission_mode') == 'plan':
        result['sandbox_mode'] = 'read-only'
    return result


def _flags(skill):
    # Only a bounded frontmatter block is configuration, never the Markdown body.
    content = str(skill.get("content") or "").replace("\r\n", "\n")
    meta = {}
    if content.startswith("---\n"):
        for line in content.split("---\n", 2)[1][:8000].splitlines():
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip()] = value.strip().strip("\"'")
    def flag(key, default):
        value = skill.get(key, meta.get(key, default))
        return value is True or str(value).lower() == "true"
    name = str(skill.get("command") or meta.get("name") or skill.get("name") or "")
    command = name if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name) else skill["id"]
    return command, flag("disable-model-invocation", False), flag("user-invocable", True)


def available_skills(agent):
    disabled = agent.get("disabled_skill_ids") or []
    selected = agent.get("skill_ids") or []
    result = []
    for skill in resource_list("skills"):
        if not skill.get("enabled", True) or skill["id"] in disabled:
            continue
        project_id = skill.get("project_id")
        if project_id and project_id != agent.get("_project_id"):
            continue
        if agent.get("skill_discovery") != "auto" and skill["id"] not in selected:
            continue
        command, manual_only, user_invocable = _flags(skill)
        result.append({**skill, "command": command, "manual_only": manual_only, "user_invocable": user_invocable})
    return result


def resolve_invocation(agent, message):
    match = re.match(r"^/([^\s/]+)(?:\s+([\s\S]*))?$", str(message).strip())
    if not match:
        return None
    command, arguments = match.group(1), match.group(2) or ""
    if command == "skill":
        parts = arguments.split(None, 1)
        if not parts:
            raise HTTPException(400, "使用 /skill 技能名 [任务]，或 /技能名 [任务]")
        command, arguments = parts[0], parts[1] if len(parts) > 1 else ""
    matches = [s for s in available_skills(agent) if s["user_invocable"] and command in {s["command"], s["id"]}]
    if len(matches) != 1:
        raise HTTPException(400, "技能不存在、已禁用或名称重复；请使用 /skills 查看可用技能及唯一 ID")
    return {"skill_id": matches[0]["id"], "arguments": arguments}


def skill_authorized(agent, skill_id):
    invoked = (agent.get("_skill_invocation") or {}).get("skill_id")
    return any(s["id"] == skill_id and (not s["manual_only"] or invoked == skill_id) for s in available_skills(agent))


def skill_catalog(agent):
    return [{"id": s["id"], "name": s["name"], "command": s["command"],
             "description": s.get("description", ""), "manual_only": s["manual_only"],
             "user_invocable": s["user_invocable"]} for s in available_skills(agent)]
