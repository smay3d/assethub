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
    assert "version_change_log" in tables
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
    assert row[0] == 3


def test_initialize_schema_migrates_v1_to_v3(tmp_path) -> None:
    """Migrating an existing v1-era DB should reach the latest schema."""
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

    # v3 tables/cols should exist.
    asset_cols = [r[1] for r in conn.execute("PRAGMA table_info(asset);").fetchall()]
    assert "storage_id" in asset_cols
    assert "type" in asset_cols
    assert "key" in asset_cols
    assert "updated_at" in asset_cols

    version_cols = [r[1] for r in conn.execute("PRAGMA table_info(version);").fetchall()]
    assert "label" in version_cols
    assert "sort_key" in version_cols
    assert "scheme" in version_cols
    assert "updated_at" in version_cols

    file_cols = [r[1] for r in conn.execute("PRAGMA table_info(file);").fetchall()]
    assert "updated_at" in file_cols

    tables = _get_tables(conn)
    assert "version_change_log" in tables

    row = conn.execute("SELECT MAX(version) FROM schema_version;").fetchone()
    assert row is not None
    assert row[0] == 3


def test_initialize_schema_migrates_v2_to_v3_and_preserves_ids(tmp_path) -> None:
    """v2 -> v3 rebuilds should preserve ids (file.version_id stability)."""
    db_path = tmp_path / "assethub_test.sqlite3"
    conn = sqlite3.connect(db_path)

    # Simulate a v2 DB (pre-v3 asset/version/file shape).
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;

        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER NOT NULL,
            applied_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        );
        INSERT INTO schema_version(version) VALUES (2);

        CREATE TABLE IF NOT EXISTS storage (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            display_name TEXT,
            root_path   TEXT,
            status      TEXT NOT NULL DEFAULT 'OK',
            created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(root_path)
        );
        INSERT INTO storage(id, name, root_path, status) VALUES (1, 'Unmanaged', NULL, 'OK');

        CREATE TABLE IF NOT EXISTS asset (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            slug        TEXT,
            created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        );
        INSERT INTO asset(id, name, slug) VALUES (1, 'Test Asset', 'test_asset');

        CREATE TABLE IF NOT EXISTS version (
            id          INTEGER PRIMARY KEY,
            asset_id    INTEGER NOT NULL,
            semver      TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(asset_id, semver),
            FOREIGN KEY(asset_id) REFERENCES asset(id) ON DELETE CASCADE
        );
        INSERT INTO version(id, asset_id, semver) VALUES (5, 1, '1.0.0');

        CREATE TABLE IF NOT EXISTS file (
            id              INTEGER PRIMARY KEY,
            version_id      INTEGER,
            storage_id      INTEGER NOT NULL,
            relative_path   TEXT NOT NULL,
            integrity_state TEXT NOT NULL DEFAULT 'OK',
            size_bytes      INTEGER,
            mtime_unix      REAL,
            created_at      TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(storage_id, relative_path),
            FOREIGN KEY(version_id) REFERENCES version(id) ON DELETE SET NULL,
            FOREIGN KEY(storage_id) REFERENCES storage(id) ON DELETE RESTRICT
        );
        INSERT INTO file(id, version_id, storage_id, relative_path, integrity_state) VALUES (9, 5, 1, 'foo/bar.txt', 'OK');
        """
    )
    conn.commit()

    initialize_schema(conn)

    # Asset id preserved + v3 columns exist.
    row = conn.execute(
        "SELECT id, storage_id, type, key, name FROM asset WHERE id=1;"
    ).fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] == 1  # Unmanaged
    assert row[2] == 'generic'
    assert row[3] == 'test_asset'
    assert row[4] == 'Test Asset'

    # Version id preserved and mapped.
    row = conn.execute(
        "SELECT id, asset_id, label, sort_key, scheme FROM version WHERE id=5;"
    ).fetchone()
    assert row is not None
    assert row[0] == 5
    assert row[1] == 1
    assert row[2] == '1.0.0'
    assert row[3] == 1
    assert row[4] == 'vNN'

    # File still points at the same version id.
    row = conn.execute("SELECT version_id FROM file WHERE id=9;").fetchone()
    assert row is not None
    assert row[0] == 5

    # v3 bookkeeping.
    row = conn.execute("SELECT MAX(version) FROM schema_version;").fetchone()
    assert row is not None
    assert row[0] == 3
