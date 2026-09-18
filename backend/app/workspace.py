import contextvars
import os
from pathlib import Path


BASE_WORKSPACE = Path(os.getenv("CODEZZN_WORKSPACE", os.path.join(os.getcwd(), "workspace"))).resolve()
_current = contextvars.ContextVar("codezzn_workspace", default=BASE_WORKSPACE)


def current_workspace(): return _current.get()
def use_workspace(path): return _current.set(Path(path).resolve())
def reset_workspace(token): _current.reset(token)


def sandbox_cwd():
    root = current_workspace()
    try: return root.relative_to(BASE_WORKSPACE).as_posix() or "."
    except ValueError: raise ValueError("执行工作区必须位于配置的 workspace 内")
