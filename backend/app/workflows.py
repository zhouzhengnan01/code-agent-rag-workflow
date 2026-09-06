import json

from .agent import run_agent
from .db import connect, new_id, now, resource_get
from .knowledge import search
from .mcp import mcp_manager


def render(value, context):
    text = str(value or "")
    for key, item in context.items():
        text = text.replace("{{" + key + "}}", str(item))
    return text


async def run_workflow(workflow, input_value):
    nodes = {node["id"]: node for node in workflow.get("nodes", [])}
    incoming = {node_id: [] for node_id in nodes}
    outgoing = {node_id: [] for node_id in nodes}
    for edge in workflow.get("edges", []):
        outgoing[edge["source"]].append(edge["target"])
        incoming[edge["target"]].append(edge["source"])
    ready = [node_id for node_id, deps in incoming.items() if not deps]
    context, trace, visited = {"input": input_value}, [], set()
    while ready:
        node_id = ready.pop(0)
        node = nodes[node_id]
        kind = node.get("type", "prompt")
        started = now()
        if kind == "input":
            output = input_value
        elif kind == "prompt":
            output = render(node.get("template", "{{input}}"), context)
        elif kind == "agent":
            agent = resource_get("agents", node["agent_id"])
            if not agent:
                raise ValueError(f"工作流节点 {node_id} 的智能体不存在")
            prompt = render(node.get("prompt", "{{input}}"), context)
            output = (await run_agent(agent, [], prompt))["content"]
        elif kind == "knowledge":
            output = await search(render(node.get("query", "{{input}}"), context), node.get("knowledge_ids"), node.get("limit", 5))
        elif kind == "mcp":
            server = resource_get("mcp_servers", node["server_id"])
            args = node.get("arguments", {})
            args = {key: render(value, context) if isinstance(value, str) else value for key, value in args.items()}
            output = await mcp_manager.call_tool(server, node["tool"], args)
        elif kind == "output":
            output = render(node.get("template", "{{input}}"), context)
        else:
            raise ValueError(f"不支持的节点类型: {kind}")
        context[node_id] = output
        context["last"] = output
        trace.append({"node_id": node_id, "type": kind, "output": output, "started_at": started, "completed_at": now()})
        visited.add(node_id)
        for target in outgoing[node_id]:
            if all(dep in visited for dep in incoming[target]) and target not in ready:
                ready.append(target)
    if len(visited) != len(nodes):
        raise ValueError("工作流包含环或不可达节点")
    return context.get("last"), trace


async def create_run(workflow, input_value):
    run_id, timestamp = new_id("run"), now()
    with connect() as db:
        db.execute("INSERT INTO workflow_runs(id,workflow_id,status,input,created_at,updated_at) VALUES(?,?,?,?,?,?)", (run_id, workflow["id"], "running", json.dumps(input_value, ensure_ascii=False), timestamp, timestamp))
    try:
        output, trace = await run_workflow(workflow, input_value)
        status = "completed"
    except Exception as exc:
        output, trace, status = {"error": str(exc)}, [], "failed"
    with connect() as db:
        db.execute("UPDATE workflow_runs SET status=?,output=?,trace=?,updated_at=? WHERE id=?", (status, json.dumps(output, ensure_ascii=False), json.dumps(trace, ensure_ascii=False), now(), run_id))
    return {"id": run_id, "workflow_id": workflow["id"], "status": status, "input": input_value, "output": output, "trace": trace, "created_at": timestamp, "updated_at": now()}
