import contextvars
import os
from pathlib import Path

from .db import current_tenant


BASE_WORKSPACE = Path(os.getenv("CODEZZN_WORKSPACE", os.path.join(os.getcwd(), "workspace"))).resolve()
_current = contextvars.ContextVar("codezzn_workspace", default=None)


def tenant_workspace(user_id=None):
    user_id = current_tenant() if user_id is None else user_id
    return BASE_WORKSPACE / ".codezzn-users" / user_id if user_id else BASE_WORKSPACE


def current_workspace(): return _current.get() or tenant_workspace()
def use_workspace(path): return _current.set(Path(path).resolve())
def reset_workspace(token): _current.reset(token)


def sandbox_cwd():
    root = current_workspace()
    try: return root.relative_to(tenant_workspace()).as_posix() or "."
    except ValueError: raise ValueError("执行工作区必须位于配置的 workspace 内")
