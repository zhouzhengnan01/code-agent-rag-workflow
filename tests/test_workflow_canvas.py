import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import db, domain_tools, main, workflows, workspace
from backend.app.workflow_store import WorkflowConflict, save_canvas_workflow


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", tmp_path / "workspace")
    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "false")
    monkeypatch.delenv("CODEZZN_ADMIN_KEY", raising=False)
    monkeypatch.delenv("CODEZZN_LEGACY_OWNER_GITHUB_ID", raising=False)
    db.init_db()


def definition():
    return {
        "name": "Canvas hello", "enabled": True, "max_parallel": 4,
        "nodes": [{"id": "i", "type": "input"}, {"id": "p", "type": "prompt", "template": "你好，{{input}}！"}, {"id": "o", "type": "output", "template": "{{p}}"}],
        "edges": [{"source": "i", "target": "p"}, {"source": "p", "target": "o"}],
        "canvas": {"version": 1, "positions": {"i": {"x": -10, "y": 30}}, "viewport": {"x": 0, "y": 0, "zoom": .8}},
    }


def test_canvas_api_versions_conflict_and_execution(store):
    client = TestClient(main.app)
    saved = client.post("/api/resources/workflows", json=definition())
    assert saved.status_code == 200, saved.text
    workflow = saved.json()
    assert workflow["version"] == 1
    path = f"/api/resources/workflows/{workflow['id']}"
    assert client.get(path).json()["canvas"] == definition()["canvas"]
    changed = client.put(path, json={"name": "renamed", "expected_version": 1}).json()
    assert changed["version"] == 2 and changed["canvas"] == workflow["canvas"]
    assert client.put(path, json={"name": "stale", "expected_version": 1}).status_code == 409
    assert client.get(path).json()["name"] == "renamed"
    history = client.get(f"/api/workflows/{workflow['id']}/versions").json()["data"]
    assert [item["version"] for item in history] == [2, 1]
    old = client.get(f"/api/workflows/{workflow['id']}/versions/1").json()
    assert old["name"] == "Canvas hello" and old["canvas"] == workflow["canvas"]
    run = client.post(f"/api/workflows/{workflow['id']}/run", json={"input": "Codezzn"}).json()
    assert run["status"] == "completed" and run["output"] == "你好，Codezzn！"
    assert all(item["status"] == "completed" for item in run["trace"])
    assert client.get(f"/api/workflow-runs/{run['id']}").json()["output"] == run["output"]
    assert client.get(f"/api/workflow-runs?workflow_id={workflow['id']}").json()["data"][0]["id"] == run["id"]


def test_conversation_draft_keeps_canvas_and_interoperates_with_canvas_versions(store):
    saved = save_canvas_workflow(definition())
    draft = domain_tools.create_workflow_draft({"workflow_id": saved["id"], "description": "from agent"}, thread_id=None, turn_id=None)
    assert draft["definition"]["canvas"] == saved["canvas"]
    domain_tools.update_workflow_draft(draft["draft_id"], {"name": "draft edited"})
    result = domain_tools.save_workflow_draft(draft["draft_id"], thread_id=None, turn_id=None)
    assert result["version"] == 2
    assert db.resource_get("workflows", saved["id"])["canvas"] == saved["canvas"]
    with pytest.raises(WorkflowConflict):
        save_canvas_workflow({"name": "stale", "expected_version": 1}, saved["id"])
    stale_draft = domain_tools.create_workflow_draft({"workflow_id": saved["id"]}, thread_id=None, turn_id=None)
    save_canvas_workflow({"description": "canvas changed", "expected_version": 2}, saved["id"])
    with pytest.raises(ValueError, match="其他操作修改"):
        domain_tools.save_workflow_draft(stale_draft["draft_id"], thread_id=None, turn_id=None)


def test_draft_canvas_update_rejects_stale_revision(store):
    client = TestClient(main.app)
    draft = domain_tools.create_workflow_draft(definition(), thread_id=None, turn_id=None)
    original = client.get(f"/api/workflow-drafts/{draft['draft_id']}").json()
    changed = client.put(f"/api/workflow-drafts/{draft['draft_id']}", json={"name": "new", "expected_revision": original["revision"]})
    assert changed.status_code == 200
    assert client.put(f"/api/workflow-drafts/{draft['draft_id']}", json={"name": "stale", "expected_revision": original["revision"]}).status_code == 409
    assert client.post(f"/api/workflow-drafts/{draft['draft_id']}/save", json={"expected_revision": original["revision"]}).status_code == 409
    saved = client.post(f"/api/workflow-drafts/{draft['draft_id']}/save", json={"expected_revision": changed.json()["revision"]})
    assert saved.status_code == 200
    assert saved.json()["name"] == "new"


@pytest.mark.parametrize("patch", [
    {"max_parallel": 0}, {"max_parallel": "4"}, {"canvas": []},
    {"canvas": {"positions": {"i": {"x": "bad", "y": 0}}}},
    {"canvas": {"viewport": {"x": 0, "y": 0, "zoom": 0}}},
    {"edges": [{"source": "i", "target": "missing"}]},
    {"edges": [{"source": "i", "target": "p"}, {"source": "p", "target": "i"}]},
    {"nodes": [{"id": "a", "type": "unknown"}]},
    {"nodes": [{"id": "a", "type": "mcp", "arguments": []}]},
])
def test_invalid_save_is_rejected_without_writing(store, patch):
    client = TestClient(main.app)
    assert client.post("/api/resources/workflows", json={**definition(), **patch}).status_code == 400
    assert db.resource_list("workflows") == []


def test_missing_resources_and_invalid_variable_rejected_before_enqueue(store):
    client = TestClient(main.app)
    workflow = definition()
    workflow["nodes"][1] = {"id": "p", "type": "agent", "agent_id": "missing", "prompt": "{{input}}"}
    saved = client.post("/api/resources/workflows", json=workflow).json()
    assert client.post("/api/workflow-validation", json=workflow).status_code == 400
    assert client.post(f"/api/workflows/{saved['id']}/enqueue", json={}).status_code == 400
    assert client.get("/api/workflow-runs").json()["data"] == []
    bad = definition()
    bad["nodes"][1]["template"] = "{{o}}"
    assert client.post("/api/workflow-validation", json=bad).status_code == 400
    saved = client.put(f"/api/resources/workflows/{saved['id']}", json={**definition(), "enabled": False}).json()
    assert client.post(f"/api/workflows/{saved['id']}/run", json={}).status_code == 400


def test_queued_run_uses_saved_snapshot_even_after_edit(store):
    client = TestClient(main.app)
    saved = client.post("/api/resources/workflows", json=definition()).json()
    queued = client.post(f"/api/workflows/{saved['id']}/enqueue", json={"input": "v1"}).json()
    changed = copy.deepcopy(definition())
    changed["nodes"][1]["template"] = "v2"
    client.put(f"/api/resources/workflows/{saved['id']}", json=changed)
    result = asyncio.run(main.execute_persistent_task(queued["task"]))
    assert result["output"] == "你好，v1！"


def test_configured_knowledge_agent_and_mcp_nodes_use_upstream_results(store, monkeypatch):
    kb = db.resource_save("knowledge", {"name": "kb"})
    agent = db.resource_save("agents", {"name": "agent"})
    server = db.resource_save("mcp_servers", {"name": "mcp"})
    calls = []
    async def search(query, knowledge_ids, limit, diagnostics=None):
        assert query == "question" and knowledge_ids == [kb["id"]] and limit == 3
        calls.append("search")
        return [{"content": "evidence"}]
    async def run_agent(resource, history, prompt, **kwargs):
        assert resource["id"] == agent["id"] and '"content": "evidence"' in prompt
        calls.append("agent")
        return {"content": "answer:evidence"}
    async def call_tool(resource, tool, arguments):
        assert resource["id"] == server["id"] and tool == "echo"
        assert arguments == {"nested": {"value": "answer:evidence"}}
        calls.append("mcp")
        return {"result": "answer:evidence"}
    monkeypatch.setattr(workflows, "search", search)
    monkeypatch.setattr(workflows, "run_agent", run_agent)
    monkeypatch.setattr(workflows.mcp_manager, "call_tool", call_tool)
    definition = {
        "name": "RAG tool pipeline", "nodes": [
            {"id": "k", "type": "knowledge", "knowledge_ids": [kb["id"]], "query": "{{input.question}}", "limit": 3},
            {"id": "a", "type": "agent", "agent_id": agent["id"], "prompt": "Evidence: {{k}}"},
            {"id": "m", "type": "mcp", "server_id": server["id"], "tool": "echo", "arguments": {"nested": {"value": "{{a}}"}}},
            {"id": "o", "type": "output", "template": "{{m.result}}"},
        ], "edges": [{"source": "k", "target": "a"}, {"source": "a", "target": "m"}, {"source": "m", "target": "o"}],
    }
    client = TestClient(main.app)
    saved = client.post("/api/resources/workflows", json=definition).json()
    run = client.post(f"/api/workflows/{saved['id']}/run", json={"input": {"question": "question"}}).json()
    assert run["status"] == "completed", run
    assert run["output"] == "answer:evidence" and calls == ["search", "agent", "mcp"]


@pytest.mark.parametrize("input_value,expected,skipped", [("yes", "MATCH", "no"), ("other", "FALLBACK", "yes")])
def test_branch_with_join_excludes_skipped_values(input_value, expected, skipped):
    workflow = {
        "nodes": [{"id": "gate", "type": "condition", "value": "{{input}}", "equals": "yes"},
                  {"id": "yes", "type": "prompt", "template": "MATCH"}, {"id": "no", "type": "prompt", "template": "FALLBACK"},
                  {"id": "join", "type": "parallel"}, {"id": "out", "type": "output", "template": "{{join.0}}"}],
        "edges": [{"source": "gate", "target": "yes", "when": True}, {"source": "gate", "target": "no", "when": False},
                  {"source": "yes", "target": "join"}, {"source": "no", "target": "join"}, {"source": "join", "target": "out"}],
    }
    workflows.validate_workflow(workflow, runnable=True)
    output, trace, _ = asyncio.run(workflows.run_workflow(workflow, input_value))
    assert output == expected
    assert next(record for record in trace if record["node_id"] == skipped)["status"] == "skipped"


def test_failure_is_checkpointed_per_node_and_successful_nodes_resume(monkeypatch):
    attempts, checkpoints = {}, []
    async def execute(node, *args, **kwargs):
        attempts[node["id"]] = attempts.get(node["id"], 0) + 1
        if node["id"] == "bad" and attempts["bad"] == 1:
            raise RuntimeError("test failure")
        return node["id"]
    monkeypatch.setattr(workflows, "_execute_node", execute)
    workflow = {"nodes": [{"id": "good", "type": "prompt"}, {"id": "bad", "type": "prompt"}], "edges": []}
    with pytest.raises(RuntimeError):
        asyncio.run(workflows.run_workflow(workflow, "", checkpoint=lambda state: checkpoints.append(copy.deepcopy(state))))
    final = checkpoints[-1]
    assert final["visited"] == ["good"]
    assert any(record["status"] == "failed" and record["error"] == "test failure" for record in final["trace"])
    assert any(record["status"] == "running" for state in checkpoints for record in state["trace"])
    _, trace, _ = asyncio.run(workflows.run_workflow(workflow, "", state=final))
    assert attempts == {"good": 1, "bad": 2}
    assert all(record["status"] == "completed" for record in trace)


def test_structured_template_and_nested_tool_arguments():
    context = {"input": {"question": "hello"}, "kb": [{"content": "evidence", "score": .9}], "gate": {"matched": False}}
    assert workflows.render("{{input.question}} {{kb.0.content}} {{gate.matched}}", context) == "hello evidence false"
    assert workflows.render_arguments({"nested": ["{{kb.0.content}}", 2]}, context) == {"nested": ["evidence", 2]}
    with pytest.raises(ValueError, match="变量路径不存在"):
        workflows.render("{{kb.missing}}", context)
    with pytest.raises(ValueError, match="变量尚无结果"):
        workflows.render("{{skipped_branch}}", context)


def test_queued_run_can_be_cancelled(store):
    client = TestClient(main.app)
    saved = client.post("/api/resources/workflows", json=definition()).json()
    queued = client.post(f"/api/workflows/{saved['id']}/enqueue", json={}).json()
    response = client.post(f"/api/workflow-runs/{queued['run_id']}/cancel", json={})
    assert response.json()["cancelled"] is True
    result = client.get(f"/api/workflow-runs/{queued['run_id']}").json()
    assert result["status"] == "cancelled" and result["workflow_version"] == 1
    repeated = client.post(f"/api/workflow-runs/{queued['run_id']}/cancel", json={}).json()
    assert repeated["cancelled"] is True and repeated["run"]["status"] == "cancelled"
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main.execute_persistent_task(queued["task"]))
    assert client.get(f"/api/workflow-runs/{queued['run_id']}").json()["status"] == "cancelled"


def test_stop_reports_completed_result_and_repairs_already_cancelled_task(store):
    from backend.app.tasks import cancel_task
    client = TestClient(main.app)
    saved = client.post("/api/resources/workflows", json=definition()).json()
    completed = client.post(f"/api/workflows/{saved['id']}/run", json={"input": "done"}).json()
    response = client.post(f"/api/workflow-runs/{completed['id']}/cancel", json={}).json()
    assert response["cancelled"] is False and response["status"] == "completed"
    assert response["run"]["output"] == completed["output"]
    queued = client.post(f"/api/workflows/{saved['id']}/enqueue", json={}).json()
    assert cancel_task(queued["task"]["id"])
    response = client.post(f"/api/workflow-runs/{queued['run_id']}/cancel", json={}).json()
    assert response["cancelled"] and response["run"]["status"] == "cancelled"


@pytest.mark.parametrize("on_cancel", ["propagate", "return", "error"])
def test_stop_http_cancels_live_queue_and_does_not_run_downstream(store, monkeypatch, on_cancel):
    import httpx
    from backend.app import tasks

    queue = tasks.PersistentTaskQueue()
    monkeypatch.setattr(main, "task_queue", queue)
    monkeypatch.setattr(tasks, "_active_tenants", lambda: [None])
    visited, cancelled = [], []

    async def scenario():
        started = asyncio.Event()
        original = workflows._execute_node

        async def blocked(node, *args, **kwargs):
            visited.append(node["id"])
            if node["id"] != "p":
                return await original(node, *args, **kwargs)
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.append(node["id"])
                if on_cancel == "return":
                    return "late answer"
                if on_cancel == "error":
                    raise RuntimeError("request aborted")
                raise

        monkeypatch.setattr(workflows, "_execute_node", blocked)
        await queue.start(main.execute_persistent_task, concurrency=1)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                saved = (await client.post("/api/resources/workflows", json=definition())).json()
                queued = (await client.post(f"/api/workflows/{saved['id']}/enqueue", json={"input": "test", "max_attempts": 3})).json()
                queue._wakeup.set()
                await asyncio.wait_for(started.wait(), 4)
                execution = queue.running[queued["task"]["id"]]
                response = await client.post(f"/api/workflow-runs/{queued['run_id']}/cancel", json={})
                assert response.status_code == 200, response.text
                stopped = response.json()
                assert stopped["cancelled"] and stopped["status"] == "cancelled"
                assert next(t for t in stopped["run"]["trace"] if t["node_id"] == "p")["status"] == "cancelled"
                await asyncio.wait_for(asyncio.gather(execution, return_exceptions=True), 2)
                run = (await client.get(f"/api/workflow-runs/{queued['run_id']}")).json()
                assert run["status"] == "cancelled" and run["output"] is None
                assert next(t for t in json.loads(run["state"])["trace"] if t["node_id"] == "p")["status"] == "cancelled"
                task = tasks.get_task(queued["task"]["id"])
                assert task["status"] == "cancelled" and task["attempts"] == 1
                assert [e["type"] for e in tasks.task_events(task["id"])].count("cancelled") == 1
                assert not any(e["type"] in {"retrying", "failed", "completed"} for e in tasks.task_events(task["id"]))
                assert visited == ["i", "p"] and cancelled == ["p"]
        finally:
            await queue.close()

    asyncio.run(scenario())


def test_queue_failure_after_cancellation_does_not_retry(store, monkeypatch):
    from backend.app import tasks

    async def scenario():
        queue = tasks.PersistentTaskQueue()
        async def handler(task):
            tasks.cancel_task(task["id"])
            raise RuntimeError("late transport failure")
        queue.handler = handler
        task = tasks.enqueue_task("test", "cancel failure", {}, max_attempts=3)
        with db.connect() as connection:
            connection.execute("UPDATE tasks SET status='running',attempts=1 WHERE id=?", (task["id"],))
        await queue._execute(tasks.get_task(task["id"]), None)
        assert tasks.get_task(task["id"])["status"] == "cancelled"
        assert [e["type"] for e in tasks.task_events(task["id"])] == ["queued", "started", "cancelled"]

    asyncio.run(scenario())


def test_local_upload_and_workflow_retrieval_without_ragflow(store, monkeypatch):
    from backend.app import knowledge, knowledge_service

    # Exercise the real upload/chunking/SQLite/search path; replace only external
    # vector and model services so this regression test requires no credentials.
    provider = db.resource_save("providers", {"name": "embedding", "api_key": "test", "base_url": "http://invalid"})
    kb = db.resource_save("knowledge", {"name": "本地部署手册", "backend": "local", "embedding_provider_id": provider["id"],
                                           "embedding_dimension": 2, "rerank_enabled": False})
    assistant = db.resource_save("agents", {"name": "answer"})
    class VectorStore:
        def upsert(self, **kwargs):
            assert kwargs["data"]
        def flush(self, **kwargs):
            pass
    monkeypatch.setattr(knowledge, "_ensure_collection", lambda *args: (VectorStore(), "test_collection"))
    async def embed(provider, texts, model, dimension):
        return [[1.0, 0.0] for _ in texts]
    async def vector_unavailable(*args):
        raise knowledge.KnowledgeError("vectors unavailable")
    def remote_forbidden(*args):
        pytest.fail("Local knowledge must never instantiate a RAGFlow client")
    async def answer(config, history, prompt, **kwargs):
        assert "部署口令是 local-workflow-2026" in prompt
        assert not config["knowledge_ids"]
        return {"content": "部署口令是 local-workflow-2026。"}
    monkeypatch.setattr(knowledge, "_embed", embed)
    monkeypatch.setattr(knowledge, "_vector_search", vector_unavailable)
    monkeypatch.setattr(knowledge_service, "RAGFlowClient", remote_forbidden)
    monkeypatch.setattr(workflows, "run_agent", answer)
    monkeypatch.delenv("RAGFLOW_BASE_URL", raising=False)
    monkeypatch.delenv("RAGFLOW_API_KEY", raising=False)
    client = TestClient(main.app)
    uploaded = client.post(f"/api/knowledge/{kb['id']}/documents", files={"file": ("manual.txt", "部署口令是 local-workflow-2026。".encode(), "text/plain")})
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["backend"] == "local" and uploaded.json()["chunks"] > 0
    flow = {
        "name": "Local RAG", "nodes": [
            {"id": "k", "type": "knowledge", "knowledge_ids": [kb["id"]], "query": "{{input}}"},
            {"id": "a", "type": "agent", "agent_id": assistant["id"], "knowledge_mode": "workflow", "tool_mode": "disabled", "prompt": "问题：{{input}}\n资料：{{k}}"},
            {"id": "o", "type": "output", "template": "{{a}}"}],
        "edges": [{"source": "k", "target": "a"}, {"source": "a", "target": "o"}],
    }
    saved = client.post("/api/resources/workflows", json=flow).json()
    run = client.post(f"/api/workflows/{saved['id']}/run", json={"input": "部署口令是什么？"}).json()
    assert run["status"] == "completed", run
    assert run["output"] == "部署口令是 local-workflow-2026。"
    retrieval = run["trace"][0]["retrieval"]
    assert set(retrieval["backends"]) == {"local"}
    assert retrieval["backends"]["local"]["retrieval"] == "lexical"
    assert retrieval["backends"]["local"]["vector"][0]["status"] == "fallback"


def test_running_cancellation_marks_inflight_nodes(store, monkeypatch):
    started = asyncio.Event()
    async def execute(*args, **kwargs):
        started.set()
        await asyncio.sleep(30)
    monkeypatch.setattr(workflows, "_execute_node", execute)
    client = TestClient(main.app)
    saved = client.post("/api/resources/workflows", json=definition()).json()
    queued = client.post(f"/api/workflows/{saved['id']}/enqueue", json={}).json()
    async def scenario():
        task = asyncio.create_task(main.execute_persistent_task(queued["task"]))
        await asyncio.wait_for(started.wait(), 2)
        from backend.app.tasks import cancel_task
        cancel_task(queued["task"]["id"])
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    result = client.get(f"/api/workflow-runs/{queued['run_id']}").json()
    assert result["status"] == "cancelled"
    assert result["trace"][0]["status"] == "cancelled"


@pytest.mark.parametrize("operator,value,expected,matched", [
    ("contains", "查知识库", "知识", True), ("not_contains", "hello", "知识", True),
    ("not_equals", "a", "b", True), ("is_empty", " ", "", True),
    ("not_empty", "", "", False),
])
def test_condition_operators(operator, value, expected, matched):
    result = asyncio.run(workflows._execute_node({"id": "c", "type": "condition", "operator": operator, "value": value, "equals": expected}, "", {}, []))
    assert result["matched"] is matched


def test_canvas_and_runs_are_tenant_scoped(store, monkeypatch):
    monkeypatch.setenv("CODEZZN_AUTH_REQUIRED", "true")
    client = TestClient(main.app)
    assert client.get("/workflow.html", follow_redirects=False).status_code == 303
    sessions = []
    for email in ("canvas-a@example.com", "canvas-b@example.com"):
        response = client.post("/api/auth/register", json={"name": "test", "email": email, "password": "password-12345"})
        assert response.status_code == 200, response.text
        sessions.append(response.cookies["codezzn_session"])
    client.cookies.set("codezzn_session", sessions[0])
    saved = client.post("/api/resources/workflows", json=definition()).json()
    run = client.post(f"/api/workflows/{saved['id']}/run", json={"input": "tenant A"}).json()
    client.cookies.set("codezzn_session", sessions[1])
    assert client.get(f"/api/resources/workflows/{saved['id']}").status_code == 404
    assert client.get(f"/api/workflow-runs/{run['id']}").status_code == 404
    assert client.get(f"/api/workflows/{saved['id']}/versions").status_code == 404
