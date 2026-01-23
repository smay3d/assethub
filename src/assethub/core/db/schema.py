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


LATEST_SCHEMA_VERSION = 4


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

    # NOTE: This DDL represents the *latest* schema version. Older DBs are
    # upgraded via the migrations below.
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
        storage_id  INTEGER NOT NULL,
        type        TEXT NOT NULL DEFAULT 'generic',
        key         TEXT NOT NULL,
        name        TEXT NOT NULL,
        slug        TEXT,
        created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
        updated_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
        UNIQUE(storage_id, type, key),
        FOREIGN KEY(storage_id) REFERENCES storage(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS version (
        id          INTEGER PRIMARY KEY,
        asset_id    INTEGER NOT NULL,
        label       TEXT NOT NULL,
        sort_key    INTEGER NOT NULL,
        scheme      TEXT NOT NULL DEFAULT 'vNN',
        created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
        updated_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
        UNIQUE(asset_id, sort_key),
        FOREIGN KEY(asset_id) REFERENCES asset(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS version_change_log (
        id          INTEGER PRIMARY KEY,
        version_id  INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        summary     TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
        FOREIGN KEY(version_id) REFERENCES version(id) ON DELETE CASCADE
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
        updated_at      TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
        UNIQUE(storage_id, relative_path),
        FOREIGN KEY(version_id) REFERENCES version(id) ON DELETE SET NULL,
        FOREIGN KEY(storage_id) REFERENCES storage(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS tag (
        id      INTEGER PRIMARY KEY,
        name    TEXT NOT NULL UNIQUE,
        color   TEXT NOT NULL DEFAULT '#808080'
    );

    CREATE TABLE IF NOT EXISTS asset_tag (
        asset_id    INTEGER NOT NULL,
        tag_id      INTEGER NOT NULL,
        PRIMARY KEY (asset_id, tag_id),
        FOREIGN KEY(asset_id) REFERENCES asset(id) ON DELETE CASCADE,
        FOREIGN KEY(tag_id) REFERENCES tag(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_file_storage_id ON file(storage_id);
    CREATE INDEX IF NOT EXISTS idx_file_version_id ON file(version_id);
    CREATE INDEX IF NOT EXISTS idx_log_version_id ON version_change_log(version_id);
    """

    conn.executescript(ddl)

    current = get_schema_version(conn)
    if current == 0:
        # Fresh DB: record the latest schema version.
        conn.execute("INSERT INTO schema_version(version) VALUES (?);", (int(LATEST_SCHEMA_VERSION),))
        _ensure_latest_indexes(conn)
        conn.commit()
        return

    # If a DB reports a version newer than this code knows, do not attempt to "downgrade".
    if int(current) >= int(LATEST_SCHEMA_VERSION):
        conn.commit()
        return

    _apply_migrations(conn, from_version=int(current), to_version=int(LATEST_SCHEMA_VERSION))
    _ensure_latest_indexes(conn)
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


def _ensure_latest_indexes(conn: sqlite3.Connection) -> None:
    """Ensure indexes exist for the current on-disk schema.

    Important: `initialize_schema` runs its DDL before migrations, so we must
    *not* create indexes that reference columns absent in older schemas.
    """
    # Asset (v3)
    try:
        asset_cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(asset);").fetchall()]
        if all(c in asset_cols for c in ("storage_id", "type", "key")):
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uidx_asset_storage_type_key ON asset(storage_id, type, key);"
            )
    except Exception:
        pass

    # Version: v2 has (asset_id, semver), v3 has (asset_id, sort_key).
    try:
        version_cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(version);").fetchall()]
        if "sort_key" in version_cols:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_version_asset_sort ON version(asset_id, sort_key);")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uidx_version_asset_sort ON version(asset_id, sort_key);"
            )
        else:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_version_asset_id ON version(asset_id);")
    except Exception:
        pass


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate to schema v2.

    v2 adds `storage.display_name` (nullable) and records schema_version 2.
    """
    # Guard against partial/hand-modified DBs.
    cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(storage);").fetchall()]
    if "display_name" not in cols:
        conn.execute("ALTER TABLE storage ADD COLUMN display_name TEXT;")

    _record_schema_version(conn, 2)


def _migrate_to_v3(conn: sqlite3.Connection) -> None:
    """Migrate to schema v3.

    v3 introduces:
      - storage-scoped assets with stable identity fields (storage_id, type, key)
      - versions with monotonic sort_key + display label (label, sort_key, scheme)
      - version_change_log for per-action accountability
      - file.updated_at for auditing

    Notes:
      - Migration is forward-only and idempotent.
      - SQLite cannot add NOT NULL + UNIQUE constraints to existing tables without
        rebuilds, so v3 rebuilds `asset` and `version`.
    """

    # Rebuild operations are easiest with FK checks disabled, then restored.
    conn.execute("PRAGMA foreign_keys = OFF;")

    # Ensure an Unmanaged storage row exists so we can backfill legacy assets.
    unmanaged_id = _ensure_unmanaged_storage_row(conn)

    _rebuild_asset_table_v3(conn, unmanaged_storage_id=unmanaged_id)
    _rebuild_version_table_v3(conn)
    _ensure_version_change_log_table(conn)
    _ensure_file_updated_at(conn)

    conn.execute("PRAGMA foreign_keys = ON;")
    _record_schema_version(conn, 3)


def _migrate_to_v4(conn: sqlite3.Connection) -> None:
    """Migrate to schema v4.

    v4 adds semantic tag colors:
      - tag.color TEXT NOT NULL DEFAULT '#808080'

    Migration is forward-only and idempotent.
    """

    cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(tag);").fetchall()]
    if "color" not in cols:
        conn.execute("ALTER TABLE tag ADD COLUMN color TEXT NOT NULL DEFAULT '#808080';")

    _record_schema_version(conn, 4)


def _ensure_unmanaged_storage_row(conn: sqlite3.Connection) -> int:
    """Return the Unmanaged storage id, creating the row if missing."""
    row = conn.execute("SELECT id FROM storage WHERE name=? ORDER BY id LIMIT 1;", ("Unmanaged",)).fetchone()
    if row and row[0] is not None:
        return int(row[0])

    # Create a minimal unmanaged row.
    # root_path is NULL; UNIQUE(root_path) allows multiple NULLs, but we only
    # create this row if no existing Unmanaged name is present.
    conn.execute(
        "INSERT INTO storage(name, display_name, root_path, status) VALUES (?, ?, ?, ?);",
        ("Unmanaged", None, None, "OK"),
    )
    row2 = conn.execute("SELECT id FROM storage WHERE name=? ORDER BY id DESC LIMIT 1;", ("Unmanaged",)).fetchone()
    return int(row2[0])


def _rebuild_asset_table_v3(conn: sqlite3.Connection, *, unmanaged_storage_id: int) -> None:
    """Rebuild asset table to match schema v3."""
    cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(asset);").fetchall()]
    has_v3_cols = all(c in cols for c in ("storage_id", "type", "key", "updated_at"))
    if has_v3_cols:
        # Table already has v3 columns; ensure the uniqueness index exists.
        # (SQLite UNIQUE constraints in CREATE TABLE will exist already, but some
        # hand-modified DBs may lack it.)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uidx_asset_storage_type_key ON asset(storage_id, type, key);"
        )
        return

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS asset_new (
            id          INTEGER PRIMARY KEY,
            storage_id  INTEGER NOT NULL,
            type        TEXT NOT NULL DEFAULT 'generic',
            key         TEXT NOT NULL,
            name        TEXT NOT NULL,
            slug        TEXT,
            created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            updated_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(storage_id, type, key),
            FOREIGN KEY(storage_id) REFERENCES storage(id) ON DELETE RESTRICT
        );
        """
    )

    # Copy legacy rows, preserving ids. Backfill storage_id to Unmanaged.
    # Derive key from slug/name; if blank, fallback to 'asset_<id>'.
    if "created_at" in cols and "slug" in cols:
        conn.execute(
            """
            INSERT INTO asset_new(id, storage_id, type, key, name, slug, created_at, updated_at)
            SELECT
                id,
                ?,
                'generic',
                CASE
                    WHEN slug IS NOT NULL AND TRIM(slug) != '' THEN slug
                    WHEN name IS NOT NULL AND TRIM(name) != '' THEN name
                    ELSE 'asset_' || id
                END,
                name,
                slug,
                created_at,
                CURRENT_TIMESTAMP
            FROM asset;
            """,
            (int(unmanaged_storage_id),),
        )
    else:
        # Extremely old / custom DB: copy what we can.
        conn.execute(
            """
            INSERT INTO asset_new(id, storage_id, type, key, name, slug, created_at, updated_at)
            SELECT
                id,
                ?,
                'generic',
                CASE
                    WHEN name IS NOT NULL AND TRIM(name) != '' THEN name
                    ELSE 'asset_' || id
                END,
                name,
                NULL,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM asset;
            """,
            (int(unmanaged_storage_id),),
        )

    conn.executescript(
        """
        DROP TABLE asset;
        ALTER TABLE asset_new RENAME TO asset;
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_asset_storage_type_key ON asset(storage_id, type, key);
        """
    )


def _rebuild_version_table_v3(conn: sqlite3.Connection) -> None:
    """Rebuild version table to match schema v3."""
    cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(version);").fetchall()]
    has_v3_cols = all(c in cols for c in ("label", "sort_key", "scheme", "updated_at"))
    if has_v3_cols:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uidx_version_asset_sort ON version(asset_id, sort_key);"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_version_asset_sort ON version(asset_id, sort_key);")
        return

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS version_new (
            id          INTEGER PRIMARY KEY,
            asset_id    INTEGER NOT NULL,
            label       TEXT NOT NULL,
            sort_key    INTEGER NOT NULL,
            scheme      TEXT NOT NULL DEFAULT 'vNN',
            created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            updated_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(asset_id, sort_key),
            FOREIGN KEY(asset_id) REFERENCES asset(id) ON DELETE CASCADE
        );
        """
    )

    # Copy legacy rows (if any), preserving ids so file.version_id stays valid.
    legacy_rows = []
    try:
        legacy_rows = conn.execute(
            "SELECT id, asset_id, semver, created_at FROM version ORDER BY asset_id, id;"
        ).fetchall()
    except Exception:
        legacy_rows = []

    counters: Dict[int, int] = {}
    for vid, asset_id, semver, created_at in legacy_rows:
        aid = int(asset_id)
        counters[aid] = counters.get(aid, 0) + 1
        sort_key = counters[aid]
        s = "" if semver is None else str(semver).strip()
        label = s if s else f"v{sort_key:02d}"
        created_at_val = None
        if created_at is not None and str(created_at).strip() != "":
            created_at_val = str(created_at)
        conn.execute(
            """
            INSERT INTO version_new(id, asset_id, label, sort_key, scheme, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP);
            """,
            (int(vid), aid, str(label), int(sort_key), "vNN", created_at_val),
        )

    conn.executescript(
        """
        DROP TABLE version;
        ALTER TABLE version_new RENAME TO version;
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_version_asset_sort ON version(asset_id, sort_key);
        CREATE INDEX IF NOT EXISTS idx_version_asset_sort ON version(asset_id, sort_key);
        """
    )


def _ensure_version_change_log_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS version_change_log (
            id          INTEGER PRIMARY KEY,
            version_id  INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            summary     TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            FOREIGN KEY(version_id) REFERENCES version(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_log_version_id ON version_change_log(version_id);
        """
    )


def _ensure_file_updated_at(conn: sqlite3.Connection) -> None:
    cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(file);").fetchall()]
    if "updated_at" not in cols:
        # SQLite may reject non-constant defaults in ALTER TABLE for some builds.
        # We add the column with a constant default, then backfill.
        conn.execute("ALTER TABLE file ADD COLUMN updated_at TEXT NOT NULL DEFAULT '';")
        conn.execute("UPDATE file SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL OR updated_at = '';")

    # Ensure inserts/updates keep updated_at meaningful even for legacy DBs where
    # the column was added without an expression default.
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS trg_file_set_updated_at_insert
        AFTER INSERT ON file
        WHEN NEW.updated_at IS NULL OR NEW.updated_at = ''
        BEGIN
            UPDATE file SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_file_set_updated_at_update
        AFTER UPDATE ON file
        BEGIN
            UPDATE file SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;
        """
    )


_MIGRATIONS: Dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_to_v2,
    3: _migrate_to_v3,
    4: _migrate_to_v4,
}
