import asyncio
import json

from .agent import run_agent
from .db import connect, new_id, now, resource_get
from .knowledge_service import search
from .mcp import mcp_manager


SUPPORTED_NODE_TYPES = {"input", "prompt", "agent", "knowledge", "mcp", "output", "condition", "parallel"}


def validate_workflow(workflow):
    nodes = {node["id"]: node for node in workflow.get("nodes", [])}
    if not nodes:
        raise ValueError("工作流至少需要一个节点")
    if len(nodes) != len(workflow.get("nodes", [])):
        raise ValueError("工作流节点 ID 必须唯一")
    for node in nodes.values():
        if node.get("type", "prompt") not in SUPPORTED_NODE_TYPES:
            raise ValueError(f"不支持的节点类型: {node.get('type')}")
    for edge in workflow.get("edges", []):
        if edge.get("source") not in nodes or edge.get("target") not in nodes:
            raise ValueError("工作流边引用了不存在的节点")
    return nodes


def render(value, context):
    text = str(value or "")
    for key, item in context.items():
        text = text.replace("{{" + key + "}}", str(item))
    return text


async def _execute_node(node, input_value, context, dependencies, *, task_id=None):
    node_id, kind = node["id"], node.get("type", "prompt")
    if kind == "input":
        return input_value
    if kind == "prompt":
        return render(node.get("template", "{{input}}"), context)
    if kind == "agent":
        agent = resource_get("agents", node["agent_id"])
        if not agent:
            raise ValueError(f"工作流节点 {node_id} 的智能体不存在")
        prompt = render(node.get("prompt", "{{input}}"), context)
        return (await run_agent(agent, [], prompt, current_task_id=task_id))["content"]
    if kind == "knowledge":
        return await search(render(node.get("query", "{{input}}"), context), node.get("knowledge_ids") or [], node.get("limit", 5))
    if kind == "mcp":
        server = resource_get("mcp_servers", node["server_id"])
        if not server:
            raise ValueError(f"工作流节点 {node_id} 的 MCP 服务不存在")
        args = {key: render(value, context) if isinstance(value, str) else value for key, value in (node.get("arguments") or {}).items()}
        return await mcp_manager.call_tool(server, node["tool"], args)
    if kind == "output":
        return render(node.get("template", "{{input}}"), context)
    if kind == "condition":
        left = render(node.get("value", "{{input}}"), context)
        expected = render(node.get("equals", "true"), context)
        return {"value": left, "matched": str(left) == str(expected)}
    if kind == "parallel":
        return [context.get(dependency) for dependency in dependencies]
    raise ValueError(f"不支持的节点类型: {kind}")


def _edge_enabled(edge, context):
    if "when" not in edge:
        return True
    source = context.get(edge["source"])
    value = source.get("matched") if isinstance(source, dict) and "matched" in source else bool(source)
    expected = edge.get("when")
    if isinstance(expected, str):
        expected = expected.lower() in {"true", "1", "yes", "matched"}
    return bool(value) == bool(expected)


async def run_workflow(workflow, input_value, *, state=None, checkpoint=None, task_id=None):
    nodes = validate_workflow(workflow)
    edges = workflow.get("edges", [])
    incoming = {node_id: [edge for edge in edges if edge["target"] == node_id] for node_id in nodes}
    context = dict((state or {}).get("context") or {"input": input_value})
    context.setdefault("input", input_value)
    trace = list((state or {}).get("trace") or [])
    visited = set((state or {}).get("visited") or [])
    skipped = set((state or {}).get("skipped") or [])
    parallelism = max(1, min(int(workflow.get("max_parallel", 4)), 16))

    async def persist():
        if checkpoint:
            value = {"context": context, "trace": trace, "visited": sorted(visited), "skipped": sorted(skipped)}
            result = checkpoint(value)
            if asyncio.iscoroutine(result):
                await result

    while len(visited) < len(nodes):
        ready, newly_skipped = [], []
        for node_id in nodes:
            if node_id in visited:
                continue
            dependencies = incoming[node_id]
            if not dependencies:
                ready.append(node_id)
                continue
            if not all(edge["source"] in visited for edge in dependencies):
                continue
            enabled = [edge for edge in dependencies if edge["source"] not in skipped and _edge_enabled(edge, context)]
            if enabled:
                ready.append(node_id)
            else:
                newly_skipped.append(node_id)
        if newly_skipped:
            for node_id in newly_skipped:
                visited.add(node_id)
                skipped.add(node_id)
                trace.append({"node_id": node_id, "type": nodes[node_id].get("type", "prompt"), "status": "skipped", "started_at": now(), "completed_at": now()})
            await persist()
            continue
        if not ready:
            raise ValueError("工作流包含环、不可达节点或无效条件分支")

        batch = ready[:parallelism]

        async def execute(node_id):
            node = nodes[node_id]
            retries = max(0, min(int(node.get("retries", 0)), 5))
            timeout = max(1, min(int(node.get("timeout", 120)), 3600))
            started, last_error = now(), None
            for attempt in range(retries + 1):
                try:
                    output = await asyncio.wait_for(
                        _execute_node(node, input_value, dict(context), [edge["source"] for edge in incoming[node_id]], task_id=task_id),
                        timeout=timeout,
                    )
                    return node_id, output, {"node_id": node_id, "type": node.get("type", "prompt"), "status": "completed", "attempts": attempt + 1, "output": output, "started_at": started, "completed_at": now()}
                except Exception as exc:
                    last_error = exc
                    if attempt < retries:
                        await asyncio.sleep(min(2 ** attempt, 5))
            raise RuntimeError(f"工作流节点 {node_id} 执行失败（{retries + 1} 次尝试）：{last_error}") from last_error

        results = await asyncio.gather(*(execute(node_id) for node_id in batch), return_exceptions=True)
        failure = next((result for result in results if isinstance(result, Exception)), None)
        for result in results:
            if isinstance(result, Exception):
                continue
            node_id, output, record = result
            context[node_id] = output
            context["last"] = output
            trace.append(record)
            visited.add(node_id)
        await persist()
        if failure:
            raise failure
    return context.get("last"), trace, {"context": context, "trace": trace, "visited": sorted(visited), "skipped": sorted(skipped)}


async def create_run(workflow, input_value, *, run_id=None, task_id=None, raise_errors=False):
    timestamp = now()
    if run_id:
        with connect() as db:
            row = db.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise ValueError("工作流运行不存在")
        state = json.loads(row["state"] or "{}")
        created_at = row["created_at"]
        with connect() as db:
            db.execute("UPDATE workflow_runs SET status='running',error=NULL,updated_at=? WHERE id=?", (timestamp, run_id))
    else:
        run_id, created_at, state = new_id("run"), timestamp, {}
        with connect() as db:
            db.execute("INSERT INTO workflow_runs(id,workflow_id,status,input,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (run_id, workflow["id"], "running", json.dumps(input_value, ensure_ascii=False), "{}", timestamp, timestamp))

    def checkpoint(value):
        with connect() as db:
            db.execute("UPDATE workflow_runs SET state=?,trace=?,updated_at=? WHERE id=?", (json.dumps(value, ensure_ascii=False, default=str), json.dumps(value.get("trace", []), ensure_ascii=False, default=str), now(), run_id))

    try:
        output, trace, final_state = await run_workflow(workflow, input_value, state=state, checkpoint=checkpoint, task_id=task_id)
        status, error = "completed", None
    except Exception as exc:
        output, trace, final_state, status, error = {"error": str(exc)}, state.get("trace", []), state, "failed", str(exc)
        with connect() as db:
            latest = db.execute("SELECT state,trace FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        if latest:
            final_state, trace = json.loads(latest["state"] or "{}"), json.loads(latest["trace"] or "[]")
    with connect() as db:
        db.execute("UPDATE workflow_runs SET status=?,output=?,trace=?,state=?,error=?,updated_at=? WHERE id=?", (status, json.dumps(output, ensure_ascii=False), json.dumps(trace, ensure_ascii=False, default=str), json.dumps(final_state, ensure_ascii=False, default=str), error, now(), run_id))
    result = {"id": run_id, "workflow_id": workflow["id"], "status": status, "input": input_value, "output": output, "trace": trace, "error": error, "created_at": created_at, "updated_at": now()}
    if error and raise_errors:
        raise RuntimeError(error)
    return result
