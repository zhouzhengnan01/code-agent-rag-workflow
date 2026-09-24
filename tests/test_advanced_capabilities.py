import asyncio
import io
import json
import zipfile


def isolated_db(monkeypatch, tmp_path):
    from backend.app import db
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def test_responses_payload_and_result():
    from backend.app.model import _response_result, _responses_payload

    provider = {"context_compaction": True, "compact_threshold": 32000, "async_tools": True}
    tools = [{"type": "function", "function": {"name": "lookup", "description": "x", "parameters": {"type": "object"}}}]
    payload = _responses_payload(provider, "gpt-test", [{"role": "user", "content": "hi"}], tools, "rules", "resp_previous", "high")
    assert payload["previous_response_id"] == "resp_previous"
    assert payload["reasoning"]["effort"] == "high"
    assert payload["parallel_tool_calls"] is True
    assert payload["context_management"][0]["compact_threshold"] == 32000
    assert payload["tools"][0]["async"] is True
    message, usage, response_id, _ = _response_result({
        "id": "resp_1", "usage": {"total_tokens": 3},
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "hello"}]},
            {"type": "function_call", "call_id": "call_1", "name": "lookup", "arguments": "{}"},
        ],
    })
    assert message["content"] == "hello"
    assert message["tool_calls"][0]["id"] == "call_1"
    assert usage["total_tokens"] == 3 and response_id == "resp_1"


def test_local_chat_compaction_preserves_recent_tool_exchange():
    from backend.app.agent import compact_chat_messages

    messages = [{"role": "system", "content": "rules"}]
    messages += [{"role": "user", "content": "old " * 3000}, {"role": "assistant", "content": "answer " * 3000}]
    messages += [{"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]}, {"role": "tool", "tool_call_id": "c1", "content": "ok"}, {"role": "user", "content": "latest"}]
    compacted = compact_chat_messages(messages, 8000, 3)
    assert compacted[0]["content"] == "rules"
    assert compacted[-3:] == messages[-3:]
    assert "locally compacted" in compacted[1]["content"]


def test_python_ast_index_symbols_references_and_graph(monkeypatch, tmp_path):
    isolated_db(monkeypatch, tmp_path)
    source = tmp_path / "sample.py"
    source.write_text("import json\n\ndef caller():\n    return callee()\n\ndef callee():\n    return json.dumps({})\n", encoding="utf-8")
    from backend.app.code_intelligence import graph, rebuild_index, references, symbols

    result = rebuild_index(tmp_path)
    assert result["files"] == 1 and result["symbols"] == 2
    assert symbols(tmp_path, "callee")[0]["name"] == "callee"
    assert len(references(tmp_path, "callee")) == 2
    assert any(edge["source"] == "caller" and edge["target"] == "callee" for edge in graph(tmp_path, "call"))
    assert any(edge["target"] == "json" for edge in graph(tmp_path, "import"))


def test_skill_zip_import_and_integrity(monkeypatch, tmp_path):
    isolated_db(monkeypatch, tmp_path)
    from backend.app import skill_packages, workspace
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("demo/SKILL.md", "---\nname: Demo\nversion: 1.2.3\n---\nUse the script.")
        archive.writestr("demo/skill.json", json.dumps({"version": "1.2.3", "dependencies": [{"type": "python", "name": "httpx"}]}))
        archive.writestr("demo/scripts/run.py", "print('ok')")
        archive.writestr("demo/references/guide.md", "guide")
        archive.writestr("demo/assets/icon.txt", "asset")
    skill = skill_packages.import_package("demo.zip", buffer.getvalue())
    assert skill["version"] == "1.2.3"
    assert skill["scripts"] == ["scripts/run.py"]
    assert skill_packages.verify_package(skill)["ok"] is True
    (skill_packages.package_path(skill, "scripts/run.py")).write_text("changed", encoding="utf-8")
    try:
        skill_packages.verify_package(skill)
        assert False, "tampered package must fail"
    except ValueError as exc:
        assert "完整性" in str(exc)


def test_tool_execution_ledger_reuses_result(monkeypatch, tmp_path):
    isolated_db(monkeypatch, tmp_path)
    from backend.app import agent
    calls = []

    async def fake_execute(name, arguments, configured_agent, routes, **kwargs):
        calls.append((name, arguments))
        return {"ok": len(calls)}

    monkeypatch.setattr(agent, "execute_tool", fake_execute)
    first = asyncio.run(agent.execute_tool_once("call_stable", "read_file", {"path": "a"}, {}, {}, turn_id="turn_1"))
    second = asyncio.run(agent.execute_tool_once("call_stable", "read_file", {"path": "a"}, {}, {}, turn_id="turn_1"))
    assert first == second == {"ok": 1}
    assert len(calls) == 1


def test_memory_hybrid_retrieval_and_expiry(monkeypatch, tmp_path):
    isolated_db(monkeypatch, tmp_path)
    from backend.app.memory import expire_memories, save_memory, search_memories

    saved = save_memory("project", "p1", "FastAPI 使用 lifespan 管理启动与关闭", confidence=0.95)
    assert search_memories("FastAPI lifespan", [("project", "p1")])[0]["id"] == saved["id"]
    expired = save_memory("project", "p1", "过期事实", expires_at=1)
    assert expire_memories() >= 1
    assert all(item["id"] != expired["id"] for item in search_memories("过期事实", [("project", "p1")]))


def test_browser_dom_and_screenshot(monkeypatch, tmp_path):
    from backend.app import browser, workspace
    monkeypatch.setattr(workspace, "BASE_WORKSPACE", tmp_path)
    token = workspace.use_workspace(tmp_path)

    async def scenario():
        await browser.browser_manager.execute("navigate", "smoke", url="data:text/html,<title>Smoke</title><button id=go>Go</button>")
        inspected = await browser.browser_manager.execute("inspect", "smoke", selector="button")
        screenshot = await browser.browser_manager.execute("screenshot", "smoke", path="browser-smoke.png")
        await browser.browser_manager.close()
        return inspected, screenshot

    try:
        inspected, screenshot = asyncio.run(scenario())
    finally:
        workspace.reset_workspace(token)
    assert inspected["elements"][0]["text"] == "Go"
    assert screenshot["path"] == "browser-smoke.png"
    assert (tmp_path / "browser-smoke.png").is_file()
