"""Durable per-task execution roots, with conflict-checked project publication.

All commands still run through the Docker broker. A non-Git project gets a
bounded file snapshot, never the shared canonical directory. Canonical Files
remain in projects/<id>; publication is serialized and checks content hashes.
Task copies and overwritten originals are retained, including after conflicts.
"""
import contextvars
import asyncio
import hashlib
import json
import os
import shlex
import tempfile
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from .projects import project_root
from .sandbox import run_command
from .workspace import tenant_workspace


_current = contextvars.ContextVar("codezzn_coding_workspace", default=None)
_EXCLUDED = {".git", ".codezzn-coding", ".codezzn-execution", ".codezzn-worktrees", ".codezzn-users", ".codezzn-backups", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}
MAX_FILES = 20000
MAX_BYTES = 256 * 1024 * 1024
PREPARE_LOCK_TIMEOUT = 15


class CodingWorkspaceConflict(RuntimeError):
    """A source changed since this task copied/read it; no overwrite allowed."""


def current_coding_workspace():
    return _current.get()


def inspect_workspace(thread_id, turn_id=None, project_id=None):
    """Read an existing task manifest only; never initialize execution state."""
    if not thread_id:
        return None
    if project_id:
        project_root(project_id)  # validate the project boundary
    folder = _inside(tenant_workspace() / ".codezzn-coding")
    if not folder.is_dir():
        return None
    candidates = []
    for path in folder.glob("*/metadata.json"):
        try:
            path = _inside(path)
            item = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(item, dict):
                continue
            if item.get("thread_id") != thread_id:
                continue
            if turn_id and item.get("turn_id") != turn_id:
                continue
            if project_id and item.get("project_id") != project_id:
                continue
            workspace_path(item)
            candidates.append((path.stat().st_mtime_ns, item))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if not candidates:
        return None
    item = max(candidates, key=lambda value: value[0])[1]
    return {key: item.get(key) for key in ("owner", "task_id", "thread_id", "turn_id", "project_id", "source", "path", "mode", "branch", "limitations")}


def use_coding_workspace(item):
    if item is not None:
        workspace_path(item)  # validate before selecting any stored path
    return _current.set(item)


def reset_coding_workspace(token):
    _current.reset(token)


def _inside(path):
    base = tenant_workspace().absolute()
    path = Path(path).absolute()
    try:
        parts = path.relative_to(base).parts
    except ValueError as exc:
        raise ValueError("编码工作区必须位于当前用户工作区") from exc
    current = base
    for part in (None, *parts):
        if part:
            current /= part
        if current.is_symlink() or current.resolve() != current.absolute():
            raise ValueError("编码工作区不能经过符号链接")
    return path.resolve()


def workspace_path(item):
    return _inside(tenant_workspace() / item["path"])


def logical_root(root):
    """Stable thread/project engineering scope without changing execution cwd.

    Only an exact execution root backed by this tenant's private manifest may
    resolve to a canonical project. Arbitrary paths and other tenants cannot
    select another project's state/checkpoints by forging a directory name.
    """
    candidate = Path(root).absolute()
    base = tenant_workspace().absolute()
    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        if ".codezzn-execution" in candidate.parts:
            raise PermissionError("不能读取其他用户的任务工程作用域") from exc
        return candidate.resolve()
    if not relative.parts or relative.parts[0] != ".codezzn-execution":
        return candidate.resolve()
    candidate = _inside(candidate)
    if len(relative.parts) != 2:
        raise ValueError("工程作用域必须是完整任务执行根")
    identity = relative.parts[1]
    if len(identity) != 32 or any(character not in "0123456789abcdef" for character in identity):
        raise ValueError("无效的任务工程作用域")
    metadata = _inside(base / ".codezzn-coding" / identity / "metadata.json")
    try:
        item = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("任务工程作用域缺少有效清单") from exc
    if not isinstance(item, dict) or not item.get("owner") or workspace_path(item) != candidate:
        raise ValueError("任务工程作用域清单不匹配")
    project_id = item.get("project_id")
    expected_identity = hashlib.sha256(f"{item['owner']}:{project_id or ''}".encode()).hexdigest()[:32]
    source = _inside(project_root(project_id) if project_id else base)
    if identity != expected_identity or item.get("source") != (source.relative_to(base).as_posix() or "."):
        raise ValueError("任务工程作用域项目边界不匹配")
    return source


def inspect_execution_root(root):
    """Reopen a server-owned execution manifest, e.g. a completed background command."""
    candidate = _inside(root)
    relative = candidate.relative_to(tenant_workspace())
    if len(relative.parts) != 2 or relative.parts[0] != '.codezzn-execution':
        return None
    logical_root(candidate)  # validates tenant, identity and project
    return json.loads(_inside(tenant_workspace() / '.codezzn-coding' / relative.parts[1] / 'metadata.json').read_text(encoding='utf-8'))


def execution_project_root(project_id):
    item = current_coding_workspace()
    if item and item.get("project_id") == project_id:
        return workspace_path(item)
    return project_root(project_id)


def _digest(path):
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValueError("编码产物必须是普通文件")
    result = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(block)
            if total > MAX_BYTES:
                raise ValueError("项目文件超过安全快照上限")
            result.update(block)
    return result.hexdigest()


def _inventory(root):
    files, total = {}, 0
    if not root.exists():
        return files
    for directory, names, filenames in os.walk(root, followlinks=False):
        names[:] = sorted(name for name in names if name not in _EXCLUDED)
        for name in names:
            _inside(Path(directory) / name)
        for name in sorted(filenames):
            if name in _EXCLUDED:
                continue
            path = _inside(Path(directory) / name)
            if not path.is_file():
                raise ValueError("项目包含非普通文件，无法安全建立任务快照")
            total += path.stat().st_size
            if len(files) >= MAX_FILES or total > MAX_BYTES:
                raise ValueError("项目超过安全快照上限（20000 文件/256 MiB）；请缩小项目或使用专用开发环境")
            files[path.relative_to(root).as_posix()] = _digest(path)
    return files


def _write_json(path, value):
    _atomic_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"), sandbox=False)


def _atomic_bytes(path, value, sandbox=True):
    path = _inside(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if sandbox:
        _sandbox_access(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=".codezzn-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if sandbox:
            _sandbox_access(path)
        elif os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _sandbox_access(path):
    # Linux broker executes as 10001:10001. Never enable host execution on
    # Windows; Windows is supported for isolated tests and CLI clients only.
    if os.name != "nt":
        os.chown(path, -1, 10001)
        os.chmod(path, 0o770 if path.is_dir() else 0o660)


@contextmanager
def _lock(source):
    key = hashlib.sha256(str(source).encode()).hexdigest()
    directory = _inside(tenant_workspace() / ".codezzn-coding" / "locks")
    directory.mkdir(parents=True, exist_ok=True)
    path = _inside(directory / (key + ".lock"))
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(descriptor).st_size == 0: os.write(descriptor, b'1')
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(descriptor)
        raise CodingWorkspaceConflict('该项目正在初始化或发布；请稍后重试') from exc
    try:
        yield
    finally:
        if os.name == 'nt':
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
        # Keep the inode stable for waiters. The OS releases the advisory lock
        # on crash/exit; unlinking it could let two processes lock different inodes.


@asynccontextmanager
async def _prepare_lock(source):
    # Concurrent child tasks serialize initialization briefly, then each runs
    # independently. Never block the event loop waiting for a filesystem lock.
    deadline = asyncio.get_running_loop().time() + PREPARE_LOCK_TIMEOUT
    while True:
        manager = _lock(source)
        try:
            manager.__enter__()
            break
        except CodingWorkspaceConflict:
            if asyncio.get_running_loop().time() >= deadline:
                raise
            await asyncio.sleep(0.05)
    try:
        yield
    finally:
        manager.__exit__(None, None, None)


async def prepare_coding_workspace(task_id=None, thread_id=None, turn_id=None, project_id=None):
    """Create/reopen one task copy; thread identity alone never reuses a copy.

    Task id takes precedence over turn id, so child tasks on their parent's
    thread are isolated. On resumes the same task/turn id reopens its manifest.
    """
    owner = task_id or turn_id
    if not owner:
        import uuid
        owner = "ephemeral-" + uuid.uuid4().hex
    source = _inside(project_root(project_id) if project_id else tenant_workspace())
    source.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256(f"{owner}:{project_id or ''}".encode()).hexdigest()[:32]
    folder = _inside(tenant_workspace() / ".codezzn-coding" / identity)
    metadata = folder / "metadata.json"
    async with _prepare_lock(source):
        if metadata.exists():
            item = json.loads(_inside(metadata).read_text(encoding="utf-8"))
            if item.get("owner") != owner or item.get("project_id") != project_id or item.get("source") != source.relative_to(tenant_workspace()).as_posix():
                raise ValueError("编码工作区元数据与任务不匹配")
            workspace_path(item)
            return item
        baseline = _inventory(source)
        folder.mkdir(parents=True, exist_ok=True)
        # Keep the journal/expected hashes outside the executor-writable tree.
        # Broker uid 10001 may edit its copy, never forge the CAS baseline.
        if os.name != "nt":
            os.chmod(folder, 0o700)
        root = _inside(tenant_workspace() / ".codezzn-execution" / identity)
        relative_source = source.relative_to(tenant_workspace()).as_posix() or "."
        relative_root = root.relative_to(tenant_workspace()).as_posix()
        # A project's ancestor repository is NOT its own repository. Verify
        # --show-prefix is empty before creating a project-level worktree.
        probe = await run_command("test -z \"$(git -c safe.directory=* rev-parse --show-prefix 2>/dev/null)\" && git -c safe.directory=* rev-parse --verify --quiet 'HEAD^{commit}'", "read-only", relative_source)
        mode = "snapshot"
        branch = None
        if probe.get("exit_code") == 0:
            # Use an absolute sandbox path: run_command's cwd is /workspace/<source>.
            sandbox_root = "/workspace/" + relative_root
            branch = "codezzn/task-" + identity
            result = await run_command("git -c safe.directory=* worktree add -b " + shlex.quote(branch) + " " + shlex.quote(sandbox_root) + " HEAD", "workspace-write", relative_source)
            if result.get("exit_code") != 0:
                raise RuntimeError("无法创建项目隔离 worktree；未回退共享目录: " + str(result.get("output", ""))[-1500:])
            mode = "git-worktree"
        elif root.exists():
            # Incomplete preparation is retained for inspection, never reused.
            raise RuntimeError("任务快照初始化未完成，保留目录；请使用新任务 ID 重试")
        root.mkdir(parents=True, exist_ok=True)
        _sandbox_access(root)
        if mode == "git-worktree":
            for relative in set(_inventory(root)) - set(baseline):
                _inside(root / relative).unlink()
        for relative, digest in baseline.items():
            original = _inside(source / relative)
            content = original.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise CodingWorkspaceConflict("建立快照时源文件发生改变: " + relative)
            _atomic_bytes(root / relative, content)
        item = {"owner": owner, "task_id": task_id, "thread_id": thread_id, "turn_id": turn_id,
                "project_id": project_id, "source": relative_source, "path": relative_root,
                "metadata": metadata.relative_to(tenant_workspace()).as_posix(), "mode": mode,
                "branch": branch, "baseline": baseline,
                "limitations": "依赖/缓存目录不复制；非 Git 快照不提供 Git 历史。只发布普通文件，不发布 .git 或缓存；外部编辑器不受发布锁约束，发布前仍校验哈希。"}
        _write_json(metadata, item)
        return item


def publish_coding_workspace(paths=None):
    """Publish task file changes after hash preflight; conflicts retain copies.

    Returns canonical relative paths, deleted paths and execution mode. A
    revision backup and durable journal are written BEFORE canonical mutation.
    This is cooperative CAS, not an OS filesystem transaction: writers outside
    Codezzn must not edit the same project during publication.
    """
    item = current_coding_workspace()
    if not item:
        return {"published": [], "deleted": [], "mode": "unmanaged"}
    root = workspace_path(item)
    source = _inside(tenant_workspace() / item["source"])
    metadata = _inside(tenant_workspace() / item["metadata"])
    with _lock(source):
        stored = json.loads(metadata.read_text(encoding="utf-8"))
        baseline = stored["baseline"]
        inventory = _inventory(root)
        if paths is None:
            selected = set(baseline) | set(inventory)
        else:
            selected = set()
            if not isinstance(paths, (list, tuple, set)):
                raise ValueError("发布路径必须是数组")
            for value in paths:
                path = Path(str(value))
                if path.is_absolute() or ".." in path.parts or not path.parts or any(part in _EXCLUDED for part in path.parts):
                    raise ValueError("无效的发布路径")
                selected.add(path.as_posix())
        changes = sorted(name for name in selected if baseline.get(name) != inventory.get(name))
        conflicts = [name for name in changes if _digest(_inside(source / name)) != baseline.get(name)]
        if conflicts:
            raise CodingWorkspaceConflict("项目文件已被其他任务或用户修改，拒绝覆盖；任务副本保留于 " + item["path"] + ": " + ", ".join(conflicts))
        published, deleted = [], []
        if changes:
            import uuid
            revision = metadata.parent / "revisions" / uuid.uuid4().hex
            revision.mkdir(parents=True, exist_ok=False)
            journal = {"status": "prepared", "paths": changes, "before": {name: baseline.get(name) for name in changes}}
            for name in changes:
                target = _inside(source / name)
                if target.is_file():
                    _atomic_bytes(revision / "originals" / name, target.read_bytes(), sandbox=False)
            _write_json(revision / "journal.json", journal)
            for name in changes:
                target = _inside(source / name)
                if _digest(target) != baseline.get(name):
                    raise CodingWorkspaceConflict("发布期间检测到并发修改；原文件和任务副本已保留: " + name)
                if name in inventory:
                    content = _inside(root / name).read_bytes()
                    if hashlib.sha256(content).hexdigest() != inventory[name]:
                        raise CodingWorkspaceConflict("任务文件在发布期间变化: " + name)
                    _atomic_bytes(target, content)
                    published.append(name)
                    baseline[name] = inventory[name]
                else:
                    target.unlink()
                    deleted.append(name)
                    baseline.pop(name, None)
                journal["completed"] = published + deleted
                _write_json(revision / "journal.json", journal)
                stored["baseline"] = baseline
                _write_json(metadata, stored)
            journal["status"] = "completed"
            _write_json(revision / "journal.json", journal)
        item["baseline"] = baseline
        return {"published": published, "deleted": deleted, "mode": item["mode"], "workspace": item["path"]}
