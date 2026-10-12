import asyncio
import json

import pytest

from backend.app import agent
from backend.app.retrieval_policy import automatic_retrieval, knowledge_available, retrieval_mode, validate_cards


CARD = {"id": "idea_1", "kind": "ready", "title": "实现方案", "description": "等待用户选择", "actions": [{"id": "start", "label": "采用方案"}]}
SOURCE = {"source": "policy.txt", "position": 1, "score": 1, "content": "内部制度"}


@pytest.mark.parametrize("mode,present,automatic", [(None, True, False), ("auto", True, False), ("always", True, True), ("off", False, False)])
def test_default_and_explicit_retrieval_policies(mode, present, automatic):
    settings = {"knowledge_ids": ["kb"]}
    if mode is not None: settings["retrieval_mode"] = mode
    allow = lambda *_: "allow"
    assert knowledge_available(settings, allow) is present
    assert automatic_retrieval(settings, allow) is automatic


@pytest.mark.parametrize("extra", [{"_workflow_no_tools": True}, {"knowledge_ids": []}, {"tool_policy": {"tools": {"knowledge_search": "deny"}}}, {"retrieval_mode": "off"}])
def test_unavailable_knowledge_is_hidden_and_rejected(extra):
    settings = {"knowledge_ids": ["kb"], "builtin_tools": ["knowledge_search"], **extra}
    specs, routes = asyncio.run(agent.tool_specs(settings))
    assert "knowledge_search" not in [tool["function"]["name"] for tool in specs]
    with pytest.raises(PermissionError):
        asyncio.run(agent.execute_tool("knowledge_search", {"query": "制度"}, settings, {"knowledge_search": ("builtin", None)}))


def test_knowledge_auto_is_implicitly_available_without_builtin_checkbox():
    specs, _ = asyncio.run(agent.tool_specs({"knowledge_ids": ["kb"]}))
    assert "knowledge_search" in [tool["function"]["name"] for tool in specs]
    with pytest.raises(ValueError): retrieval_mode({"retrieval_mode": "workflow"})


def test_auto_scope_is_available_to_model_without_retrieving(monkeypatch):
    monkeypatch.setattr(agent, "load_instructions", lambda *_: {"content": ""})
    monkeypatch.setattr(agent, "resource_get", lambda *_: {"name": "内部制度", "description": "员工报销流程", "enabled": True})
    prompt = asyncio.run(agent.build_context({"knowledge_ids": ["kb"]}))
    assert "员工报销流程" in prompt and "knowledge_search" in prompt and "Retrieval mode: auto" in prompt
    assert "<knowledge_scope>" not in asyncio.run(agent.build_context({"knowledge_ids": ["kb"], "retrieval_mode": "off"}))


@pytest.mark.parametrize("cards", [[], [CARD, CARD], [{**CARD, "kind": "execute"}], [{**CARD, "actions": [CARD["actions"][0]] * 2}], [{**CARD, "title": "x" * 201}]])
def test_invalid_cards_are_rejected(cards):
    with pytest.raises(ValueError): validate_cards(cards)


@pytest.mark.parametrize("protocol", ["chat_completions", "responses"])
@pytest.mark.parametrize("mode", ["auto", "always", "off"])
def test_main_model_controls_auto_retrieval_and_both_protocols_show_cards(monkeypatch, protocol, mode):
    provider = {"id": "provider", "name": "Test", "api_mode": protocol}
    monkeypatch.setattr(agent, "resource_get", lambda kind, ident: provider if kind == "providers" else {"name": "制度", "description": "公司内部制度", "enabled": True})
    async def context(*args, **kwargs): return "Test context"
    monkeypatch.setattr(agent, "build_context", context)
    monkeypatch.setattr(agent, "save_agent_run", lambda *args, **kwargs: None)
    async def execute_once(call_id, name, args, settings, routes, **kwargs):
        return await agent.execute_tool(name, args, settings, routes, **kwargs)
    monkeypatch.setattr(agent, "execute_tool_once", execute_once)
    searches = []
    async def search(query, ids, *args, **kwargs):
        searches.append(query)
        return [SOURCE]
    monkeypatch.setattr(agent, "search", search)
    monkeypatch.setattr(agent, "format_retrieval_context", lambda sources: "Retrieved facts")
    calls = []
    async def completion(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            tools = [{"id": "cards_call", "function": {"name": "present_cards", "arguments": json.dumps({"cards": [CARD]}, ensure_ascii=False)}}]
            if mode == "auto": tools.insert(0, {"id": "search_call", "function": {"name": "knowledge_search", "arguments": '{"query":"公司制度"}'}})
            result = {"content": "", "tool_calls": tools}
        else: result = {"content": "已完成", "tool_calls": []}
        return (result, {}, "response_id", {}) if protocol == "responses" else (result, {})
    monkeypatch.setattr(agent, "response_completion" if protocol == "responses" else "chat_completion", completion)
    settings = {"id": "agent", "provider_id": "provider", "model": "test-model", "knowledge_ids": ["kb"], "retrieval_mode": mode, "auto_approve": True}
    result = asyncio.run(agent.run_agent(settings, [], "内部制度怎么规定？"))
    assert result["status"] == "completed"
    assert searches == (["公司制度"] if mode == "auto" else ["内部制度怎么规定？"] if mode == "always" else [])
    assert len(result["sources"]) == (0 if mode == "off" else 1)
    cards = [item for item in result["events"] if item["type"] == "interaction_cards"]
    assert len(cards) == 1 and cards[0]["tool_call_id"] == "cards_call"
    assert not any(item["type"] == "approval_required" for item in result["events"])


@pytest.mark.parametrize("protocol", ["chat_completions", "responses"])
def test_auto_identity_question_never_prefetches(monkeypatch, protocol):
    provider = {"id": "provider", "api_mode": protocol}
    monkeypatch.setattr(agent, "resource_get", lambda *_: provider)
    async def context(*args, **kwargs): return "Context"
    async def forbidden(*args, **kwargs): raise AssertionError("Identity should not search")
    async def completion(*args, **kwargs):
        result = {"content": "我是 Codezzn", "tool_calls": []}
        return (result, {}, "response", {}) if protocol == "responses" else (result, {})
    monkeypatch.setattr(agent, "build_context", context)
    monkeypatch.setattr(agent, "search", forbidden)
    monkeypatch.setattr(agent, "save_agent_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent, "response_completion" if protocol == "responses" else "chat_completion", completion)
    result = asyncio.run(agent.run_agent({"id": "agent", "provider_id": "provider", "model": "test", "knowledge_ids": ["kb"]}, [], "你是谁？"))
    assert result["sources"] == [] and not any(event["type"].startswith("knowledge_") for event in result["events"])


@pytest.mark.parametrize("protocol", ["chat_completions", "responses"])
def test_resumed_execution_keeps_prior_sources_without_prefetching(monkeypatch, protocol):
    provider = {"id": "provider", "api_mode": protocol}
    monkeypatch.setattr(agent, "resource_get", lambda *_: provider)
    async def context(*args, **kwargs): return "Context"
    async def forbidden(*args, **kwargs): raise AssertionError("Resume must not prefetch again")
    async def completion(*args, **kwargs):
        result = {"content": "原引用仍可使用", "tool_calls": []}
        return (result, {}, "response", {}) if protocol == "responses" else (result, {})
    monkeypatch.setattr(agent, "build_context", context)
    monkeypatch.setattr(agent, "search", forbidden)
    monkeypatch.setattr(agent, "save_agent_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent, "response_completion" if protocol == "responses" else "chat_completion", completion)
    state = {"sources": [SOURCE], "events": [], "messages": [], "mode": "responses" if protocol == "responses" else "chat", "user_message": "制度", "provider_id": "provider", "model": "test"}
    result = asyncio.run(agent.run_agent({"id": "agent", "provider_id": "provider", "model": "test", "knowledge_ids": ["kb"], "retrieval_mode": "always"}, [], "", resume_state=state))
    assert result["sources"][0]["source"] == "policy.txt"
