import asyncio
import copy
import json

import pytest

from backend.app import agent as agent_runtime, db, workflows
from backend.app.workflow_store import save_canvas_workflow


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "workflow.db"))
    db.init_db()
    assistant = db.resource_save("agents", {"name": "Assistant", "knowledge_ids": ["automatic-kb"], "builtin_tools": ["knowledge_search", "run_shell"]})
    knowledge = db.resource_save("knowledge", {"name": "产品手册", "description": "企业产品与内部部署文档"})
    return assistant, knowledge


def graph(assistant, knowledge):
    return {
        "name": "Intelligent routing",
        "nodes": [
            {"id": "i", "type": "input"},
            {"id": "route", "type": "router", "agent_id": assistant["id"], "knowledge_ids": [knowledge["id"]], "query": "{{input}}"},
            {"id": "kb", "type": "knowledge", "knowledge_ids": [knowledge["id"]], "query": "{{route.query}}"},
            {"id": "direct", "type": "agent", "agent_id": assistant["id"], "knowledge_mode": "workflow", "tool_mode": "disabled", "prompt": "{{input}}"},
            {"id": "rag", "type": "agent", "agent_id": assistant["id"], "knowledge_mode": "workflow", "tool_mode": "disabled", "prompt": "问题：{{input}}\n资料：{{kb}}"},
            {"id": "od", "type": "output", "template": "{{direct}}"},
            {"id": "ok", "type": "output", "template": "{{rag}}"},
        ],
        "edges": [
            {"source": "i", "target": "route"},
            {"source": "route", "target": "kb", "when": True},
            {"source": "route", "target": "direct", "when": False},
            {"source": "kb", "target": "rag"},
            {"source": "rag", "target": "ok"},
            {"source": "direct", "target": "od"},
        ],
    }


@pytest.mark.parametrize("needs_knowledge", [False, True])
def test_semantic_branches_call_agent_and_only_selected_branch_retrieves(store, monkeypatch, needs_knowledge):
    assistant, knowledge = store
    before = copy.deepcopy(db.resource_get("agents", assistant["id"]))
    calls, searches = [], []

    async def run(config, history, message, **kwargs):
        calls.append(message)
        assert not config["knowledge_ids"]
        assert config["_workflow_no_tools"] is True
        assert history == []
        if len(calls) == 1:
            question = json.loads(message)
            assert question["question"] == ("产品如何部署？" if needs_knowledge else "你是谁？")
            assert question["knowledge_scope"][0]["description"] == "企业产品与内部部署文档"
            content = json.dumps({"needs_knowledge": needs_knowledge, "reason": "需要内部文档" if needs_knowledge else "身份问题不需要检索", "query": "产品部署步骤"}, ensure_ascii=False)
        else:
            if needs_knowledge:
                assert "产品如何部署？" in message and "按手册启动服务" in message
            else:
                assert message == "你是谁？"
            content = "按手册启动服务" if needs_knowledge else "我是 Codezzn 的智能助手。"
        return {"status": "completed", "content": content, "runtime": {"model": "actual-model"}, "usage": {"total_tokens": 15}}

    async def search(query, ids, limit, diagnostics=None):
        searches.append((query, ids, limit))
        return [{"content": "按手册启动服务"}]

    monkeypatch.setattr(workflows, "run_agent", run)
    monkeypatch.setattr(workflows, "search", search)
    flow = graph(assistant, knowledge)
    workflows.validate_workflow(flow, runnable=True, check_resources=True)
    output, trace, state = asyncio.run(workflows.run_workflow(flow, "产品如何部署？" if needs_knowledge else "你是谁？"))
    assert output == ("按手册启动服务" if needs_knowledge else "我是 Codezzn 的智能助手。")
    assert len(calls) == 2
    assert searches == ([("产品部署步骤", [knowledge["id"]], 5)] if needs_knowledge else [])
    assert state["context"]["route"]["matched"] is needs_knowledge
    statuses = {r["node_id"]: r["status"] for r in trace}
    assert statuses["rag"] == ("completed" if needs_knowledge else "skipped")
    assert statuses["direct"] == ("skipped" if needs_knowledge else "completed")
    assert all(r["runtime"]["model"] == "actual-model" for r in trace if r["type"] in ("agent", "router") and r["status"] == "completed")
    assert db.resource_get("agents", assistant["id"]) == before


@pytest.mark.parametrize("value", ['not json', '{"needs_knowledge":"false","reason":"identity"}', '{"needs_knowledge":false}', '[false]', '{"needs_knowledge":true,"reason":"docs","query":3}'])
def test_invalid_router_output_does_not_silently_select_a_branch(value):
    with pytest.raises(ValueError):
        workflows._parse_router_result(value, "original question")


def test_router_accepts_json_fence_and_keeps_original_query():
    result = workflows._parse_router_result('```json\n{"needs_knowledge":false,"reason":"identity","query":""}\n```', "你是谁？")
    assert result == {"matched": False, "reason": "identity", "query": "你是谁？"}


@pytest.mark.parametrize("result", [{"status": "waiting_for_approval", "content": ""}, {"status": "completed", "content": ""}])
def test_unfinished_agent_is_not_reported_as_a_successful_empty_answer(store, monkeypatch, result):
    assistant, _ = store
    async def run(*args, **kwargs):
        return result
    monkeypatch.setattr(workflows, "run_agent", run)
    with pytest.raises(ValueError):
        asyncio.run(workflows._execute_node({"id": "a", "type": "agent", "agent_id": assistant["id"]}, "hello", {"input": "hello"}, []))


def test_old_agent_node_still_inherits_knowledge_and_tools(store, monkeypatch):
    assistant, _ = store
    async def run(config, *args, **kwargs):
        assert config["knowledge_ids"] == ["automatic-kb"]
        assert not config.get("_workflow_no_tools")
        return {"content": "Legacy result"}
    monkeypatch.setattr(workflows, "run_agent", run)
    assert asyncio.run(workflows._execute_node({"id": "a", "type": "agent", "agent_id": assistant["id"]}, "hello", {"input": "hello"}, [])) == "Legacy result"


def test_model_only_policy_disables_implicit_domain_and_coding_tools():
    assert asyncio.run(agent_runtime.tool_specs({"_workflow_no_tools": True, "role_template": "coding", "builtin_tools": ["run_shell"], "mcp_server_ids": ["remote"], "allow_browser": True})) == ([], {})


def test_workflow_retrieval_does_not_hide_remote_connection_failure(store, monkeypatch):
    _, knowledge = store
    async def failed_search(query, ids, limit, diagnostics=None):
        diagnostics.update(status="degraded", backends={"ragflow": {"errors": [{"error": "RAGFlowConfigurationError"}]}})
        return []
    monkeypatch.setattr(workflows, "search", failed_search)
    record = {}
    with pytest.raises(ValueError, match="知识检索服务未正常完成"):
        asyncio.run(workflows._execute_node({"id": "kb", "type": "knowledge", "knowledge_ids": [knowledge["id"]]}, "query", {"input": "query"}, [], execution=record))
    assert record["retrieval"]["status"] == "degraded"


def test_router_graph_round_trips_with_versions_and_rejects_missing_resources(store):
    assistant, knowledge = store
    saved = save_canvas_workflow(graph(assistant, knowledge))
    workflows.validate_workflow(saved, runnable=True, check_resources=True)
    updated = save_canvas_workflow({"expected_version": saved["version"], "description": "Semantic decision"}, saved["id"])
    assert updated["version"] == 2
    assert updated["nodes"][1]["type"] == "router"
    db.resource_save("knowledge", {"name": "disabled", "enabled": False}, knowledge["id"])
    with pytest.raises(ValueError, match="资源不存在或已禁用"):
        workflows.validate_workflow(updated, runnable=True, check_resources=True)
