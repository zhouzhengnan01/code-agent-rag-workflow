"""Tenant-owned browser outputs that remain visible without a project save."""
from pathlib import Path
from .db import connect, new_id, now
from .workspace import tenant_workspace


def safe_file(path):
    lexical_root = tenant_workspace().absolute()
    root = lexical_root.resolve()
    if root != lexical_root: raise ValueError('Tenant workspace cannot use symlinks')
    relative = Path(path)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid conversation artifact path')
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink(): raise ValueError('Conversation artifact cannot use symlinks')
    target = (root / relative).resolve()
    if root not in target.parents or not target.is_file(): raise FileNotFoundError('Conversation artifact not found')
    return target


def public(row):
    value = dict(row)
    target = safe_file(value['path'])
    return {'id': value['id'], 'thread_id': value['thread_id'], 'turn_id': value['turn_id'],
            'kind': value['kind'], 'name': target.name, 'size_bytes': target.stat().st_size,
            'previewable': value['kind'] == 'screenshot' and target.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'},
            'download_url': f"/api/threads/{value['thread_id']}/artifacts/{value['id']}/download"}


def record(thread_id, turn_id, target, kind):
    relative = Path(target).absolute().relative_to(tenant_workspace().resolve()).as_posix()
    safe_file(relative)
    with connect() as db:
        existing = db.execute('SELECT * FROM thread_artifacts WHERE thread_id=? AND turn_id=? AND path=?', (thread_id, turn_id, relative)).fetchone()
        if existing: return public(existing)
        item = {'id': new_id('art'), 'thread_id': thread_id, 'turn_id': turn_id, 'kind': kind, 'path': relative, 'created_at': now()}
        db.execute('INSERT INTO thread_artifacts(id,thread_id,turn_id,kind,path,created_at) VALUES(:id,:thread_id,:turn_id,:kind,:path,:created_at)', item)
    return public(item)


def list_for_thread(thread_id):
    with connect() as db:
        rows = db.execute('SELECT * FROM thread_artifacts WHERE thread_id=? ORDER BY created_at,id', (thread_id,)).fetchall()
    result = []
    for row in rows:
        try: result.append(public(row))
        except (ValueError, FileNotFoundError): pass
    return result


def get(thread_id, artifact_id):
    with connect() as db:
        row = db.execute('SELECT * FROM thread_artifacts WHERE thread_id=? AND id=?', (thread_id, artifact_id)).fetchone()
    if not row: raise FileNotFoundError('Conversation artifact not found')
    return safe_file(row['path'])
