# src/assethub/core/db/schema.py

from __future__ import annotations

import sqlite3


def initialize_schema(conn: sqlite3.Connection) -> None:
    """
    Create the minimal v0 schema (storage, asset, version, file, tag, asset_tag).

    This will be implemented in a later stage.
    """
    # TODO: implement schema DDL and migrations.
    pass
