# src/assethub/core/db/schema.py

"""SQLite schema and migrations.

`initialize_schema()` is safe to call on every startup. It:

1) Ensures tables/indices exist.
2) Applies forward-only migrations (monotonic, idempotent).
3) Records applied schema versions in the `schema_version` table.

Migration pattern:
  - Add a new `_migrate_to_vN()` function.
  - Register it in `_MIGRATIONS`.
  - Bump `LATEST_SCHEMA_VERSION`.

Notes:
  - A "file record" refers to a row in the `file` table.
  - A "file on disk" refers to the actual filesystem entry.
"""

from __future__ import annotations

import sqlite3
from typing import Callable, Dict


LATEST_SCHEMA_VERSION = 2


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version as recorded in `schema_version`.

    Returns:
        Highest recorded version, or 0 if the version table is empty/missing.
    """
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version;").fetchone()
    except Exception:
        return 0
    if not row or row[0] is None:
        return 0
    try:
        return int(row[0])
    except Exception:
        return 0


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Ensure the DB schema exists and is migrated to the latest version."""

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

    current = get_schema_version(conn)
    if current == 0:
        # Fresh DB: record the latest schema version.
        conn.execute("INSERT INTO schema_version(version) VALUES (?);", (int(LATEST_SCHEMA_VERSION),))
        conn.commit()
        return

    # If a DB reports a version newer than this code knows, do not attempt to "downgrade".
    if int(current) >= int(LATEST_SCHEMA_VERSION):
        conn.commit()
        return

    _apply_migrations(conn, from_version=int(current), to_version=int(LATEST_SCHEMA_VERSION))
    conn.commit()


def _apply_migrations(conn: sqlite3.Connection, *, from_version: int, to_version: int) -> None:
    """Apply registered migrations in order."""
    cur = int(from_version)
    target = int(to_version)
    while cur < target:
        next_v = cur + 1
        fn = _MIGRATIONS.get(next_v)
        if fn is None:
            raise RuntimeError(f"Missing migration for schema v{next_v}")
        fn(conn)
        cur = next_v


def _record_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Record an applied schema version."""
    conn.execute("INSERT INTO schema_version(version) VALUES (?);", (int(version),))


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate to schema v2.

    v2 adds `storage.display_name` (nullable) and records schema_version 2.
    """
    # Guard against partial/hand-modified DBs.
    cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(storage);").fetchall()]
    if "display_name" not in cols:
        conn.execute("ALTER TABLE storage ADD COLUMN display_name TEXT;")

    _record_schema_version(conn, 2)


_MIGRATIONS: Dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_to_v2,
}
