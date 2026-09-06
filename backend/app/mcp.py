import asyncio
import json

import httpx


class McpError(RuntimeError):
    pass


class McpManager:
    def __init__(self):
        self.processes = {}
        self.locks = {}
        self.http_sessions = {}
        self.request_id = 0

    async def close(self):
        for process in self.processes.values():
            if process.returncode is None:
                process.terminate()
        self.processes.clear()
        self.http_sessions.clear()

    async def list_tools(self, config):
        result = await self.request(config, "tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, config, name, arguments):
        return await self.request(config, "tools/call", {"name": name, "arguments": arguments})

    async def request(self, config, method, params):
        if config.get("transport", "stdio") == "http":
            return await self._http(config, method, params)
        return await self._stdio(config, method, params)

    async def _http(self, config, method, params):
        key = config["id"]
        if key not in self.http_sessions:
            initialized = await self._http_rpc(config, "initialize", {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "codezzn", "version": "0.1.0"}
            })
            self.http_sessions[key] = initialized.pop("_session_id", None)
            await self._http_rpc(config, "notifications/initialized", {}, notification=True)
        return await self._http_rpc(config, method, params)

    async def _http_rpc(self, config, method, params, notification=False):
        self.request_id += 1
        request_id = self.request_id
        headers = {
            **config.get("headers", {}),
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        session_id = self.http_sessions.get(config["id"])
        if session_id:
            headers["MCP-Session-Id"] = session_id
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            payload["id"] = request_id
        async with httpx.AsyncClient(timeout=config.get("timeout", 30), follow_redirects=True) as client:
            response = await client.post(config["url"], headers=headers, json=payload)
            response.raise_for_status()
            if notification or not response.content:
                return {}
            if "text/event-stream" in response.headers.get("content-type", ""):
                data = None
                for line in response.text.splitlines():
                    if not line.startswith("data:"):
                        continue
                    candidate = json.loads(line[5:].strip())
                    if candidate.get("id") == request_id:
                        data = candidate
                        break
                if data is None:
                    raise McpError("MCP SSE 响应中没有匹配的 JSON-RPC 消息")
            else:
                data = response.json()
        if data.get("error"):
            raise McpError(data["error"].get("message", str(data["error"])))
        result = data.get("result", {})
        if method == "initialize":
            result["_session_id"] = response.headers.get("MCP-Session-Id")
        return result

    async def _stdio(self, config, method, params):
        key = config["id"]
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            process = self.processes.get(key)
            if not process or process.returncode is not None:
                env = None
                if config.get("env"):
                    import os
                    env = {**os.environ, **{str(k): str(v) for k, v in config["env"].items()}}
                process = await asyncio.create_subprocess_exec(
                    config["command"], *config.get("args", []),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, env=env,
                )
                self.processes[key] = process
                await self._rpc(process, "initialize", {
                    "protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "codezzn", "version": "0.1.0"}
                })
                process.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode())
                await process.stdin.drain()
            return await self._rpc(process, method, params)

    async def _rpc(self, process, method, params):
        self.request_id += 1
        request_id = self.request_id
        wire = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n"
        process.stdin.write(wire.encode())
        await process.stdin.drain()
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=30)
            if not line:
                stderr = (await process.stderr.read()).decode(errors="replace")
                raise McpError(f"MCP process exited: {stderr[-1000:]}")
            message = json.loads(line)
            if message.get("id") != request_id:
                continue
            if message.get("error"):
                raise McpError(message["error"].get("message", str(message["error"])))
            return message.get("result", {})


mcp_manager = McpManager()
