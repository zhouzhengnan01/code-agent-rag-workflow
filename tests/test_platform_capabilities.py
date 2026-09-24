import asyncio
import threading
import time

from backend.app import db
from backend.app.capabilities import model_candidates, tool_policy_decision
from backend.app.db import init_db, resource_save
from backend.app.memory import memory_context, save_memory, search_memories
from backend.app.mcp import McpManager
from backend.app.tasks import PersistentTaskQueue, enqueue_task, get_task
from backend.app import workflows


def setup_module():
    init_db()


def test_role_routing_policy_and_memory():
    first = resource_save("providers", {"name": "fast", "models": ["fast"], "default_model": "fast"})
    second = resource_save("providers", {"name": "strong", "models": ["strong"], "default_model": "strong"})
    agent = {
        "provider_id": first["id"], "model": "fast",
        "model_routes": [{"keywords": ["review"], "provider_id": second["id"], "model": "strong", "priority": 10}],
        "fallback_models": [{"provider_id": second["id"], "model": "strong"}],
        "tool_policy": {"default": "deny", "tools": {"read_file": "allow", "mcp:*": "ask"}},
    }
    assert [model for _, model in model_candidates(agent, "please review this")][:2] == ["strong", "fast"]
    assert tool_policy_decision(agent, "read_file") == "allow"
    assert tool_policy_decision(agent, "write_file") == "deny"
    assert tool_policy_decision(agent, "mcp__abc__search") == "ask"
    saved = save_memory("project", "capabilities", "FastAPI 项目使用 lifespan", importance=0.9)
    assert saved["scope_id"] == "capabilities"
    assert search_memories("FastAPI lifespan", [("project", "capabilities")])[0]["id"] == saved["id"]
    context, items = memory_context("FastAPI", "capabilities", "nobody")
    assert "不得覆盖用户当前指令" in context and items


def test_mcp_negotiation_roots_and_pagination(monkeypatch):
    manager = McpManager()
    config = {"id": "mcp_test"}
    assert manager._initialize_params(config)["protocolVersion"] == "2025-11-25"
    assert "sampling" not in manager._initialize_params(config)["capabilities"]

    pages = iter([
        {"resources": [{"uri": "one"}], "nextCursor": "next"},
        {"resources": [{"uri": "two"}]},
    ])

    async def request(_config, method, params):
        assert method == "resources/list"
        return next(pages)

    monkeypatch.setattr(manager, "request", request)
    assert asyncio.run(manager.list_resources(config)) == [{"uri": "one"}, {"uri": "two"}]


def test_workflow_parallel_retry_and_condition(monkeypatch):
    attempts = {}

    async def fake_execute(node, input_value, context, dependencies, task_id=None):
        attempts[node["id"]] = attempts.get(node["id"], 0) + 1
        await asyncio.sleep(0.04)
        if node["id"] == "a" and attempts[node["id"]] == 1:
            raise RuntimeError("transient")
        if node.get("type") == "condition":
            return {"matched": True, "value": "yes"}
        return node["id"]

    monkeypatch.setattr(workflows, "_execute_node", fake_execute)
    workflow = {
        "nodes": [
            {"id": "a", "type": "prompt", "retries": 1},
            {"id": "b", "type": "prompt"},
            {"id": "gate", "type": "condition"},
            {"id": "yes", "type": "output"},
            {"id": "no", "type": "output"},
        ],
        "edges": [
            {"source": "a", "target": "gate"}, {"source": "b", "target": "gate"},
            {"source": "gate", "target": "yes", "when": True},
            {"source": "gate", "target": "no", "when": False},
        ],
        "max_parallel": 4,
    }
    started = time.monotonic()
    _, trace, state = asyncio.run(workflows.run_workflow(workflow, "input"))
    assert time.monotonic() - started < 1.4
    assert attempts["a"] == 2 and attempts["b"] == 1
    assert "no" in state["skipped"]
    assert any(item["node_id"] == "yes" and item["status"] == "completed" for item in trace)


def test_persistent_queue_completes_and_records_result():
    async def scenario():
        queue = PersistentTaskQueue()

        async def handler(task):
            return {"echo": task["payload"]["value"]}

        task = enqueue_task("test", "queue capability", {"value": 7}, max_attempts=1)
        await queue.start(handler, concurrency=4)
        assert len(queue.workers) == 1
        assert queue.concurrency == 4
        try:
            for _ in range(40):
                current = get_task(task["id"])
                if current["status"] == "completed":
                    return current
                await asyncio.sleep(0.05)
            raise AssertionError("task did not complete")
        finally:
            await queue.close()

    completed = asyncio.run(scenario())
    assert completed["result"] == {"echo": 7}


def test_persistent_queue_polling_does_not_block_event_loop():
    async def scenario():
        queue = PersistentTaskQueue()
        queue.handler = lambda _task: None
        queue._claim = lambda: time.sleep(0.2)
        queue.workers = [asyncio.create_task(queue._loop())]
        try:
            started = time.monotonic()
            await asyncio.sleep(0.02)
            return time.monotonic() - started
        finally:
            await queue.close()

    assert asyncio.run(scenario()) < 0.1


def test_persistent_queue_does_not_run_task_cancelled_during_claim():
    async def scenario():
        queue = PersistentTaskQueue()
        claimed = threading.Event()
        release = threading.Event()
        handled = []
        task = enqueue_task("test", "cancel race", {}, max_attempts=1)
        original_claim = queue._claim

        def delayed_claim():
            result = original_claim()
            if result and result[0]["id"] == task["id"]:
                claimed.set()
                release.wait(1)
            return result

        async def handler(item):
            handled.append(item["id"])

        queue._claim = delayed_claim
        await queue.start(handler, concurrency=1)
        try:
            assert await asyncio.to_thread(claimed.wait, 1)
            assert await queue.cancel(task["id"])
            release.set()
            await asyncio.sleep(0.1)
            return handled, get_task(task["id"])
        finally:
            release.set()
            await queue.close()

    handled, task = asyncio.run(scenario())
    assert handled == []
    assert task["status"] == "cancelled"


def test_persistent_queue_waits_for_claim_before_closing():
    async def scenario():
        queue = PersistentTaskQueue()
        started = threading.Event()
        release = threading.Event()

        def delayed_claim():
            started.set()
            release.wait(1)

        queue._claim = delayed_claim
        queue.workers = [asyncio.create_task(queue._loop())]
        assert await asyncio.to_thread(started.wait, 1)
        closing = asyncio.create_task(queue.close())
        await asyncio.sleep(0.02)
        still_waiting = not closing.done()
        release.set()
        await closing
        return still_waiting

    assert asyncio.run(scenario())


def test_persistent_queue_claims_tenants_round_robin(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "queue.db"))
    monkeypatch.delenv("CODEZZN_LEGACY_OWNER_GITHUB_ID", raising=False)
    db.init_db()
    first_user = "usr_1111111111111111"
    second_user = "usr_2222222222222222"
    with db.connect(global_db=True) as connection:
        connection.execute(
            "INSERT INTO users(id,email,name,created_at,updated_at) VALUES(?,?,?,?,?)",
            (first_user, "first@example.com", "First", 1, 1),
        )
        connection.execute(
            "INSERT INTO users(id,email,name,created_at,updated_at) VALUES(?,?,?,?,?)",
            (second_user, "second@example.com", "Second", 2, 2),
        )
    for user_id, count in ((first_user, 2), (second_user, 1)):
        db.ensure_tenant(user_id)
        token = db.use_tenant(user_id)
        try:
            for index in range(count):
                enqueue_task("test", f"{user_id}-{index}", {}, max_attempts=1)
        finally:
            db.reset_tenant(token)

    queue = PersistentTaskQueue()
    first_claim = queue._claim()
    second_claim = queue._claim()
    assert first_claim[1] == first_user
    assert second_claim[1] == second_user
