"""Isolated capability tests; no model calls, Docker daemon or user workspace writes."""
import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import json
import subprocess
import sys

from backend.app import code_intelligence as ci, db, terminal_tools as terminal
from backend.app.lsp import LspManager, LspError
from backend.app.sandbox_broker import Config, Broker
from backend.app.lsp_sandbox_bridge import BRIDGE


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dbpatch = patch.object(db, "DB_PATH", str(self.root / "state.db")); self.dbpatch.start()
        db.init_db()

    def tearDown(self):
        self.dbpatch.stop(); self.temp.cleanup()

    def source(self, name, content):
        path = self.root / name; path.write_text(content, encoding="utf-8"); return path

    def test_digest_auto_updates_symbols_and_deleted_files(self):
        path = self.source("one.py", "def one(): pass\n")
        self.assertEqual(ci.symbols(self.root)[0]["name"], "one")
        self.assertEqual(ci.rebuild_index(self.root)["changed_files"], 0)
        path.write_text("def two(): pass\n", encoding="utf-8")
        self.assertEqual(ci.symbols(self.root)[0]["name"], "two")
        path.unlink(); self.assertEqual(ci.symbols(self.root), [])

    def test_python_references_distinguish_shadowed_scopes(self):
        self.source("one.py", "def outer():\n x=1\n def inner():\n  x=2\n  return x\n return x\n")
        refs = ci.references(self.root, "outer.x")
        self.assertEqual([x["line"] for x in refs], [2, 6])
        self.assertEqual([x["line"] for x in ci.references(self.root, "outer.inner.x")], [4, 5])

    def test_call_graph_resolves_nested_function(self):
        self.source("one.py", "def outer():\n def work(): pass\n work()\n")
        calls = ci.graph(self.root)
        self.assertEqual(calls[0]["target"], "outer.work")

    def test_call_graph_resolves_explicit_import_alias(self):
        self.source("one.py", "from util import work as run\nimport os.path as path\nrun()\npath.join('a','b')\n")
        self.assertEqual({item["target"] for item in ci.graph(self.root)}, {"util.work", "os.path.join"})

    def test_non_python_analysis_is_explicitly_heuristic(self):
        self.source("index.js", "export function test() {}\n")
        self.assertEqual(ci.symbols(self.root)[0]["analysis"], "heuristic")
        self.assertEqual(ci.references(self.root, "test")[0]["analysis"], "heuristic-text")

    def test_comments_are_not_python_references(self):
        self.source("one.py", "def hello(): pass\n# hello\ntext='hello'\nhello()\n")
        self.assertEqual({x["line"] for x in ci.references(self.root, "hello")}, {1, 4})


class TerminalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.patches = [patch.object(db, "DB_PATH", str(self.root / "db.sqlite")), patch.object(terminal, "tenant_workspace", return_value=self.root)]
        for item in self.patches: item.start()
        db.init_db()
        self.start = patch.object(terminal, "start_command", new=AsyncMock(return_value={"id": "ignored", "status": "running", "output": "first\n"})); self.mock_start = self.start.start()
        self.poll = patch.object(terminal, "command_task", new=AsyncMock(return_value={"status": "completed", "output": "first\nsecond\n", "exit_code": 0, "cleanup_pending": False})); self.mock_poll = self.poll.start()
        self.agent = {"allow_shell": True, "sandbox_mode": "workspace-write"}

    async def asyncTearDown(self):
        self.start.stop(); self.poll.stop()
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    async def test_start_and_incremental_logs_across_turns(self):
        result = await terminal.execute_terminal("terminal_start", {"command": "python test.py", "timeout_seconds": 600}, self.agent, self.root)
        self.assertFalse(result["pty"])
        task = result["task_id"]
        logs = await terminal.execute_terminal("terminal_logs", {"task_id": task, "cursor": 6}, self.agent, self.root)
        self.assertEqual(logs["output"], "second\n")
        self.assertEqual(logs["next_cursor"], 13)
        await terminal.execute_terminal("terminal_cancel", {"task_id": task}, self.agent, self.root)
        self.mock_poll.assert_awaited_with(task, cancel=True)

    async def test_cross_workspace_task_denied(self):
        row = await terminal.execute_terminal("terminal_start", {"command": "echo ok"}, self.agent, self.root)
        with self.assertRaises(PermissionError): await terminal.execute_terminal("terminal_status", {"task_id": row["task_id"]}, self.agent, self.root / "other")

    async def test_cross_tenant_task_denied(self):
        row = await terminal.execute_terminal("terminal_start", {"command": "echo ok"}, self.agent, self.root)
        token = db.use_tenant("usr_" + "a" * 16)
        try:
            with self.assertRaises(PermissionError): await terminal.execute_terminal("terminal_status", {"task_id": row["task_id"]}, self.agent, self.root)
        finally: db.reset_tenant(token)

    async def test_read_only_policy_cannot_be_escalated(self):
        with self.assertRaises(PermissionError): await terminal.execute_terminal("terminal_start", {"command": "echo ok", "mode": "workspace-write"}, {"allow_shell": True, "sandbox_mode": "read-only"}, self.root)
        self.mock_start.assert_not_awaited()

    async def test_traversal_denied(self):
        with self.assertRaises(ValueError): await terminal.execute_terminal("terminal_start", {"command": "id", "cwd": "../outside"}, self.agent, self.root)

    async def test_lost_submit_response_leaves_recoverable_identity(self):
        self.mock_start.side_effect = TimeoutError("lost")
        with self.assertRaisesRegex(RuntimeError, "query terminal_status task_id="): await terminal.execute_terminal("terminal_start", {"command": "id"}, self.agent, self.root)
        with db.connect() as connection:
            row = connection.execute("SELECT * FROM terminal_tasks").fetchone()
        self.assertEqual(row["status"], "submitting")
        result = await terminal.execute_terminal("terminal_status", {"task_id": row["task_id"]}, self.agent, self.root)
        self.assertEqual(result["status"], "completed")


class LspSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_tenant_local_process_still_denied(self):
        token = db.use_tenant("usr_" + "b" * 16)
        try:
            with self.assertRaises(LspError): await LspManager().process({"id": "x", "command": "evil"}, Path.cwd())
        finally: db.reset_tenant(token)

    async def test_outside_workspace_uri_and_execute_command_denied(self):
        manager = LspManager()
        root = Path.cwd()
        with self.assertRaises(LspError): await manager.request({"id": "x"}, root, "textDocument/definition", {"textDocument": {"uri": root.parent.as_uri()}})
        with self.assertRaises(LspError): await manager.request({"id": "x"}, root, "workspace/executeCommand", {})

    async def test_workspace_edit_target_is_checked(self):
        manager = LspManager(); root = Path.cwd()
        with self.assertRaises(LspError): manager._validate_uris({"changes": {root.parent.as_uri(): [{"newText": "escape"}]}}, root)
        manager._validate_uris({"changes": {(root / "safe.py").as_uri(): [{"newText": "ok"}]}}, root)

    async def test_http_proxy_requires_admin_allowlist(self):
        with patch.dict(os.environ, {"CODEZZN_LSP_PROXY_URLS": ""}):
            with self.assertRaisesRegex(LspError, "administrator-allowlisted"): await LspManager().request({"id": "x", "transport": "http", "endpoint": "http://attacker.invalid"}, Path.cwd(), "workspace/symbol", {})

    async def test_sandbox_transport_reuses_broker_token_and_admin_server_alias(self):
        import httpx
        root = Path.cwd()
        response = httpx.Response(200, json={"result": {"contents": "safe hover"}}, request=httpx.Request("POST", "http://broker/lsp"))
        client = AsyncMock(); client.post.return_value = response
        manager = AsyncMock(); manager.__aenter__.return_value = client
        with patch("backend.app.lsp.httpx.AsyncClient", return_value=manager), patch("backend.app.sandbox.settings", return_value=("http://broker", {"Authorization": "Bearer " + "t" * 40})), patch("backend.app.lsp.tenant_workspace", return_value=root):
            result = await LspManager().request({"id": "resource_opaque", "transport": "sandbox", "sandbox_server_id": "python", "command": "ignored-untrusted"}, root, "workspace/symbol", {"query": "main"})
        self.assertEqual(result["contents"], "safe hover")
        request = client.post.call_args
        self.assertEqual(request.args[0], "http://broker/lsp")
        self.assertEqual(request.kwargs["json"]["server_id"], "python")
        self.assertNotIn("command", request.kwargs["json"])
        self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer " + "t" * 40)


class BrokerLspTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"CODEZZN_SANDBOX_TOKEN": "t" * 40, "CODEZZN_SANDBOX_STATE": str(Path(self.temp.name) / "tasks.db"), "CODEZZN_LSP_SERVERS_JSON": json.dumps({"python": ["pyright-langserver", "--stdio"]})})
        self.env.start(); self.broker = Broker(Config(), docker=object())
        self.payload = {"tenant": "usr_" + "a" * 16, "server_id": "python", "workspace_uri": "file:///client/project", "workspace_cwd": "projects/project", "method": "textDocument/hover", "params": {"textDocument": {"uri": "file:///client/project/main.py"}, "position": {"line": 0, "character": 0}}}

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def test_isolated_proxy_maps_uri_and_uses_only_admin_command(self):
        with patch.object(self.broker, "submit") as submit, patch.object(self.broker, "get", return_value={"status": "completed", "exit_code": 0, "cleanup_pending": False, "output": json.dumps({"result": {"uri": "file:///workspace/projects/project/main.py"}})}):
            result = self.broker.lsp(self.payload)
        self.assertEqual(result["result"]["uri"], "file:///client/project/main.py")
        payload = submit.call_args.args[0]
        self.assertEqual(payload["tenant"], self.payload["tenant"])
        self.assertEqual(payload["mode"], "read-only")
        self.assertEqual(payload["cwd"], "projects/project")
        self.assertNotIn("command", self.payload)

    def test_arbitrary_server_and_document_escape_rejected(self):
        with self.assertRaises(ValueError): self.broker.lsp({**self.payload, "server_id": "unconfigured"})
        with self.assertRaises(ValueError): self.broker.lsp({**self.payload, "params": {"textDocument": {"uri": "file:///client/secret.py"}}})
        with self.assertRaises(ValueError): self.broker.lsp({**self.payload, "workspace_cwd": "../other"})

    def test_document_cache_versions_and_tenant_isolation(self):
        opened = {**self.payload, "method": "textDocument/didOpen", "params": {"textDocument": {"uri": "file:///client/project/main.py", "version": 1, "languageId": "python", "text": "x=1"}}}
        self.assertTrue(self.broker.lsp(opened)["notified"])
        changed = {**opened, "method": "textDocument/didChange", "params": {"textDocument": {"uri": "file:///client/project/main.py", "version": 2}, "contentChanges": [{"text": "x=2"}]}}
        self.broker.lsp(changed)
        with self.assertRaises(ValueError): self.broker.lsp(changed)
        with self.assertRaises(ValueError): self.broker.lsp({**changed, "tenant": "usr_" + "b" * 16})

    def test_broker_timeout_policy_rejects_unbounded_background_command(self):
        with self.assertRaises(ValueError): self.broker.submit({"id": "a" * 32, "command": "sleep 500", "timeout_seconds": 86401})

    def test_bridge_real_json_rpc_fixture(self):
        import base64
        fixture = Path(self.temp.name) / "fake_lsp.py"
        fixture.write_text('''import sys,json
while True:
 headers={}
 while True:
  line=sys.stdin.buffer.readline()
  if not line:sys.exit(0)
  if line==b'\\r\\n':break
  key,value=line.decode().split(':',1);headers[key.lower()]=value.strip()
 payload=json.loads(sys.stdin.buffer.read(int(headers['content-length'])))
 if 'id' not in payload:continue
 result={'capabilities':{}} if payload['method']=='initialize' else {'contents':'fixture hover'}
 raw=json.dumps({'jsonrpc':'2.0','id':payload['id'],'result':result}).encode()
 sys.stdout.buffer.write(('Content-Length: %d\\r\\n\\r\\n'%len(raw)).encode()+raw);sys.stdout.buffer.flush()
''', encoding="utf-8")
        packet = {"argv": [sys.executable, str(fixture)], "root_uri": "file:///workspace", "documents": [], "method": "textDocument/hover", "params": {"textDocument": {"uri": "file:///workspace/main.py"}}}
        run = subprocess.run([sys.executable, "-c", BRIDGE, base64.b64encode(json.dumps(packet).encode()).decode()], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["result"]["contents"], "fixture hover")


if __name__ == "__main__": unittest.main()
