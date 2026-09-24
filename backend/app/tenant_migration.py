"""One-time, recoverable assignment of the pre-account store to a GitHub user."""

import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from . import db
from .workspace import BASE_WORKSPACE, tenant_workspace


def migrate_legacy_owner(github_id: str) -> str:
    if not github_id.isdecimal():
        raise ValueError("CODEZZN_LEGACY_OWNER_GITHUB_ID must be a numeric GitHub ID")
    with db.connect(global_db=True) as source:
        row = source.execute("SELECT id FROM users WHERE github_id=?", (github_id,)).fetchone()
        if not row:
            raise RuntimeError("Legacy owner GitHub ID has no matching signed-in account")
        user_id = row["id"]
        destination = db.tenant_db_path(user_id)
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging = destination.with_name("codezzn.db.migrating")
            if staging.exists():
                staging.unlink()
            try:
                with closing(sqlite3.connect(staging)) as private:
                    source.backup(private)
                    # Identities and sessions remain solely in the shared auth database.
                    private.execute("DELETE FROM auth_sessions")
                    private.execute("DELETE FROM oauth_states")
                    private.execute("DELETE FROM users")
                    private.commit()
                    private.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                os.replace(staging, destination)
            finally:
                if staging.exists():
                    staging.unlink()

    root = tenant_workspace(user_id)
    if not root.exists():
        stage = root.with_name(root.name + ".migrating")
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        try:
            for item in BASE_WORKSPACE.iterdir():
                if item.name == ".codezzn-users":
                    continue
                target = stage / item.name
                if item.is_dir():
                    shutil.copytree(item, target, symlinks=True)
                else:
                    shutil.copy2(item, target, follow_symlinks=False)
            os.replace(stage, root)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return user_id
