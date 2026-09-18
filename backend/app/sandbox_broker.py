"""Trusted, single-instance Docker control plane. Never expose its port publicly.

Only this process sees the Docker socket. Requests cannot select mounts, images,
users, network or resource limits. One command = one disposable Linux container.
"""
import contextlib
import hmac
import http.client
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlencode

ACTIVE = {"queued", "creating", "running"}
LABEL = "io.codezzn.sandbox.instance"
TASK_LABEL = "io.codezzn.sandbox.task"
DEADLINE_LABEL = "io.codezzn.sandbox.deadline"


class DockerError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(f"Docker HTTP {status}: {message[:500]}")
        self.status = status


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect("/var/run/docker.sock")


class Docker:
    def request(self, method, path, body=None, raw=False, limit=2 * 1024 * 1024):
        conn = UnixConnection("localhost", timeout=15)
        try:
            data = json.dumps(body).encode() if body is not None else None
            conn.request(method, "/v1.41" + path, body=data, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            data = response.read(limit + 1)
            if response.status >= 400:
                raise DockerError(response.status, data.decode(errors="replace"))
            if raw:
                return data[:limit]
            if len(data) > limit:
                raise RuntimeError("Docker control response exceeds size limit")
            return json.loads(data) if data else {}
        finally:
            conn.close()


class Config:
    def __init__(self):
        self.instance = os.getenv("CODEZZN_SANDBOX_INSTANCE", "codezzn-local")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", self.instance):
            raise ValueError("Invalid sandbox instance label")
        self.image = os.getenv("CODEZZN_SANDBOX_IMAGE", "codezzn-sandbox:local")
        self.workspace_container = os.getenv("CODEZZN_SANDBOX_WORKSPACE_CONTAINER", "codezzn")
        self.token = os.getenv("CODEZZN_SANDBOX_TOKEN", "")
        if len(self.token) < 32:
            raise ValueError("CODEZZN_SANDBOX_TOKEN must contain at least 32 characters")
        self.cpus = float(os.getenv("CODEZZN_SANDBOX_CPUS", "1"))
        self.memory = int(os.getenv("CODEZZN_SANDBOX_MEMORY_MB", "512")) * 1024 * 1024
        self.pids = int(os.getenv("CODEZZN_SANDBOX_PIDS", "64"))
        self.timeout = int(os.getenv("CODEZZN_SANDBOX_TIMEOUT", "60"))
        self.output_limit = 20000
        self.max_active = 4
        self.allow_git_network = os.getenv("CODEZZN_SANDBOX_GIT_NETWORK", "false").lower() == "true"
        if not math.isfinite(self.cpus) or not 0.1 <= self.cpus <= 8:
            raise ValueError("CPUs must be between 0.1 and 8")
        if not 64 * 1024 * 1024 <= self.memory <= 8 * 1024**3 or not 8 <= self.pids <= 512 or not 1 <= self.timeout <= 600:
            raise ValueError("Invalid sandbox resource bounds")
        self.state = os.getenv("CODEZZN_SANDBOX_STATE", "/state/tasks.db")


def container_spec(config, task_id, command, mode, mount, deadline, image_id, cwd=".", network=False):
    if mode not in ("read-only", "workspace-write"):
        raise ValueError("Only read-only and workspace-write modes are supported")
    return {
        "Image": image_id, "User": "10001:10001", "WorkingDir": "/workspace" + ("/" + cwd if cwd != "." else ""),
        # PID 1 owns an independent deadline even if the broker is stopped.
        "Entrypoint": ["python", "-c", "import subprocess,sys\ntry:\n r=subprocess.run(['/bin/sh','-c',sys.argv[2]],timeout=float(sys.argv[1]));sys.exit(r.returncode)\nexcept subprocess.TimeoutExpired:\n sys.exit(124)"],
        "Cmd": [str(max(0.1, deadline - time.time())), command], "Tty": False,
        "Env": ["PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp", "LANG=C.UTF-8"],
        "Labels": {LABEL: config.instance, TASK_LABEL: task_id, DEADLINE_LABEL: str(deadline)},
        "HostConfig": {
            "Mounts": [{**mount, "Target": "/workspace", "ReadOnly": mode == "read-only"}],
            "NetworkMode": "bridge" if network else "none", "ReadonlyRootfs": True, "Privileged": False,
            "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
            "NanoCpus": int(config.cpus * 1_000_000_000), "Memory": config.memory,
            "MemorySwap": config.memory, "PidsLimit": config.pids,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=67108864,mode=1777"},
            "Ulimits": [{"Name": "nofile", "Soft": 256, "Hard": 256}, {"Name": "core", "Soft": 0, "Hard": 0}],
            "LogConfig": {"Type": "json-file", "Config": {"max-size": "1m", "max-file": "1"}},
            "RestartPolicy": {"Name": "no"}, "AutoRemove": False,
        },
    }


def decode_logs(raw, limit):
    parts, offset = [], 0
    while offset + 8 <= len(raw):
        size = int.from_bytes(raw[offset + 4:offset + 8], "big")
        if raw[offset] not in (0, 1, 2):
            break
        parts.append(raw[offset + 8:min(offset + 8 + size, len(raw))])
        offset += 8 + size
    return b"".join(parts)[:limit].decode("utf-8", errors="replace")


class Broker:
    def __init__(self, config, docker=None):
        self.config, self.docker = config, docker or Docker()
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.running = {}
        self.recovery_error = None
        Path(config.state).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, name TEXT NOT NULL, container_id TEXT, status TEXT NOT NULL, mode TEXT NOT NULL, created REAL NOT NULL, deadline REAL NOT NULL, exit_code INTEGER, output TEXT DEFAULT '', error TEXT DEFAULT '', cleanup_pending INTEGER DEFAULT 1)")

    @contextlib.contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(self.config.state, timeout=15)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            finally:
                db.close()

    def update(self, task_id, **values):
        with self.db() as db:
            db.execute("UPDATE tasks SET " + ",".join(key + "=?" for key in values) + " WHERE id=?", [*values.values(), task_id])

    def get(self, task_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        result = dict(row)
        result["task_id"] = result["id"]
        result["cleanup_pending"] = bool(result["cleanup_pending"])
        return result

    def tasks(self):
        with self.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM tasks ORDER BY created DESC LIMIT 100")]

    def workspace(self):
        source = self.docker.request("GET", "/containers/" + quote(self.config.workspace_container, safe="") + "/json")
        matches = [m for m in source.get("Mounts", []) if m.get("Destination") == "/workspace"]
        if len(matches) != 1 or matches[0].get("Type") not in ("bind", "volume"):
            raise RuntimeError("Main container must have exactly one bind/volume at /workspace")
        item = matches[0]
        mount_source = item.get("Name") if item["Type"] == "volume" else item.get("Source")
        if not mount_source or mount_source in ("/", "/var/run", "/var/run/docker.sock"):
            raise RuntimeError("Refusing unsafe workspace source")
        if item["Type"] == "bind":
            # Docker recursive bind mounts can otherwise inherit nested host mounts.
            return {"Type": "bind", "Source": mount_source, "BindOptions": {"Propagation": "rprivate", "NonRecursive": True}}
        return {"Type": "volume", "Source": mount_source, "VolumeOptions": {"NoCopy": True}}

    def image(self):
        info = self.docker.request("GET", "/images/" + quote(self.config.image, safe="") + "/json")
        if info.get("Os") != "linux":
            raise RuntimeError("Sandbox requires Linux containers")
        if info.get("Config", {}).get("Volumes"):
            raise RuntimeError("Sandbox image must not declare extra VOLUME mounts")
        if info.get("Config", {}).get("Healthcheck"):
            raise RuntimeError("Sandbox image must not define a healthcheck")
        return info["Id"]

    def submit(self, payload):
        if self.stop.is_set():
            raise RuntimeError("Broker is stopping")
        if set(payload) - {"id", "command", "mode", "cwd", "network"}:
            raise ValueError("Unknown fields; container policy is administrator-controlled")
        task_id, command, mode = payload.get("id"), payload.get("command"), payload.get("mode", "read-only")
        cwd = str(payload.get("cwd") or ".").replace("\\", "/")
        network = bool(payload.get("network", False))
        if not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-f]{32}", task_id):
            raise ValueError("Invalid task id")
        if not isinstance(command, str) or not command.strip() or len(command.encode()) > 32768 or "\x00" in command:
            raise ValueError("Invalid command")
        if mode not in ("read-only", "workspace-write"):
            raise ValueError("Unsupported sandbox mode")
        if network and not self.config.allow_git_network:
            raise ValueError("Networked Git is disabled by CODEZZN_SANDBOX_GIT_NETWORK")
        if cwd.startswith("/") or cwd == ".." or any(part in ("", "..") for part in cwd.split("/")):
            if cwd != ".": raise ValueError("Invalid workspace cwd")
        with self.lock:
            # Fail closed while leftovers cannot be reconciled.
            if self.recovery_error:
                raise RuntimeError("Sandbox recovery pending: " + self.recovery_error)
            with self.db() as db:
                pending = db.execute("SELECT COUNT(*) FROM tasks WHERE cleanup_pending=1 AND status NOT IN ('queued','creating','running')").fetchone()[0]
            if pending:
                raise RuntimeError("Unreclaimed containers block new execution")
            if len(self.running) >= self.config.max_active:
                raise RuntimeError("Sandbox concurrent task limit reached")
            now = time.time()
            name = "codezzn-" + self.config.instance + "-" + task_id
            with self.db() as db:
                db.execute("INSERT INTO tasks(id,name,status,mode,created,deadline) VALUES(?,?,?,?,?,?)",
                           (task_id, name, "queued", mode, now, now + self.config.timeout))
            cancel = threading.Event()
            thread = threading.Thread(target=self.execute, args=(task_id, command, cancel, cwd, network), daemon=True)
            self.running[task_id] = (thread, cancel)
            thread.start()
        return self.get(task_id)

    def remove(self, name):
        try:
            self.docker.request("DELETE", "/containers/" + quote(name, safe="") + "?force=true&v=true")
            return True
        except DockerError as exc:
            if exc.status == 404:
                return True
            raise

    def execute(self, task_id, command, cancel, cwd=".", network=False):
        row = self.get(task_id)
        status, error, output, exit_code = "failed", "", "", None
        try:
            self.update(task_id, status="creating")
            mount, image_id = self.workspace(), self.image()
            if cancel.is_set():
                status = "cancelled"
                return
            spec = container_spec(self.config, task_id, command, row["mode"], mount, row["deadline"], image_id, cwd, network)
            created = self.docker.request("POST", "/containers/create?" + urlencode({"name": row["name"]}), spec)
            self.update(task_id, container_id=created["Id"])
            if created.get("Warnings"):
                raise RuntimeError("Docker refused full policy enforcement: " + str(created["Warnings"]))
            # Check cancellation/deadline before executing any user code.
            if cancel.is_set() or time.time() >= row["deadline"]:
                status = "cancelled" if cancel.is_set() else "timed_out"
                return
            self.docker.request("POST", "/containers/" + row["name"] + "/start")
            self.update(task_id, status="running")
            while True:
                if cancel.is_set() or self.stop.is_set():
                    status = "cancelled"
                    break
                if time.time() >= row["deadline"]:
                    status = "timed_out"
                    break
                info = self.docker.request("GET", "/containers/" + row["name"] + "/json")
                if not info["State"]["Running"]:
                    exit_code = info["State"]["ExitCode"]
                    status = "failed" if info["State"].get("OOMKilled") else ("timed_out" if exit_code == 124 else "completed")
                    error = "Memory limit exceeded" if info["State"].get("OOMKilled") else ""
                    raw = self.docker.request("GET", "/containers/" + row["name"] + "/logs?stdout=true&stderr=true&tail=1000", raw=True, limit=131072)
                    output = decode_logs(raw, self.config.output_limit)
                    break
                cancel.wait(0.2)
        except Exception as exc:
            error = str(exc)
        finally:
            pending = True
            try:
                pending = not self.remove(row["name"])
            except Exception as exc:
                error += "; cleanup pending: " + str(exc)
                self.recovery_error = "Cleanup pending: " + str(exc)
            self.update(task_id, status=status, error=error, output=output, exit_code=exit_code, cleanup_pending=int(pending))
            with self.lock:
                self.running.pop(task_id, None)

    def cancel(self, task_id):
        with self.lock:
            self.get(task_id)
            running = self.running.get(task_id)
            if running:
                running[1].set()
        return self.get(task_id)

    def recover(self):
        """Run at startup and every 2 seconds; never prune unrelated containers."""
        try:
            filters = json.dumps({"label": [LABEL + "=" + self.config.instance]})
            containers = self.docker.request("GET", "/containers/json?all=true&" + urlencode({"filters": filters}))
            for container in containers:
                labels = container.get("Labels", {})
                task_id = labels.get(TASK_LABEL)
                if labels.get(LABEL) != self.config.instance or not re.fullmatch(r"[0-9a-f]{32}", task_id or ""):
                    continue
                with self.lock:
                    active = task_id in self.running
                    expired = float(labels.get(DEADLINE_LABEL, "0")) <= time.time()
                    if not active or expired:
                        if active:
                            self.running[task_id][1].set()
                        self.remove(container["Id"])
            with self.db() as db:
                rows = [dict(row) for row in db.execute("SELECT * FROM tasks WHERE cleanup_pending=1 OR status IN ('queued','creating','running')")]
            for row in rows:
                with self.lock:
                    if row["id"] in self.running:
                        continue
                    self.remove(row["name"])
                    self.update(row["id"], status="interrupted" if row["status"] in ACTIVE else row["status"], cleanup_pending=0)
            self.recovery_error = None
        except Exception as exc:
            self.recovery_error = str(exc)

    def reap(self):
        while not self.stop.wait(2):
            self.recover()

    def close(self):
        self.stop.set()
        with self.lock:
            tasks = list(self.running.values())
            for _, cancel in tasks:
                cancel.set()
        for thread, _ in tasks:
            thread.join(timeout=35)
        self.recover()


def handler_for(broker):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No request bodies, commands, or auth tokens in access logs.

        def respond(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def dispatch(self):
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + broker.config.token):
                return self.respond(401, {"error": "Unauthorized"})
            try:
                if self.command == "GET" and self.path == "/tasks":
                    return self.respond(200, {"data": broker.tasks()})
                if self.command == "GET" and self.path == "/health":
                    broker.image()
                    broker.workspace()
                    return self.respond(200, {"ready": broker.recovery_error is None, "recovery_error": broker.recovery_error, "tasks": broker.tasks(), "policy": {"network": "git-opt-in" if broker.config.allow_git_network else "none", "user": "10001:10001", "cpus": broker.config.cpus, "memory_bytes": broker.config.memory, "pids": broker.config.pids, "timeout": broker.config.timeout}})
                if self.command == "POST" and self.path == "/tasks":
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 65536:
                        return self.respond(413, {"error": "Invalid request size"})
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise ValueError("Object required")
                    return self.respond(202, broker.submit(payload))
                match = re.fullmatch(r"/tasks/([0-9a-f]{32})", self.path)
                if match and self.command in ("GET", "DELETE"):
                    return self.respond(200, broker.get(match[1]) if self.command == "GET" else broker.cancel(match[1]))
                self.respond(404, {"error": "Not found"})
            except KeyError:
                self.respond(404, {"error": "Task not found"})
            except (ValueError, sqlite3.IntegrityError) as exc:
                self.respond(400, {"error": str(exc)})
            except Exception as exc:
                self.respond(503, {"error": str(exc)})

        do_GET = do_POST = do_DELETE = dispatch
    return Handler


def main():
    config = Config()
    Path(config.state).parent.mkdir(parents=True, exist_ok=True)
    # Prevent two brokers sharing the same persistent state from reaping each other.
    import fcntl
    with open(config.state + ".lock", "a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        broker = Broker(config)
        broker.recover()
        threading.Thread(target=broker.reap, daemon=True).start()
        server = ThreadingHTTPServer(("", 8090), handler_for(broker))
        def stop(*_):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            server.serve_forever()
        finally:
            server.server_close()
            broker.close()


if __name__ == "__main__":
    main()
