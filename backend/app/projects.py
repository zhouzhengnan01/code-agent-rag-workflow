"""Tenant-local project and artifact persistence.

Every query uses the tenant selected by the auth middleware. Paths are checked
against that tenant's project directory before being saved or served.
"""

import os
import re
import hashlib
from pathlib import Path

from .db import connect, new_id, now
from .workspace import tenant_workspace


_PROJECT_ID = re.compile(r"^prj_[0-9a-f]{16}$")
_VERSION_CONTENT_LIMIT = 1024 * 1024


def project_root(project_id: str) -> Path:
    if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
        raise ValueError("无效的项目 ID")
    workspace = tenant_workspace()
    projects = workspace / "projects"
    root = projects / project_id
    # Reject tenant-controlled links at every boundary. In particular, a link
    # named projects or <project_id> must not redirect a download to another
    # tenant (or anywhere else on the host).
    if any(path.resolve() != path.absolute() for path in (workspace, projects, root)):
        raise ValueError("项目目录不能使用符号链接")
    return root.resolve()


def list_projects():
    with connect() as db:
        rows = db.execute("SELECT * FROM projects ORDER BY updated_at DESC, id DESC").fetchall()
    return [dict(row) for row in rows]


def get_project(project_id: str):
    project_root(project_id)
    with connect() as db:
        row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return dict(row) if row else None


def create_project(name: str, description: str = ""):
    name = str(name or "").strip()
    description = str(description or "").strip()
    if not name or len(name) > 100:
        raise ValueError("项目名称长度须为 1–100 个字符")
    if len(description) > 2000:
        raise ValueError("项目描述不能超过 2000 个字符")
    project_id, timestamp = new_id("prj"), now()
    root = project_root(project_id)
    root.mkdir(parents=True, exist_ok=False)
    # The isolated executor is an unprivileged 10001:10001 process. Grant only
    # that group access to this tenant's project directory.
    os.chown(root, -1, 10001)
    os.chmod(root, 0o770)
    with connect() as db:
        db.execute(
            "INSERT INTO projects(id,name,description,created_at,updated_at) VALUES(?,?,?,?,?)",
            (project_id, name, description, timestamp, timestamp),
        )
    return get_project(project_id)


def update_project(project_id: str, payload: dict):
    if not get_project(project_id):
        return None
    updates, values = [], []
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name or len(name) > 100:
            raise ValueError("项目名称长度须为 1–100 个字符")
        updates.append("name=?")
        values.append(name)
    if "description" in payload:
        description = str(payload.get("description") or "").strip()
        if len(description) > 2000:
            raise ValueError("项目描述不能超过 2000 个字符")
        updates.append("description=?")
        values.append(description)
    if not updates:
        raise ValueError("没有可更新的项目字段")
    values.extend((now(), project_id))
    with connect() as db:
        db.execute(f"UPDATE projects SET {', '.join(updates)},updated_at=? WHERE id=?", values)
    return get_project(project_id)


def list_artifacts(project_id: str):
    if not get_project(project_id):
        return None
    with connect() as db:
        rows = db.execute(
            "SELECT pa.*, (SELECT MAX(v.version) FROM project_artifact_versions v WHERE v.artifact_id=pa.id) AS version "
            "FROM project_artifacts pa WHERE pa.project_id=? ORDER BY pa.created_at DESC,pa.id DESC",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_artifact(project_id: str, artifact_id: str):
    if not get_project(project_id):
        return None
    with connect() as db:
        row = db.execute(
            "SELECT * FROM project_artifacts WHERE id=? AND project_id=?",
            (artifact_id, project_id),
        ).fetchone()
    return dict(row) if row else None


def list_artifact_versions(project_id: str, artifact_id: str):
    if not get_artifact(project_id, artifact_id):
        return None
    with connect() as db:
        rows = db.execute(
            "SELECT artifact_id,version,turn_id,sha256,size_bytes,created_at,content IS NOT NULL AS downloadable "
            "FROM project_artifact_versions WHERE artifact_id=? ORDER BY version DESC", (artifact_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_artifact_version_content(project_id: str, artifact_id: str, version: int):
    if not get_artifact(project_id, artifact_id):
        return None
    with connect() as db:
        row = db.execute(
            "SELECT content FROM project_artifact_versions WHERE artifact_id=? AND version=?",
            (artifact_id, version),
        ).fetchone()
    return row["content"] if row else None


def artifact_path(project_id: str, path: str) -> Path:
    root = project_root(project_id)
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else root / candidate
    # Preserve the lexical path while checking for links, then resolve to
    # defend against `..` and platform-specific traversal behavior.
    try:
        relative = candidate.absolute().relative_to(root)
    except ValueError as exc:
        raise ValueError("产物路径不在项目目录内") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("产物路径不能使用符号链接")
    target = candidate.resolve()
    if target == root or root not in target.parents:
        raise ValueError("产物路径不在项目目录内")
    return target


def get_turn_project(turn_id: str):
    with connect() as db:
        row = db.execute(
            "SELECT project_id,save_to_project FROM turn_projects WHERE turn_id=?", (turn_id,)
        ).fetchone()
    if row is None:
        return None
    return {"project_id": row["project_id"], "save_to_project": bool(row["save_to_project"])}


def record_artifact(project_id: str, thread_id: str, turn_id: str, path: str, kind: str):
    """Register an existing project file, never a path outside its project."""
    target = artifact_path(project_id, path)
    if not target.is_file():
        raise FileNotFoundError(target)
    relative = target.relative_to(project_root(project_id)).as_posix()
    timestamp = now()
    digest = hashlib.sha256()
    size = target.stat().st_size
    content = bytearray() if size <= _VERSION_CONTENT_LIMIT else None
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            if content is not None:
                content.extend(chunk)
    with connect() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise ValueError("项目不存在")
        if not db.execute("SELECT 1 FROM threads WHERE id=?", (thread_id,)).fetchone():
            raise ValueError("对话不存在")
        db.execute(
            """INSERT INTO project_artifacts(id,project_id,thread_id,turn_id,path,kind,created_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(project_id,path) DO UPDATE SET
                 thread_id=excluded.thread_id,turn_id=excluded.turn_id,
                 kind=excluded.kind,created_at=excluded.created_at""",
            (new_id("art"), project_id, thread_id, turn_id, relative, str(kind or "file")[:40], timestamp),
        )
        db.execute("UPDATE projects SET updated_at=? WHERE id=?", (timestamp, project_id))
        row = db.execute(
            "SELECT * FROM project_artifacts WHERE project_id=? AND path=?", (project_id, relative)
        ).fetchone()
        latest = db.execute(
            "SELECT version,sha256 FROM project_artifact_versions WHERE artifact_id=? ORDER BY version DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        if not latest or latest["sha256"] != digest.hexdigest():
            db.execute(
                "INSERT INTO project_artifact_versions(artifact_id,version,turn_id,sha256,size_bytes,content,created_at) VALUES(?,?,?,?,?,?,?)",
                (row["id"], (latest["version"] + 1) if latest else 1, turn_id, digest.hexdigest(), size,
                 bytes(content) if content is not None else None, timestamp),
            )
    return dict(row)
