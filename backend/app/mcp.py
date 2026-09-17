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
        self.initialized = {}
        self.request_id = 0

    @staticmethod
    def _protocol_version(config):
        return str(config.get("protocol_version") or "2025-11-25")

    @staticmethod
    def _roots(config):
        configured = config.get("roots") or [{"uri": "file:///workspace", "name": "Codezzn workspace"}]
        return [{"uri": str(item["uri"]), **({"name": str(item["name"])} if item.get("name") else {})} for item in configured if item.get("uri")]

    def _initialize_params(self, config):
        return {
            "protocolVersion": self._protocol_version(config),
            "capabilities": {"roots": {"listChanged": False}},
            "clientInfo": {"name": "codezzn", "version": "0.2.0"},
        }

    async def close(self):
        for process in self.processes.values():
            if process.returncode is None:
                process.terminate()
        self.processes.clear()
        self.http_sessions.clear()
        self.initialized.clear()

    async def list_tools(self, config):
        result = await self.request(config, "tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, config, name, arguments):
        return await self.request(config, "tools/call", {"name": name, "arguments": arguments})

    async def server_info(self, config):
        await self.request(config, "ping", {})
        return self.initialized.get(config["id"], {})

    async def _paged(self, config, method, key):
        values, cursor = [], None
        for _ in range(20):
            params = {"cursor": cursor} if cursor else {}
            result = await self.request(config, method, params)
            values.extend(result.get(key, []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return values

    async def list_resources(self, config):
        return await self._paged(config, "resources/list", "resources")

    async def list_resource_templates(self, config):
        return await self._paged(config, "resources/templates/list", "resourceTemplates")

    async def read_resource(self, config, uri):
        return await self.request(config, "resources/read", {"uri": uri})

    async def subscribe_resource(self, config, uri):
        return await self.request(config, "resources/subscribe", {"uri": uri})

    async def unsubscribe_resource(self, config, uri):
        return await self.request(config, "resources/unsubscribe", {"uri": uri})

    async def list_prompts(self, config):
        return await self._paged(config, "prompts/list", "prompts")

    async def get_prompt(self, config, name, arguments=None):
        return await self.request(config, "prompts/get", {"name": name, "arguments": arguments or {}})

    async def complete(self, config, reference, argument):
        return await self.request(config, "completion/complete", {"ref": reference, "argument": argument})

    async def set_log_level(self, config, level="info"):
        return await self.request(config, "logging/setLevel", {"level": level})

    async def request(self, config, method, params):
        if config.get("transport", "stdio") == "http":
            return await self._http(config, method, params)
        return await self._stdio(config, method, params)

    async def _http(self, config, method, params):
        key = config["id"]
        if key not in self.http_sessions:
            initialized = await self._http_rpc(config, "initialize", self._initialize_params(config))
            self.http_sessions[key] = initialized.pop("_session_id", None)
            self.initialized[key] = initialized
            await self._http_rpc(config, "notifications/initialized", {}, notification=True)
        return await self._http_rpc(config, method, params)

    async def _http_rpc(self, config, method, params, notification=False):
        self.request_id += 1
        request_id = self.request_id
        headers = {
            **config.get("headers", {}),
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": (self.initialized.get(config["id"]) or {}).get("protocolVersion", self._protocol_version(config)),
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
                initialized = await self._rpc(process, "initialize", self._initialize_params(config), config)
                self.initialized[key] = initialized
                process.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode())
                await process.stdin.drain()
            return await self._rpc(process, method, params, config)

    async def _respond_to_server_request(self, process, message, config):
        response = {"jsonrpc": "2.0", "id": message.get("id")}
        if message.get("method") == "roots/list":
            response["result"] = {"roots": self._roots(config)}
        elif message.get("method") == "ping":
            response["result"] = {}
        else:
            response["error"] = {"code": -32601, "message": f"Client method not supported: {message.get('method')}"}
        process.stdin.write((json.dumps(response) + "\n").encode())
        await process.stdin.drain()

    async def _rpc(self, process, method, params, config=None):
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
            if "method" in message and "id" in message:
                await self._respond_to_server_request(process, message, config or {})
                continue
            if message.get("id") != request_id:
                continue
            if message.get("error"):
                raise McpError(message["error"].get("message", str(message["error"])))
            return message.get("result", {})


mcp_manager = McpManager()
