# src/assethub/core/db/schema.py

from __future__ import annotations

import sqlite3


def initialize_schema(conn: sqlite3.Connection) -> None:
    """
    Create the minimal v0 schema (storage, asset, version, file, tag, asset_tag).

    Stage 6.1: implement schema DDL with idempotent creation.
    This function is safe to call on every startup.
    """

    # Ensure FK constraints are enforced.
    conn.execute("PRAGMA foreign_keys = ON;")

    ddl = """
    CREATE TABLE IF NOT EXISTS schema_version (
        version     INTEGER NOT NULL,
        applied_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
    );

    CREATE TABLE IF NOT EXISTS storage (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        display_name TEXT,
        root_path   TEXT,
        status      TEXT NOT NULL DEFAULT 'OK',
        created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
        UNIQUE(root_path)
    );

    CREATE TABLE IF NOT EXISTS asset (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        slug        TEXT,
        created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
    );

    CREATE TABLE IF NOT EXISTS version (
        id          INTEGER PRIMARY KEY,
        asset_id    INTEGER NOT NULL,
        semver      TEXT NOT NULL,
        created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
        UNIQUE(asset_id, semver),
        FOREIGN KEY(asset_id) REFERENCES asset(id) ON DELETE CASCADE
    );

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

    CREATE TABLE IF NOT EXISTS tag (
        id      INTEGER PRIMARY KEY,
        name    TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS asset_tag (
        asset_id    INTEGER NOT NULL,
        tag_id      INTEGER NOT NULL,
        PRIMARY KEY (asset_id, tag_id),
        FOREIGN KEY(asset_id) REFERENCES asset(id) ON DELETE CASCADE,
        FOREIGN KEY(tag_id) REFERENCES tag(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_version_asset_id ON version(asset_id);
    CREATE INDEX IF NOT EXISTS idx_file_storage_id ON file(storage_id);
    CREATE INDEX IF NOT EXISTS idx_file_version_id ON file(version_id);
    """

    conn.executescript(ddl)

    # ---
    # Schema versioning + migrations
    # ---
    # Stage 7.6.2 introduces storage.display_name and bumps schema version to 2.
    latest_version = 2

    row = conn.execute("SELECT MAX(version) FROM schema_version;").fetchone()
    current = row[0] if row else None

    if current is None:
        # Fresh DB: record the latest schema version.
        conn.execute("INSERT INTO schema_version(version) VALUES (?);", (int(latest_version),))
        conn.commit()
        return

    try:
        current_i = int(current)
    except Exception:
        current_i = 0

    if current_i < 2:
        _migrate_to_v2(conn)

    conn.commit()


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Stage 7.6.2 migration.

    Adds storage.display_name (nullable) and records schema_version 2.
    """
    # Guard against partial/hand-modified DBs.
    cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(storage);").fetchall()]
    if "display_name" not in cols:
        conn.execute("ALTER TABLE storage ADD COLUMN display_name TEXT;")

    conn.execute("INSERT INTO schema_version(version) VALUES (2);")
    conn.commit()
