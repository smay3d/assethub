# tests/test_db_schema.py

from __future__ import annotations

import sqlite3

from assethub.core.db.schema import initialize_schema


def _get_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    ).fetchall()
    return {r[0] for r in rows}


def test_initialize_schema_creates_tables(tmp_path) -> None:
    db_path = tmp_path / "assethub_test.sqlite3"
    conn = sqlite3.connect(db_path)

    initialize_schema(conn)

    tables = _get_tables(conn)

    # Core tables
    assert "storage" in tables
    assert "asset" in tables
    assert "version" in tables
    assert "file" in tables
    assert "tag" in tables
    assert "asset_tag" in tables

    # Schema bookkeeping
    assert "schema_version" in tables


def test_initialize_schema_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "assethub_test.sqlite3"
    conn = sqlite3.connect(db_path)

    initialize_schema(conn)
    initialize_schema(conn)  # should not raise

    row = conn.execute("SELECT MAX(version) FROM schema_version;").fetchone()
    assert row is not None
    assert row[0] == 1
