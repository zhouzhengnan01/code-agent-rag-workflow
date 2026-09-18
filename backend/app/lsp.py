"""Minimal LSP 3.18 stdio client for configured language servers."""
import asyncio
import json
from pathlib import Path


class LspError(RuntimeError): pass


class LspManager:
    def __init__(self): self.processes, self.locks, self.ids = {}, {}, 0

    async def close(self):
        for process in self.processes.values():
            if process.returncode is None:
                process.terminate()
                try: await asyncio.wait_for(process.wait(), 3)
                except asyncio.TimeoutError: process.kill()
        self.processes.clear()

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
            if message.get("id") == request_id:
                if message.get("error"): raise LspError(message["error"].get("message", str(message["error"])))
                return message.get("result")
            # Language servers can issue client requests while a client request is pending.
            if "id" in message and message.get("method"):
                method = message["method"]
                result = ([None] * len((message.get("params") or {}).get("items", []))) if method == "workspace/configuration" else ([] if method == "workspace/workspaceFolders" else None)
                await self._send(process, {"jsonrpc":"2.0","id":message["id"],"result":result})

    async def process(self, config, root):
        root = Path(root).resolve(); key = f"{config['id']}:{root}"
        process = self.processes.get(key)
        if process and process.returncode is None: return process
        process = await asyncio.create_subprocess_exec(config["command"], *config.get("args", []), cwd=str(root), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        self.processes[key] = process
        uri = root.as_uri()
        await self._request(process, "initialize", {"processId":None,"rootUri":uri,"capabilities":{"textDocument":{"documentSymbol":{},"references":{},"publishDiagnostics":{}}},"workspaceFolders":[{"uri":uri,"name":"workspace"}]})
        await self._send(process, {"jsonrpc":"2.0","method":"initialized","params":{}})
        return process

    async def request(self, config, root, method, params):
        lock = self.locks.setdefault(f"{config['id']}:{Path(root).resolve()}", asyncio.Lock())
        async with lock: return await self._request(await self.process(config, root), method, params)


lsp_manager = LspManager()
