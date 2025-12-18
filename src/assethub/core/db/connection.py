# src/assethub/core/db/connection.py

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


_connection: Optional[sqlite3.Connection] = None


def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Return a global SQLite connection for the given database path.

    Schema creation is handled separately (see `assethub.core.db.schema`).
    """
    global _connection

    if _connection is None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(path)
        # Default safety/consistency settings.
        _connection.execute("PRAGMA foreign_keys = ON;")

    return _connection
