"""Minimal LSP 3.18 stdio client for configured language servers."""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from .db import current_tenant
from .workspace import tenant_workspace


class LspError(RuntimeError): pass


class LspManager:
    def __init__(self):
        self.processes, self.locks, self.ids = {}, {}, 0
        self.diagnostics, self.documents, self.stderr_tasks = {}, {}, []

    async def close(self):
        for process in self.processes.values():
            if process.returncode is None:
                process.terminate()
                try: await asyncio.wait_for(process.wait(), 3)
                except asyncio.TimeoutError: process.kill()
        self.processes.clear()
        for task in self.stderr_tasks: task.cancel()

    def _validate_uris(self, value, root):
        """Reject out-of-workspace URIs in request params and WorkspaceEdit results."""
        if isinstance(value, dict):
            for key, item in value.items():
                if (key == "uri" or key.endswith("Uri")) and isinstance(item, str): self._uri(item, root)
                if key == "changes" and isinstance(item, dict):
                    for uri in item: self._uri(uri, root)
                self._validate_uris(item, root)
        elif isinstance(value, list):
            for item in value: self._validate_uris(item, root)

    def _uri(self, value, root):
        parsed = urlparse(value)
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            raise LspError("LSP only accepts local workspace file URIs")
        path = unquote(parsed.path)
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":": path = path[1:]
        try: Path(path).resolve().relative_to(Path(root).resolve())
        except ValueError: raise LspError("LSP URI escapes workspace")

    async def _http_request(self, config, root, method, params):
        sandbox = config.get("transport") == "sandbox"
        endpoint = str(config.get("endpoint") or "").rstrip("/")
        if sandbox:
            from .sandbox import settings
            url, headers = settings()
            endpoint = url + "/lsp"
        allowed = {item.strip().rstrip("/") for item in os.getenv("CODEZZN_LSP_PROXY_URLS", "").split(",") if item.strip()}
        parsed = urlparse(endpoint)
        if (not sandbox and endpoint not in allowed) or parsed.scheme not in ("http", "https") or parsed.username or parsed.password or parsed.fragment:
            raise LspError("LSP HTTP proxy must be explicitly administrator-allowlisted in CODEZZN_LSP_PROXY_URLS")
        token = os.getenv("CODEZZN_LSP_PROXY_TOKEN", "") if not sandbox else headers["Authorization"][7:]
        if len(token) < 32: raise LspError("LSP proxy requires administrator token of at least 32 characters")
        try: cwd = Path(root).resolve().relative_to(tenant_workspace().resolve()).as_posix() or "."
        except ValueError: raise LspError("LSP root escapes tenant workspace")
        async with httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False) as client:
            response = await client.post(endpoint, headers={"Authorization": "Bearer " + token}, json={"tenant": current_tenant(), "server_id": config.get("sandbox_server_id") or config["id"], "workspace_uri": Path(root).resolve().as_uri(), "workspace_cwd": cwd, "method": method, "params": params})
            if response.is_redirect: raise LspError("LSP proxy redirects are forbidden")
            response.raise_for_status()
            if len(response.content) > 4 * 1024 * 1024: raise LspError("LSP response exceeds limit")
            payload = response.json()
            if payload.get("error"): raise LspError(str(payload["error"]))
            result = payload.get("result")
            self._validate_uris(result, root)
            return result

    async def _read(self, process):
        headers = {}
        while True:
            line = await process.stdout.readline()
            if not line: raise LspError("Language server exited")
            if line in (b"\r\n", b"\n"): break
            key, value = line.decode(errors="replace").split(":", 1); headers[key.lower()] = value.strip()
        return json.loads((await process.stdout.readexactly(int(headers["content-length"]))).decode())

    async def _send(self, process, payload):
        raw = json.dumps(payload).encode(); process.stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw); await process.stdin.drain()

    async def _request(self, process, method, params):
        self.ids += 1; request_id = self.ids
        await self._send(process, {"jsonrpc":"2.0","id":request_id,"method":method,"params":params})
        while True:
            message = await asyncio.wait_for(self._read(process), 30)
            if message.get("method") == "textDocument/publishDiagnostics":
                payload = message.get("params") or {}
                self.diagnostics[(id(process), payload.get("uri"))] = payload
            if message.get("id") == request_id:
                if message.get("error"): raise LspError(message["error"].get("message", str(message["error"])))
                return message.get("result")
            # Language servers can issue client requests while a client request is pending.
            if "id" in message and message.get("method"):
                method = message["method"]
                result = ([None] * len((message.get("params") or {}).get("items", []))) if method == "workspace/configuration" else ([] if method == "workspace/workspaceFolders" else None)
                await self._send(process, {"jsonrpc":"2.0","id":message["id"],"result":result})

    async def process(self, config, root):
        if current_tenant() is not None:
            raise LspError("多用户模式下本机 LSP 进程暂不可用")
        root = Path(root).resolve(); key = f"{config['id']}:{root}"
        process = self.processes.get(key)
        if process and process.returncode is None: return process
        process = await asyncio.create_subprocess_exec(config["command"], *config.get("args", []), cwd=str(root), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        async def drain():
            while await process.stderr.read(8192): pass
        self.stderr_tasks.append(asyncio.create_task(drain()))
        self.processes[key] = process
        uri = root.as_uri()
        await self._request(process, "initialize", {"processId":None,"rootUri":uri,"capabilities":{"textDocument":{"documentSymbol":{},"references":{},"publishDiagnostics":{}}},"workspaceFolders":[{"uri":uri,"name":"workspace"}]})
        await self._send(process, {"jsonrpc":"2.0","method":"initialized","params":{}})
        return process

    async def request(self, config, root, method, params):
        supported = {"textDocument/didOpen", "textDocument/didChange", "textDocument/didClose", "textDocument/diagnostic", "textDocument/hover", "textDocument/definition", "textDocument/references", "textDocument/documentSymbol", "textDocument/rename", "textDocument/prepareRename", "workspace/symbol"}
        if method not in supported: raise LspError("Unsupported LSP method; arbitrary commands and workspace edits are not executed")
        self._validate_uris(params, root)
        # tenant is part of identity even when two tenant configurations share an id.
        key = f"{current_tenant()}:{config['id']}:{Path(root).resolve()}"
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            if config.get("transport") in ("http", "sandbox"): return await self._http_request(config, root, method, params)
            process = await self.process(config, root)
            if method in ("textDocument/didOpen", "textDocument/didChange", "textDocument/didClose"):
                document = params.get("textDocument") or {}
                uri = document.get("uri")
                if not uri: raise LspError("textDocument.uri is required")
                if method == "textDocument/didChange":
                    old = self.documents.get((key, uri), -1)
                    if not isinstance(document.get("version"), int) or document["version"] <= old: raise LspError("Document version must increase")
                if method != "textDocument/didClose": self.documents[(key, uri)] = document.get("version", 0)
                else: self.documents.pop((key, uri), None)
                await self._send(process, {"jsonrpc": "2.0", "method": method, "params": params})
                return {"notified": True}
            result = await self._request(process, method, params)
            self._validate_uris(result, root)
            return result


lsp_manager = LspManager()
