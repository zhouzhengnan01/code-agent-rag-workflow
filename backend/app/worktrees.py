import re
import shlex
import logging
from pathlib import Path

from .db import connect, new_id, now
from .sandbox import run_command
from .workspace import tenant_workspace


logger = logging.getLogger(__name__)


def _safe_name(value): return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value))[:80].strip(".-") or new_id("task")


async def ensure_worktree(task_id=None, thread_id=None, base_ref="HEAD"):
    owner = task_id or ("thread-" + str(thread_id))
    with connect() as db:
        # A child task often shares its parent's thread. Task ownership must
        # win; the former OR query silently reused the parent's checkout.
        if task_id:
            row = db.execute("SELECT * FROM worktrees WHERE task_id=? AND status='active' ORDER BY created_at DESC LIMIT 1", (task_id,)).fetchone()
        else:
            row = db.execute("SELECT * FROM worktrees WHERE task_id IS NULL AND thread_id=? AND status='active' ORDER BY created_at DESC LIMIT 1", (thread_id,)).fetchone()
    if row:
        worktree_path(row)
        return dict(row)
    name = _safe_name(owner); relative = f".codezzn-worktrees/{name}"; branch = f"codezzn/{name}"
    worktree_path({"path": relative})
    # git init creates an unborn HEAD. It is a repository, but worktree add
    # cannot branch from HEAD until there is a first commit. Treat it like a
    # non-Git workspace instead of failing every chat before the model runs.
    probe = await run_command(
        "git -c safe.directory=* rev-parse --is-inside-work-tree "
        '&& git -c safe.directory=* rev-parse --verify --quiet "HEAD^{commit}"',
        "read-only",
    )
    if probe.get("exit_code") != 0:
        logger.warning("Git worktree unavailable (no committed HEAD or no repository); task uses tenant workspace without per-task file isolation")
        return None
    result = await run_command(f"git -c safe.directory=* worktree add -b {shlex.quote(branch)} {shlex.quote(relative)} {shlex.quote(base_ref)}", "workspace-write")
    if result.get("exit_code") != 0:
        raise RuntimeError("创建任务 worktree 失败: " + result.get("output", "")[-2000:])
    timestamp, item_id = now(), new_id("wt")
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO worktrees(id,task_id,thread_id,path,branch,base_ref,status,created_at,updated_at) VALUES(?,?,?,?,?,?, 'active',?,?)", (item_id, task_id, thread_id, relative, branch, base_ref, timestamp, timestamp))
        row = db.execute("SELECT * FROM worktrees WHERE path=?", (relative,)).fetchone()
    return dict(row)


def worktree_path(item):
    base = tenant_workspace().absolute()
    relative = Path(item["path"])
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 2 or relative.parts[0] != ".codezzn-worktrees":
        raise ValueError("无效的 worktree 路径")
    current = base
    for part in (None, *relative.parts):
        if part:
            current /= part
        if current.is_symlink() or current.resolve() != current.absolute():
            raise ValueError("worktree 路径不能经过符号链接")
    return current.resolve()


def list_worktrees():
    with connect() as db: return [dict(row) for row in db.execute("SELECT * FROM worktrees ORDER BY created_at DESC").fetchall()]


async def remove_worktree(item_id):
    with connect() as db: row = db.execute("SELECT * FROM worktrees WHERE id=?", (item_id,)).fetchone()
    if not row: return False
    target = worktree_path(row)
    intended = (tenant_workspace() / ".codezzn-worktrees").resolve()
    if target == intended or intended not in target.parents:
        raise ValueError("拒绝清理配置目录以外的 worktree")
    # Do not throw away uncommitted or untracked work. A failed removal must
    # remain active in the database so users can recover/commit their files.
    result = await run_command(f"git -c safe.directory=* worktree remove -- {shlex.quote(row['path'])}", "workspace-write")
    if result.get("exit_code") != 0:
        raise RuntimeError("worktree 未删除（可能含未提交文件），保留全部工作: " + str(result.get("output", ""))[-2000:])
    with connect() as db: db.execute("UPDATE worktrees SET status='removed',updated_at=? WHERE id=?", (now(), item_id))
    return True
