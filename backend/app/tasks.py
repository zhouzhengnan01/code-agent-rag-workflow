import asyncio
import json
import os
import uuid

from .db import connect, ensure_tenant, new_id, now, reset_tenant, tenant_ids, use_tenant
from .workspace import tenant_workspace


def _active_tenants():
    # Once the legacy store is assigned, it is a read-only rollback copy.
    return ([] if os.getenv("CODEZZN_LEGACY_OWNER_GITHUB_ID", "").strip() else [None]) + tenant_ids()


def _decode(row):
    item = dict(row)
    for key in ("payload", "result"):
        if item.get(key):
            try:
                item[key] = json.loads(item[key])
            except json.JSONDecodeError:
                pass
    return item


def enqueue_task(kind, name, payload, max_attempts=3, parent_task_id=None):
    task_id, timestamp = new_id("task"), now()
    with connect() as db:
        db.execute(
            "INSERT INTO tasks(id,kind,name,status,payload,attempts,max_attempts,available_at,parent_task_id,created_at,updated_at) VALUES(?,?,?,'queued',?,0,?,?,?,?,?)",
            (task_id, kind, str(name or kind), json.dumps(payload or {}, ensure_ascii=False), max(1, min(int(max_attempts), 10)), timestamp, parent_task_id, timestamp, timestamp),
        )
    append_task_event(task_id, "queued", {"kind": kind})
    return get_task(task_id)


def append_task_event(task_id, event_type, data=None):
    with connect() as db:
        sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 AS value FROM task_events WHERE task_id=?", (task_id,)).fetchone()["value"]
        db.execute("INSERT INTO task_events(id,task_id,sequence,type,data,created_at) VALUES(?,?,?,?,?,?)", (
            new_id("tevt"), task_id, sequence, event_type, json.dumps(data or {}, ensure_ascii=False), now()
        ))


def get_task(task_id):
    with connect() as db:
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return _decode(row) if row else None


def list_tasks(status=None, limit=100):
    with connect() as db:
        if status:
            rows = db.execute("SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, min(int(limit), 500))).fetchall()
        else:
            rows = db.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (min(int(limit), 500),)).fetchall()
    return [_decode(row) for row in rows]


def task_events(task_id):
    with connect() as db:
        rows = db.execute("SELECT * FROM task_events WHERE task_id=? ORDER BY sequence", (task_id,)).fetchall()
    result = []
    for row in rows:
        item = dict(row); item["data"] = json.loads(item["data"] or "{}"); result.append(item)
    return result


def cancel_task(task_id):
    with connect() as db:
        changed = db.execute("UPDATE tasks SET status='cancelled',lease_until=NULL,worker_id=NULL,updated_at=? WHERE id=? AND status IN ('queued','running')", (now(), task_id)).rowcount
    if changed:
        append_task_event(task_id, "cancelled")
    return bool(changed)


class PersistentTaskQueue:
    def __init__(self):
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.handler = None
        self.workers = []
        self.running = {}
        self.stopping = False
        self.concurrency = 1
        self._tenant_cursor = 0
        self._wakeup = asyncio.Event()

    async def start(self, handler, concurrency=2):
        self.handler = handler
        self.stopping = False
        self.concurrency = max(1, min(int(concurrency), 8))
        self._wakeup.clear()
        timestamp = now()
        for user_id in _active_tenants():
            token = use_tenant(user_id)
            try:
                if user_id:
                    ensure_tenant(user_id)
                    tenant_workspace().mkdir(parents=True, exist_ok=True)
                with connect() as db:
                    db.execute("UPDATE tasks SET status='queued',worker_id=NULL,lease_until=NULL,available_at=?,updated_at=? WHERE status='running'", (timestamp, timestamp))
            finally:
                reset_tenant(token)
        self.workers = [asyncio.create_task(self._loop())]

    async def close(self):
        self.stopping = True
        self._wakeup.set()
        workers = list(self.workers)
        await asyncio.gather(*workers, return_exceptions=True)
        running = list(self.running.values())
        for execution in running:
            execution.cancel()
        await asyncio.gather(*running, return_exceptions=True)
        self.workers = []
        self.running = {}

    async def cancel(self, task_id):
        changed = cancel_task(task_id)
        running = self.running.get(task_id)
        if running and not running.done():
            running.cancel()
        return changed

    def _claim(self):
        tenants = _active_tenants()
        if self.stopping or not tenants:
            return None
        timestamp = now()
        start = self._tenant_cursor % len(tenants)
        for offset in range(len(tenants)):
            if self.stopping:
                return None
            index = (start + offset) % len(tenants)
            user_id = tenants[index]
            token = use_tenant(user_id)
            try:
                if user_id:
                    ensure_tenant(user_id)
                    tenant_workspace().mkdir(parents=True, exist_ok=True)
                with connect() as db:
                    row = db.execute("SELECT id FROM tasks WHERE status='queued' AND available_at<=? ORDER BY created_at LIMIT 1", (timestamp,)).fetchone()
                    if not row:
                        continue
                    changed = db.execute(
                        "UPDATE tasks SET status='running',attempts=attempts+1,worker_id=?,lease_until=?,updated_at=? WHERE id=? AND status='queued'",
                        (self.worker_id, timestamp + 300, timestamp, row["id"]),
                    ).rowcount
                if changed:
                    self._tenant_cursor = (index + 1) % len(tenants)
                    return get_task(row["id"]), user_id
            finally:
                reset_tenant(token)
        return None

    def _release_claim(self, task_id, user_id):
        token = use_tenant(user_id)
        try:
            with connect() as db:
                db.execute(
                    "UPDATE tasks SET status='queued',attempts=CASE WHEN attempts>0 THEN attempts-1 ELSE 0 END,"
                    "worker_id=NULL,lease_until=NULL,updated_at=? WHERE id=? AND status='running' AND worker_id=?",
                    (now(), task_id, self.worker_id),
                )
        finally:
            reset_tenant(token)

    async def _loop(self):
        while not self.stopping:
            if len(self.running) >= self.concurrency:
                await asyncio.wait(tuple(self.running.values()), timeout=0.2, return_when=asyncio.FIRST_COMPLETED)
                continue
            claimed = await asyncio.to_thread(self._claim)
            if self.stopping:
                if claimed:
                    await asyncio.to_thread(self._release_claim, claimed[0]["id"], claimed[1])
                break
            if claimed:
                task, user_id = claimed
                execution = asyncio.create_task(self._execute(task, user_id))
                self.running[task["id"]] = execution
                execution.add_done_callback(lambda _future, task_id=task["id"]: self.running.pop(task_id, None))
                continue
            if self.running:
                await asyncio.wait(tuple(self.running.values()), timeout=2, return_when=asyncio.FIRST_COMPLETED)
            else:
                self._wakeup.clear()
                if self.stopping:
                    break
                try:
                    await asyncio.wait_for(self._wakeup.wait(), timeout=2)
                except TimeoutError:
                    pass

    async def _execute(self, task, user_id):
        token = use_tenant(user_id)
        try:
            with connect() as db:
                row = db.execute("SELECT status FROM tasks WHERE id=?", (task["id"],)).fetchone()
            if not row or row["status"] != "running":
                return
            append_task_event(task["id"], "started", {"attempt": task["attempts"]})
            result = await self.handler(task)
            with connect() as db:
                if db.execute("SELECT status FROM tasks WHERE id=?", (task["id"],)).fetchone()["status"] == "cancelled":
                    return
                db.execute("UPDATE tasks SET status='completed',result=?,error=NULL,lease_until=NULL,worker_id=NULL,updated_at=? WHERE id=?", (json.dumps(result, ensure_ascii=False, default=str), now(), task["id"]))
            append_task_event(task["id"], "completed")
        except asyncio.CancelledError:
            if self.stopping:
                raise
            append_task_event(task["id"], "cancelled")
        except Exception as exc:
            retry = task["attempts"] < task["max_attempts"]
            status = "queued" if retry else "failed"
            available = now() + min(2 ** task["attempts"], 60)
            with connect() as db:
                db.execute("UPDATE tasks SET status=?,error=?,available_at=?,lease_until=NULL,worker_id=NULL,updated_at=? WHERE id=?", (status, str(exc)[:4000], available, now(), task["id"]))
            append_task_event(task["id"], "retrying" if retry else "failed", {"error": str(exc)[:1000]})
        finally:
            self.running.pop(task["id"], None)
            reset_tenant(token)


task_queue = PersistentTaskQueue()
