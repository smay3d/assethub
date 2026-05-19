from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def test_latest_schema_version_is_9() -> None:
    from assethub.core.db.schema import LATEST_SCHEMA_VERSION
    assert LATEST_SCHEMA_VERSION == 9


def test_fresh_db_has_checksum_column(tmp_path: Path) -> None:
    from assethub.core.db.schema import initialize_schema, get_schema_version

    conn = sqlite3.connect(str(tmp_path / "fresh.db"))
    initialize_schema(conn)

    assert get_schema_version(conn) == 9
    cols = [r[1] for r in conn.execute("PRAGMA table_info(file);").fetchall()]
    assert "checksum" in cols


def test_checksum_column_is_nullable(tmp_path: Path) -> None:
    from assethub.core.db.schema import initialize_schema

    conn = sqlite3.connect(str(tmp_path / "nullable.db"))
    initialize_schema(conn)

    conn.execute("INSERT INTO storage(name, root_path, status) VALUES ('t', '/t', 'OK')")
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (1, 'a.txt', 'OK')"
    )
    conn.commit()
    row = conn.execute("SELECT checksum FROM file WHERE relative_path='a.txt'").fetchone()
    assert row[0] is None


def test_checksum_index_exists(tmp_path: Path) -> None:
    from assethub.core.db.schema import initialize_schema

    conn = sqlite3.connect(str(tmp_path / "idx.db"))
    initialize_schema(conn)

    idx_names = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='file';"
        ).fetchall()
    ]
    assert "idx_file_checksum" in idx_names


def test_migrate_v8_to_v9(tmp_path: Path) -> None:
    """A DB at v8 (no checksum column) should migrate cleanly to v9."""
    from assethub.core.db.schema import initialize_schema, get_schema_version

    conn = sqlite3.connect(str(tmp_path / "v8.db"))
    # Build a minimal v8 schema without the checksum column.
    conn.executescript(
        """
        CREATE TABLE schema_version (
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        );
        CREATE TABLE storage (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            display_name TEXT,
            root_path TEXT,
            status TEXT NOT NULL DEFAULT 'OK',
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(root_path)
        );
        CREATE TABLE asset (
            id INTEGER PRIMARY KEY,
            storage_id INTEGER NOT NULL,
            type TEXT NOT NULL DEFAULT 'generic',
            key TEXT NOT NULL,
            name TEXT NOT NULL,
            slug TEXT,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(storage_id, type, key),
            FOREIGN KEY(storage_id) REFERENCES storage(id)
        );
        CREATE TABLE version (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            sort_key INTEGER NOT NULL,
            scheme TEXT NOT NULL DEFAULT 'vNN',
            is_discarded INTEGER NOT NULL DEFAULT 0,
            user_label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            FOREIGN KEY(asset_id) REFERENCES asset(id)
        );
        CREATE TABLE version_change_log (
            id INTEGER PRIMARY KEY,
            version_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            FOREIGN KEY(version_id) REFERENCES version(id)
        );
        CREATE TABLE file (
            id INTEGER PRIMARY KEY,
            version_id INTEGER,
            storage_id INTEGER NOT NULL,
            relative_path TEXT NOT NULL,
            integrity_state TEXT NOT NULL DEFAULT 'OK',
            size_bytes INTEGER,
            mtime_unix REAL,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(storage_id, relative_path),
            FOREIGN KEY(storage_id) REFERENCES storage(id)
        );
        CREATE TABLE version_file (
            version_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            added_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            PRIMARY KEY(version_id, file_id)
        );
        CREATE TABLE file_binding (
            file_id INTEGER PRIMARY KEY,
            asset_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        );
        CREATE TABLE storage_scan_exclusion (
            id INTEGER PRIMARY KEY,
            storage_id INTEGER NOT NULL REFERENCES storage(id) ON DELETE CASCADE,
            extension TEXT NOT NULL,
            UNIQUE(storage_id, extension)
        );
        CREATE TABLE tag (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            color TEXT NOT NULL DEFAULT '#808080'
        );
        CREATE TABLE asset_tag (
            asset_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY(asset_id, tag_id)
        );
        INSERT INTO schema_version(version) VALUES (8);
        """
    )
    conn.commit()

    initialize_schema(conn)

    assert get_schema_version(conn) == 9
    cols = [r[1] for r in conn.execute("PRAGMA table_info(file);").fetchall()]
    assert "checksum" in cols
    idx_names = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='file';"
        ).fetchall()
    ]
    assert any("checksum" in n for n in idx_names)
