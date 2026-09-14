"""Fail-closed client for the separately deployed Docker sandbox broker."""
import asyncio
import os

import httpx


def settings():
    url = os.getenv("CODEZZN_SANDBOX_URL", "").rstrip("/")
    token = os.getenv("CODEZZN_SANDBOX_TOKEN", "")
    if not url or len(token) < 32:
        raise RuntimeError("Sandbox not configured: set broker URL and a token of at least 32 characters; host execution is disabled")
    return url, {"Authorization": "Bearer " + token}


async def sandbox_status():
    url, headers = settings()
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        response = await client.get(url + "/health", headers=headers)
        response.raise_for_status()
        return response.json()


async def run_command(command, mode="read-only"):
    if mode not in ("read-only", "workspace-write"):
        raise PermissionError("Container execution supports read-only or workspace-write only")
    url, headers = settings()
    task_id = None
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        try:
            # Caller-supplied opaque id makes cleanup possible even if POST response is lost.
            import uuid
            task_id = uuid.uuid4().hex
            response = await client.post(url + "/tasks", headers=headers,
                                         json={"id": task_id, "command": command, "mode": mode})
            response.raise_for_status()
            while True:
                response = await client.get(url + "/tasks/" + task_id, headers=headers)
                response.raise_for_status()
                result = response.json()
                if result["status"] not in ("queued", "running", "creating"):
                    if result["status"] in ("failed", "timed_out", "interrupted", "cancelled"):
                        raise RuntimeError(f"Sandbox task {task_id}: {result['status']}; {result.get('error', '')}; cleanup_pending={result.get('cleanup_pending')}")
                    if result.get("cleanup_pending"):
                        raise RuntimeError(f"Sandbox task {task_id} finished but container cleanup is pending")
                    return result
                await asyncio.sleep(0.3)
        except BaseException:
            if task_id:
                async def cancel():
                    try:
                        await client.delete(url + "/tasks/" + task_id, headers=headers)
                    except Exception:
                        # Broker has its own deadline/reaper even if this request fails.
                        pass
                cleanup = asyncio.create_task(cancel())
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await cleanup
            raise
