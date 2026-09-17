import re

from .db import resource_get


ROLE_TEMPLATES = {
    "general": {
        "name": "通用执行者",
        "description": "分析需求、调用工具并验证结果。",
        "instructions": "准确理解目标，持续执行到任务完成；在结论中说明验证结果。",
    },
    "coding": {
        "name": "软件工程师",
        "description": "面向代码库分析、实现、测试和审查。",
        "instructions": (
            "像资深软件工程师一样工作：先检查仓库和约束，再做最小且完整的修改；"
            "修改后运行与风险匹配的测试，检查 Git diff，并明确报告剩余风险。"
        ),
    },
    "reviewer": {
        "name": "代码审查员",
        "description": "只读检查正确性、安全性和回归风险。",
        "instructions": (
            "以代码审查为主，优先发现可复现的正确性、安全性和兼容性问题；"
            "给出文件位置、触发条件和最小修复建议，不在没有授权时修改文件。"
        ),
    },
    "research": {
        "name": "研究分析师",
        "description": "收集证据、比较来源并形成可追溯结论。",
        "instructions": "区分事实、推断与未知信息；优先使用可追溯来源，并在证据不足时继续调用可用工具。",
    },
    "operator": {
        "name": "运维执行者",
        "description": "诊断服务、执行命令并控制变更风险。",
        "instructions": "先收集运行状态和日志，再执行可回滚操作；对破坏性或外部副作用操作使用审批。",
    },
}


def role_template(name):
    return ROLE_TEMPLATES.get(name or "general", ROLE_TEMPLATES["general"])


def tool_policy_decision(agent, tool_name):
    policy = agent.get("tool_policy") or {}
    rules = policy.get("tools") if isinstance(policy, dict) else {}
    rules = rules if isinstance(rules, dict) else {}
    candidates = [tool_name]
    if tool_name.startswith("mcp__"):
        candidates.extend(["mcp:*", "mcp"])
    for key in candidates:
        value = rules.get(key)
        if value in {"allow", "ask", "deny"}:
            return value
    default = policy.get("default", "inherit") if isinstance(policy, dict) else "inherit"
    return default if default in {"allow", "ask", "deny", "inherit"} else "inherit"


def model_candidates(agent, user_message):
    routes = agent.get("model_routes") or []
    selected = []
    for route in sorted((item for item in routes if isinstance(item, dict)), key=lambda item: int(item.get("priority", 0)), reverse=True):
        pattern = str(route.get("pattern") or "").strip()
        keywords = [str(value).lower() for value in route.get("keywords", []) if str(value).strip()]
        matched = bool(pattern and re.search(pattern, user_message, re.IGNORECASE)) or bool(keywords and any(word in user_message.lower() for word in keywords))
        if matched:
            selected.append(route)
    selected.append({"provider_id": agent.get("provider_id"), "model": agent.get("model")})
    selected.extend(item for item in (agent.get("fallback_models") or []) if isinstance(item, dict))
    result, seen = [], set()
    for item in selected:
        provider = resource_get("providers", item.get("provider_id"))
        if not provider or not provider.get("enabled", True):
            continue
        model = item.get("model") or provider.get("default_model")
        key = (provider["id"], model)
        if model and key not in seen:
            seen.add(key)
            result.append((provider, model))
    return result
