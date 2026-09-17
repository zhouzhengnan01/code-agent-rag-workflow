import asyncio
import json
import uuid

from .db import connect, new_id, now


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

    async def start(self, handler, concurrency=2):
        self.handler = handler
        self.stopping = False
        timestamp = now()
        with connect() as db:
            db.execute("UPDATE tasks SET status='queued',worker_id=NULL,lease_until=NULL,available_at=?,updated_at=? WHERE status='running'", (timestamp, timestamp))
        self.workers = [asyncio.create_task(self._loop(index)) for index in range(max(1, min(int(concurrency), 8)))]

    async def close(self):
        self.stopping = True
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []
        self.running = {}

    async def cancel(self, task_id):
        changed = cancel_task(task_id)
        running = self.running.get(task_id)
        if running and not running.done():
            running.cancel()
        return changed

    def _claim(self):
        timestamp = now()
        with connect() as db:
            row = db.execute("SELECT id FROM tasks WHERE status='queued' AND available_at<=? ORDER BY created_at LIMIT 1", (timestamp,)).fetchone()
            if not row:
                return None
            changed = db.execute(
                "UPDATE tasks SET status='running',attempts=attempts+1,worker_id=?,lease_until=?,updated_at=? WHERE id=? AND status='queued'",
                (self.worker_id, timestamp + 300, timestamp, row["id"]),
            ).rowcount
        return get_task(row["id"]) if changed else None

    async def _loop(self, _index):
        while not self.stopping:
            task = self._claim()
            if not task:
                await asyncio.sleep(0.35)
                continue
            append_task_event(task["id"], "started", {"attempt": task["attempts"]})
            execution = asyncio.create_task(self.handler(task))
            self.running[task["id"]] = execution
            try:
                result = await execution
                with connect() as db:
                    if db.execute("SELECT status FROM tasks WHERE id=?", (task["id"],)).fetchone()["status"] == "cancelled":
                        continue
                    db.execute("UPDATE tasks SET status='completed',result=?,error=NULL,lease_until=NULL,worker_id=NULL,updated_at=? WHERE id=?", (json.dumps(result, ensure_ascii=False, default=str), now(), task["id"]))
                append_task_event(task["id"], "completed")
            except asyncio.CancelledError:
                if self.stopping:
                    execution.cancel()
                    raise
                append_task_event(task["id"], "cancelled")
                continue
            except Exception as exc:
                retry = task["attempts"] < task["max_attempts"]
                status = "queued" if retry else "failed"
                available = now() + min(2 ** task["attempts"], 60)
                with connect() as db:
                    db.execute("UPDATE tasks SET status=?,error=?,available_at=?,lease_until=NULL,worker_id=NULL,updated_at=? WHERE id=?", (status, str(exc)[:4000], available, now(), task["id"]))
                append_task_event(task["id"], "retrying" if retry else "failed", {"error": str(exc)[:1000]})
            finally:
                self.running.pop(task["id"], None)


task_queue = PersistentTaskQueue()
