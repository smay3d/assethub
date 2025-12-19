# src/assethub/core/db/connection.py

from __future__ import annotations

import sqlite3
from pathlib import Path


def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Open (or create) a SQLite database connection at db_path.

    This function intentionally does NOT cache connections globally.
    The AppContext owns the lifetime of the connection in the running app.

    Schema creation is handled separately (see `assethub.core.db.schema`).
    """
    path = Path(db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    # Default safety/consistency settings.
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn