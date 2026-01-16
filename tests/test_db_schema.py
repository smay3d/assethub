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
    assert row[0] == 2


def test_initialize_schema_migrates_v1_to_v2_adds_display_name(tmp_path) -> None:
    """Stage 7.6.2: migrating an existing DB should add storage.display_name and bump schema."""
    db_path = tmp_path / "assethub_test.sqlite3"
    conn = sqlite3.connect(db_path)

    # Simulate a v1-era DB: storage table exists without display_name and schema_version==1.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER NOT NULL,
            applied_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        );
        INSERT INTO schema_version(version) VALUES (1);

        CREATE TABLE IF NOT EXISTS storage (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            root_path   TEXT,
            status      TEXT NOT NULL DEFAULT 'OK',
            created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(root_path)
        );
        """
    )
    conn.commit()

    # Now run current initializer; it should migrate.
    initialize_schema(conn)

    cols = [r[1] for r in conn.execute("PRAGMA table_info(storage);").fetchall()]
    assert "display_name" in cols

    row = conn.execute("SELECT MAX(version) FROM schema_version;").fetchone()
    assert row is not None
    assert row[0] == 2
