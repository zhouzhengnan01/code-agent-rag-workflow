"""Agent retrieval policy; workflow node knowledge_mode remains independent."""

MODES = {"auto", "always", "off"}


def retrieval_mode(agent):
    value = agent.get("retrieval_mode", "auto")
    if value not in MODES:
        raise ValueError("retrieval_mode 必须为 auto、always 或 off")
    return value


def knowledge_available(agent, policy):
    return bool(agent.get("knowledge_ids")) and not agent.get("_workflow_no_tools") and retrieval_mode(agent) != "off" and policy(agent, "knowledge_search") != "deny"


def automatic_retrieval(agent, policy):
    return knowledge_available(agent, policy) and retrieval_mode(agent) == "always"


def merge_sources(existing, incoming):
    """Keep source provenance across multiple queries and resumed executions."""
    import json
    result, seen = [], set()
    for source in [*existing, *(incoming if isinstance(incoming, list) else [])]:
        if not isinstance(source, dict):
            continue
        key = json.dumps(source, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(source)
    return result


def validate_cards(value):
    """Validate UI-only cards. They never authorize tools or execute action text."""
    if not isinstance(value, list) or not 1 <= len(value) <= 6:
        raise ValueError("cards 必须包含 1–6 张卡片")
    cards, ids = [], set()

    def text(item, field, limit, required=True):
        raw = item.get(field, "")
        if not isinstance(raw, str) or len(raw) > limit or (required and not raw.strip()):
            raise ValueError(f"卡片 {field} 必须是非空文本且不超过 {limit} 字符")
        return raw.strip()

    for card in value:
        if not isinstance(card, dict):
            raise ValueError("卡片必须为对象")
        ident = text(card, "id", 80)
        if ident in ids:
            raise ValueError("卡片 id 不可重复")
        ids.add(ident)
        kind = card.get("kind")
        if kind not in {"idea", "opportunity", "risk", "ready"}:
            raise ValueError("卡片 kind 无效")
        actions = card.get("actions")
        if not isinstance(actions, list) or not 1 <= len(actions) <= 4:
            raise ValueError("每张卡片必须包含 1–4 个动作")
        normalized_actions, action_ids = [], set()
        for action in actions:
            if not isinstance(action, dict):
                raise ValueError("卡片动作必须为对象")
            action_id = text(action, "id", 80)
            if action_id in action_ids:
                raise ValueError("同卡片动作 id 不可重复")
            action_ids.add(action_id)
            normalized_actions.append({"id": action_id, "label": text(action, "label", 120), "description": text(action, "description", 800, False)})
        cards.append({"id": ident, "kind": kind, "title": text(card, "title", 200), "description": text(card, "description", 4000, False), "actions": normalized_actions})
    return cards
