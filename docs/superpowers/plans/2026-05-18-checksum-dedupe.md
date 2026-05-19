# Checksum Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store SHA-256 checksums on file records and surface duplicate files to the user via a Duplicates view in the Library tab and a passive chip in the Files view.

**Architecture:** Add a `checksum TEXT` column to the `file` table (schema v9). The Scanner computes checksums incrementally during scan — only for new or changed files. A new `core/db/duplicates.py` module provides Qt-free query helpers. The UI adds a Duplicates view inside the existing `LibraryTab` stack and a "Duplicate" text indicator in the Tags column of the Files view.

**Tech Stack:** Python 3.x · PySide6 · SQLite · pytest (headless)

**Spec:** `docs/superpowers/specs/2026-05-18-checksum-dedupe-design.md`

---

## File Map

| Action | Path | Purpose |
|---|---|---|
| Modify | `core/db/schema.py` | Add `_migrate_to_v9()`, bump `LATEST_SCHEMA_VERSION` to 9, add `checksum TEXT` to DDL |
| Modify | `core/model/file.py` | Add `checksum: Optional[str] = None` |
| Modify | `core/scanner/scanner.py` | Accept optional `AppLog`; add `files_checksummed`/`files_without_checksum` to `ScanResult`; compute checksums incrementally in `_upsert_file()` |
| Modify | `context.py` | Pass `self.log` to `Scanner` |
| Create | `core/db/duplicates.py` | `DuplicateFile`, `DuplicateGroup` dataclasses; `query_duplicate_groups`, `get_duplicate_file_ids`, `count_checksummed_files` |
| Modify | `core/db/file_records.py` | Add `query_library_files_by_ids(conn, file_ids)` |
| Modify | `ui/models/file_table_model.py` | Add `is_duplicate: bool = False` to `FileRow`; add Tags column |
| Modify | `ui/views/library_tab.py` | Wire Duplicates mode into view switcher; call `get_duplicate_file_ids` in Files refresh |
| Create | `ui/views/duplicates_view.py` | `DuplicateGroupTableModel`, `DuplicatesView` widget |
| Create | `tests/test_schema_v9.py` | Schema migration tests |
| Create | `tests/test_scanner_checksum.py` | Scanner incremental checksum tests |
| Create | `tests/test_db_duplicates.py` | Duplicate query helper tests |
| Modify | `tests/test_library_file_query.py` | Add `query_library_files_by_ids` tests |

---

## Task 1: Schema v9 + File dataclass

**Files:**
- Create: `tests/test_schema_v9.py`
- Modify: `src/assethub/core/db/schema.py`
- Modify: `src/assethub/core/model/file.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schema_v9.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_schema_v9.py -v
```

Expected: FAIL — `LATEST_SCHEMA_VERSION` is 8, `checksum` column missing.

- [ ] **Step 3: Implement schema v9**

In `src/assethub/core/db/schema.py`:

**3a.** Bump the constant:
```python
LATEST_SCHEMA_VERSION = 9
```

**3b.** In the DDL string inside `initialize_schema()`, update the `file` table definition to include `checksum TEXT` after `mtime_unix REAL`:
```sql
    CREATE TABLE IF NOT EXISTS file (
        id              INTEGER PRIMARY KEY,
        version_id      INTEGER,
        storage_id      INTEGER NOT NULL,
        relative_path   TEXT NOT NULL,
        integrity_state TEXT NOT NULL DEFAULT 'OK',
        size_bytes      INTEGER,
        mtime_unix      REAL,
        checksum        TEXT,
        created_at      TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
        updated_at      TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
        UNIQUE(storage_id, relative_path),
        FOREIGN KEY(version_id) REFERENCES version(id) ON DELETE SET NULL,
        FOREIGN KEY(storage_id) REFERENCES storage(id) ON DELETE RESTRICT
    );
```

**3c.** In the DDL, add the checksum index after the existing file indexes:
```sql
    CREATE INDEX IF NOT EXISTS idx_file_checksum ON file(checksum);
```

**3d.** Add the migration function (before `_MIGRATIONS`):
```python
def _migrate_to_v9(conn: sqlite3.Connection) -> None:
    """Migrate to schema v9.

    v9 adds per-file SHA-256 checksums:
      - file.checksum TEXT (nullable, NULL means not yet computed)
      - idx_file_checksum index on file(checksum)

    Migration is forward-only and idempotent.
    """
    cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(file);").fetchall()]
    if "checksum" not in cols:
        conn.execute("ALTER TABLE file ADD COLUMN checksum TEXT;")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_file_checksum ON file(checksum);")
    _record_schema_version(conn, 9)
```

**3e.** Register it in `_MIGRATIONS`:
```python
_MIGRATIONS: Dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_to_v2,
    3: _migrate_to_v3,
    4: _migrate_to_v4,
    5: _migrate_to_v5,
    6: _migrate_to_v6,
    7: _migrate_to_v7,
    8: _migrate_to_v8,
    9: _migrate_to_v9,
}
```

- [ ] **Step 4: Add `checksum` to the File dataclass**

In `src/assethub/core/model/file.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class File:
    id: int
    version_id: int
    storage_id: int
    relative_path: str
    integrity_state: str
    checksum: Optional[str] = None
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_schema_v9.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Run full suite to verify no regression**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_schema_v9.py src/assethub/core/db/schema.py src/assethub/core/model/file.py
git commit -m "feat: schema v9 — add file.checksum column and File.checksum field"
```

---

## Task 2: Scanner — incremental checksumming

**Files:**
- Create: `tests/test_scanner_checksum.py`
- Modify: `src/assethub/core/scanner/scanner.py`
- Modify: `src/assethub/context.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scanner_checksum.py`:

```python
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest


def _make_env(tmp_path: Path):
    """Return (conn, storage_manager, root_path) for a fresh test environment."""
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.storage.roots import StorageManager

    conn = get_connection(str(tmp_path / "test.db"))
    initialize_schema(conn)
    sm = StorageManager(conn)
    sm.ensure_unmanaged_storage()

    root = tmp_path / "root"
    root.mkdir()
    sm.register_root(str(root), name="TestRoot")

    return conn, sm, str(root)


def _make_scanner(conn, sm):
    from assethub.core.scanner.scanner import Scanner
    return Scanner(conn, sm)


def test_new_file_gets_checksum(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "a.txt").write_bytes(b"hello world")

    scanner = _make_scanner(conn, sm)
    result = scanner.scan_all()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='a.txt'").fetchone()
    assert row is not None
    assert row[0] is not None
    assert len(row[0]) == 64  # SHA-256 hex digest length
    assert result.files_checksummed == 1
    assert result.files_without_checksum == 0


def test_unchanged_file_checksum_preserved(tmp_path: Path) -> None:
    """Unchanged file (same size + mtime) must NOT recompute checksum.

    Poison the stored checksum after first scan. If the second scan
    recomputes, the poison disappears — meaning the cache is broken.
    """
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "b.txt").write_bytes(b"stable content")

    scanner = _make_scanner(conn, sm)
    scanner.scan_all()

    # Poison the checksum in the DB.
    conn.execute("UPDATE file SET checksum='poisoned_value' WHERE relative_path='b.txt'")
    conn.commit()

    # Second scan — file is unchanged, poison must survive.
    result = scanner.scan_all()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='b.txt'").fetchone()
    assert row[0] == "poisoned_value", "Checksum was recomputed for an unchanged file"
    assert result.files_checksummed == 0


def test_changed_file_recomputes_checksum(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    f = Path(root) / "c.txt"
    f.write_bytes(b"version 1")

    scanner = _make_scanner(conn, sm)
    scanner.scan_all()

    original = conn.execute("SELECT checksum FROM file WHERE relative_path='c.txt'").fetchone()[0]

    # Overwrite file content and bump mtime.
    time.sleep(0.05)
    f.write_bytes(b"version 2 — different content")
    os.utime(str(f), None)

    result = scanner.scan_all()

    new_checksum = conn.execute("SELECT checksum FROM file WHERE relative_path='c.txt'").fetchone()[0]
    assert new_checksum != original, "Checksum was not updated after file changed"
    assert result.files_checksummed == 1


def test_null_checksum_file_gets_checksummed_on_next_scan(tmp_path: Path) -> None:
    """A file with checksum=NULL but unchanged size/mtime must be checksummed.

    This covers the database-upgrade case: existing records from before v9
    have NULL checksums but valid size/mtime.
    """
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "d.txt").write_bytes(b"needs checksum")

    scanner = _make_scanner(conn, sm)
    scanner.scan_all()

    # Simulate a pre-v9 record by clearing the checksum.
    conn.execute("UPDATE file SET checksum=NULL WHERE relative_path='d.txt'")
    conn.commit()

    result = scanner.scan_all()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='d.txt'").fetchone()
    assert row[0] is not None, "NULL checksum was not filled in on subsequent scan"
    assert result.files_checksummed == 1
    assert result.files_without_checksum == 0


def test_scan_result_without_checksum_count(tmp_path: Path) -> None:
    """files_without_checksum reflects all NULL-checksum file records after scan."""
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "e.txt").write_bytes(b"data")

    scanner = _make_scanner(conn, sm)
    result = scanner.scan_all()

    assert result.files_without_checksum == 0

    # Force a NULL checksum then check the count.
    conn.execute("UPDATE file SET checksum=NULL WHERE relative_path='e.txt'")
    conn.commit()

    # Re-scan: NULL → fills in checksum.
    result2 = scanner.scan_all()
    assert result2.files_without_checksum == 0
    assert result2.files_checksummed == 1


def test_multiple_files_all_get_checksums(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    for i in range(5):
        (Path(root) / f"file{i}.txt").write_bytes(f"content {i}".encode())

    scanner = _make_scanner(conn, sm)
    result = scanner.scan_all()

    assert result.files_checksummed == 5
    assert result.files_without_checksum == 0
    null_count = conn.execute("SELECT COUNT(*) FROM file WHERE checksum IS NULL").fetchone()[0]
    assert null_count == 0
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_scanner_checksum.py -v
```

Expected: FAIL — `ScanResult` has no `files_checksummed` attribute; scanner doesn't compute checksums.

- [ ] **Step 3: Update ScanResult**

In `src/assethub/core/scanner/scanner.py`, update `ScanResult`:

```python
@dataclass(frozen=True)
class ScanResult:
    discovered_paths: List[str]
    files_indexed: int
    files_checksummed: int = 0
    files_without_checksum: int = 0
    canceled: bool = False
```

- [ ] **Step 4: Add imports to scanner.py**

At the top of `src/assethub/core/scanner/scanner.py`, add:

```python
from typing import Callable, List, Optional

from assethub.core.utils.app_log import AppLog
from assethub.core.utils.checksum import sha256_file
```

(Remove any duplicate `Optional` import if already present.)

- [ ] **Step 5: Add `log` parameter to Scanner.__init__**

```python
class Scanner:
    def __init__(
        self,
        conn: sqlite3.Connection,
        storage_manager: StorageManager,
        *,
        log: Optional[AppLog] = None,
    ) -> None:
        self._conn = conn
        self._storage = storage_manager
        self._log = log
```

- [ ] **Step 6: Add `_count_without_checksum` helper**

```python
def _count_without_checksum(self) -> int:
    row = self._conn.execute("SELECT COUNT(*) FROM file WHERE checksum IS NULL;").fetchone()
    return int(row[0]) if row else 0
```

- [ ] **Step 7: Replace `_upsert_file` with checksum-aware version**

Replace the existing `_upsert_file` method entirely:

```python
def _upsert_file(
    self,
    *,
    storage_id: int,
    relative_path: str,
    size_bytes: int,
    mtime_unix: float,
    checksum: Optional[str],
    update_checksum: bool,
) -> None:
    """Upsert a file record.

    When ``update_checksum`` is True the provided ``checksum`` value
    (which may be None if hashing failed) is written to the DB.
    When False the existing checksum column value is left untouched.
    """
    if update_checksum:
        self._conn.execute(
            """
            INSERT INTO file(
                version_id, storage_id, relative_path,
                integrity_state, size_bytes, mtime_unix, checksum
            ) VALUES (NULL, ?, ?, 'OK', ?, ?, ?)
            ON CONFLICT(storage_id, relative_path) DO UPDATE SET
                integrity_state = 'OK',
                size_bytes      = excluded.size_bytes,
                mtime_unix      = excluded.mtime_unix,
                checksum        = excluded.checksum;
            """,
            (storage_id, relative_path, size_bytes, mtime_unix, checksum),
        )
    else:
        self._conn.execute(
            """
            INSERT INTO file(
                version_id, storage_id, relative_path,
                integrity_state, size_bytes, mtime_unix
            ) VALUES (NULL, ?, ?, 'OK', ?, ?)
            ON CONFLICT(storage_id, relative_path) DO UPDATE SET
                integrity_state = 'OK',
                size_bytes      = excluded.size_bytes,
                mtime_unix      = excluded.mtime_unix;
            """,
            (storage_id, relative_path, size_bytes, mtime_unix),
        )
```

- [ ] **Step 8: Update `scan_all` to compute checksums incrementally**

Replace the inner file-processing block (from `abs_path = os.path.join(...)` to the end of the filename loop) with:

```python
                    abs_path = os.path.join(dirpath, fname)

                    # Best-effort: skip if file vanished mid-walk.
                    try:
                        st = os.stat(abs_path)
                    except FileNotFoundError:
                        continue

                    rel = os.path.relpath(abs_path, root.root_path)
                    rel = rel.replace("\\", "/")

                    disk_size = int(st.st_size)
                    disk_mtime = float(st.st_mtime)

                    # Decide whether to (re)compute the checksum.
                    old_row = self._conn.execute(
                        "SELECT size_bytes, mtime_unix, checksum "
                        "FROM file WHERE storage_id=? AND relative_path=?",
                        (root.id, rel),
                    ).fetchone()

                    need_checksum = (
                        old_row is None
                        or old_row[0] != disk_size
                        or old_row[1] != disk_mtime
                        or old_row[2] is None  # NULL → never checksummed
                    )

                    new_checksum: Optional[str] = None
                    if need_checksum:
                        try:
                            new_checksum = sha256_file(abs_path)
                            files_checksummed += 1
                        except OSError:
                            if self._log is not None:
                                self._log.warn(
                                    f"Checksum skipped (unreadable): {abs_path}"
                                )

                    self._upsert_file(
                        storage_id=root.id,
                        relative_path=rel,
                        size_bytes=disk_size,
                        mtime_unix=disk_mtime,
                        checksum=new_checksum,
                        update_checksum=need_checksum,
                    )
                    discovered.append(abs_path)
                    indexed += 1
```

Also add `files_checksummed = 0` near the top of `scan_all`, after `indexed = 0`.

- [ ] **Step 9: Update all `return ScanResult(...)` calls in `scan_all`**

All early-return (canceled) paths and the final return must include the new fields. For canceled returns, compute the without-checksum count:

```python
# Replace each canceled return with:
self._conn.commit()
return ScanResult(
    discovered_paths=discovered,
    files_indexed=indexed,
    files_checksummed=files_checksummed,
    files_without_checksum=self._count_without_checksum(),
    canceled=True,
)
```

Final (non-canceled) return:
```python
self._conn.commit()
return ScanResult(
    discovered_paths=discovered,
    files_indexed=indexed,
    files_checksummed=files_checksummed,
    files_without_checksum=self._count_without_checksum(),
    canceled=False,
)
```

- [ ] **Step 10: Pass log to Scanner in AppContext**

In `src/assethub/context.py`, in `initialize_core_services()`, find:

```python
self.scanner = Scanner(self.db_connection, self.storage_manager)
```

Change it to:

```python
self.scanner = Scanner(self.db_connection, self.storage_manager, log=self.log)
```

- [ ] **Step 11: Run scanner checksum tests**

```
pytest tests/test_scanner_checksum.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 12: Run full test suite**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 13: Commit**

```bash
git add tests/test_scanner_checksum.py src/assethub/core/scanner/scanner.py src/assethub/context.py
git commit -m "feat: compute SHA-256 checksums incrementally during scan"
```

---

## Task 3: DB duplicate query helpers

**Files:**
- Create: `tests/test_db_duplicates.py`
- Create: `src/assethub/core/db/duplicates.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db_duplicates.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _db(tmp_path: Path, name: str = "test.db") -> sqlite3.Connection:
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema

    conn = get_connection(str(tmp_path / name))
    initialize_schema(conn)
    return conn


def _add_storage(conn: sqlite3.Connection, name: str = "Root", path: str = "/root") -> int:
    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, 'OK')", (name, path)
    )
    conn.commit()
    return int(conn.execute("SELECT id FROM storage WHERE name=?", (name,)).fetchone()[0])


def _add_file(
    conn: sqlite3.Connection,
    storage_id: int,
    rel_path: str,
    checksum: str | None = None,
    size_bytes: int = 1000,
) -> int:
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state, size_bytes, checksum)"
        " VALUES (?, ?, 'OK', ?, ?)",
        (storage_id, rel_path, size_bytes, checksum),
    )
    conn.commit()
    return int(
        conn.execute("SELECT id FROM file WHERE relative_path=?", (rel_path,)).fetchone()[0]
    )


# --- query_duplicate_groups ---

def test_empty_db_returns_no_groups(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    assert query_duplicate_groups(conn) == []


def test_unique_checksums_return_no_groups(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    _add_file(conn, sid, "a.txt", checksum="aaa111")
    _add_file(conn, sid, "b.txt", checksum="bbb222")
    assert query_duplicate_groups(conn) == []


def test_two_files_same_checksum_form_one_group(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    _add_file(conn, sid, "a.txt", checksum="shared_hash", size_bytes=500)
    _add_file(conn, sid, "b.txt", checksum="shared_hash", size_bytes=500)

    groups = query_duplicate_groups(conn)
    assert len(groups) == 1
    g = groups[0]
    assert g.checksum == "shared_hash"
    assert g.file_count == 2
    assert len(g.files) == 2


def test_null_checksums_excluded_from_groups(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    _add_file(conn, sid, "a.txt", checksum=None)
    _add_file(conn, sid, "b.txt", checksum=None)
    assert query_duplicate_groups(conn) == []


def test_groups_sorted_by_file_count_desc(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    # 2-copy group
    _add_file(conn, sid, "a1.txt", checksum="dup2", size_bytes=100)
    _add_file(conn, sid, "a2.txt", checksum="dup2", size_bytes=100)
    # 3-copy group
    _add_file(conn, sid, "b1.txt", checksum="dup3", size_bytes=200)
    _add_file(conn, sid, "b2.txt", checksum="dup3", size_bytes=200)
    _add_file(conn, sid, "b3.txt", checksum="dup3", size_bytes=200)

    groups = query_duplicate_groups(conn)
    assert len(groups) == 2
    assert groups[0].file_count == 3  # dup3 first
    assert groups[1].file_count == 2  # dup2 second


def test_groups_with_equal_count_sorted_by_size_desc(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    _add_file(conn, sid, "small1.txt", checksum="small", size_bytes=100)
    _add_file(conn, sid, "small2.txt", checksum="small", size_bytes=100)
    _add_file(conn, sid, "big1.txt", checksum="big", size_bytes=9000)
    _add_file(conn, sid, "big2.txt", checksum="big", size_bytes=9000)

    groups = query_duplicate_groups(conn)
    assert groups[0].files[0].size_bytes == 9000  # big group first


def test_duplicate_file_has_correct_storage_name(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn, name="MyRoot", path="/my/root")
    _add_file(conn, sid, "a.txt", checksum="xyz")
    _add_file(conn, sid, "b.txt", checksum="xyz")

    groups = query_duplicate_groups(conn)
    for f in groups[0].files:
        assert f.storage_name == "MyRoot"


# --- get_duplicate_file_ids ---

def test_get_duplicate_file_ids_returns_only_duplicates(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import get_duplicate_file_ids

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    fid_a = _add_file(conn, sid, "a.txt", checksum="shared")
    fid_b = _add_file(conn, sid, "b.txt", checksum="shared")
    fid_c = _add_file(conn, sid, "c.txt", checksum="unique")

    dup_ids = get_duplicate_file_ids(conn)
    assert isinstance(dup_ids, frozenset)
    assert fid_a in dup_ids
    assert fid_b in dup_ids
    assert fid_c not in dup_ids


def test_get_duplicate_file_ids_empty_db(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import get_duplicate_file_ids

    conn = _db(tmp_path)
    assert get_duplicate_file_ids(conn) == frozenset()


# --- count_checksummed_files ---

def test_count_checksummed_files_mixed(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import count_checksummed_files

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    _add_file(conn, sid, "a.txt", checksum="abc")
    _add_file(conn, sid, "b.txt", checksum=None)
    _add_file(conn, sid, "c.txt", checksum="def")

    checksummed, total = count_checksummed_files(conn)
    assert checksummed == 2
    assert total == 3


def test_count_checksummed_files_empty_db(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import count_checksummed_files

    conn = _db(tmp_path)
    checksummed, total = count_checksummed_files(conn)
    assert checksummed == 0
    assert total == 0
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_db_duplicates.py -v
```

Expected: FAIL — module `assethub.core.db.duplicates` does not exist.

- [ ] **Step 3: Implement `core/db/duplicates.py`**

Create `src/assethub/core/db/duplicates.py`:

```python
"""DB helpers for duplicate file detection.

Queries file records grouped by SHA-256 checksum to identify files with
identical content across storage roots.

Qt-free. All functions accept a sqlite3.Connection and return plain dataclasses.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class DuplicateFile:
    file_id: int
    storage_id: int
    storage_name: str
    relative_path: str
    size_bytes: Optional[int]
    integrity_state: str


@dataclass(frozen=True)
class DuplicateGroup:
    checksum: str
    file_count: int
    files: List[DuplicateFile]


def query_duplicate_groups(conn: sqlite3.Connection) -> List[DuplicateGroup]:
    """Return all groups of files that share a SHA-256 checksum.

    Only files with a non-NULL checksum are considered. Groups are sorted
    by file_count DESC, then by size_bytes DESC (most overlap first).

    Args:
        conn: SQLite connection with an initialized v9+ schema.

    Returns:
        List of DuplicateGroup, one per unique duplicated checksum.
        Empty list when no duplicates exist.
    """
    rows = conn.execute(
        """
        SELECT
            f.id,
            f.storage_id,
            COALESCE(NULLIF(s.display_name, ''), s.name) AS storage_name,
            f.relative_path,
            f.size_bytes,
            f.integrity_state,
            f.checksum
        FROM file f
        JOIN storage s ON s.id = f.storage_id
        WHERE f.checksum IN (
            SELECT checksum
            FROM file
            WHERE checksum IS NOT NULL
            GROUP BY checksum
            HAVING COUNT(*) > 1
        )
        ORDER BY f.checksum, f.storage_id, f.relative_path;
        """
    ).fetchall()

    # Assemble groups from the ordered flat result.
    groups_by_checksum: dict[str, list[DuplicateFile]] = {}
    order: list[str] = []
    for file_id, storage_id, storage_name, rel_path, size_bytes, integrity, checksum in rows:
        dup_file = DuplicateFile(
            file_id=int(file_id),
            storage_id=int(storage_id),
            storage_name=str(storage_name),
            relative_path=str(rel_path),
            size_bytes=None if size_bytes is None else int(size_bytes),
            integrity_state=str(integrity),
        )
        cs = str(checksum)
        if cs not in groups_by_checksum:
            groups_by_checksum[cs] = []
            order.append(cs)
        groups_by_checksum[cs].append(dup_file)

    groups = [
        DuplicateGroup(
            checksum=cs,
            file_count=len(files),
            files=files,
        )
        for cs, files in ((cs, groups_by_checksum[cs]) for cs in order)
    ]

    # Sort: most copies first, then largest size first.
    groups.sort(
        key=lambda g: (
            -g.file_count,
            -(g.files[0].size_bytes or 0),
        )
    )
    return groups


def get_duplicate_file_ids(conn: sqlite3.Connection) -> frozenset[int]:
    """Return the set of file IDs that share a checksum with at least one other file.

    Used by FileTableModel to decorate the Tags column. O(1) membership testing.

    Args:
        conn: SQLite connection with an initialized v9+ schema.

    Returns:
        frozenset of file IDs that are part of a duplicate group.
    """
    rows = conn.execute(
        """
        SELECT id
        FROM file
        WHERE checksum IS NOT NULL
          AND checksum IN (
              SELECT checksum
              FROM file
              WHERE checksum IS NOT NULL
              GROUP BY checksum
              HAVING COUNT(*) > 1
          );
        """
    ).fetchall()
    return frozenset(int(r[0]) for r in rows)


def count_checksummed_files(conn: sqlite3.Connection) -> Tuple[int, int]:
    """Return (checksummed, total) file counts.

    Used by DuplicatesView to populate the status banner.

    Args:
        conn: SQLite connection with an initialized v9+ schema.

    Returns:
        Tuple of (number of files with non-NULL checksum, total file count).
    """
    row = conn.execute(
        "SELECT COUNT(*) FILTER (WHERE checksum IS NOT NULL), COUNT(*) FROM file;"
    ).fetchone()
    if row is None:
        return (0, 0)
    return (int(row[0]), int(row[1]))
```

- [ ] **Step 4: Run the duplicate helper tests**

```
pytest tests/test_db_duplicates.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Run full suite**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_db_duplicates.py src/assethub/core/db/duplicates.py
git commit -m "feat: add duplicate file query helpers (duplicates.py)"
```

---

## Task 4: `query_library_files_by_ids` helper

**Files:**
- Modify: `tests/test_library_file_query.py`
- Modify: `src/assethub/core/db/file_records.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_library_file_query.py`:

```python
# ---- query_library_files_by_ids ----

def test_query_by_ids_returns_correct_files(tmp_path):
    """query_library_files_by_ids returns only the requested file IDs."""
    import sqlite3
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.db.file_records import query_library_files_by_ids

    conn = get_connection(str(tmp_path / "by_ids.db"))
    initialize_schema(conn)

    conn.execute("INSERT INTO storage(name, root_path, status) VALUES ('Root', '/r', 'OK')")
    conn.commit()
    sid = conn.execute("SELECT id FROM storage WHERE name='Root'").fetchone()[0]

    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (?, 'a.txt', 'OK')",
        (sid,),
    )
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (?, 'b.txt', 'OK')",
        (sid,),
    )
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (?, 'c.txt', 'OK')",
        (sid,),
    )
    conn.commit()

    fid_a = conn.execute("SELECT id FROM file WHERE relative_path='a.txt'").fetchone()[0]
    fid_b = conn.execute("SELECT id FROM file WHERE relative_path='b.txt'").fetchone()[0]
    fid_c = conn.execute("SELECT id FROM file WHERE relative_path='c.txt'").fetchone()[0]

    result = query_library_files_by_ids(conn, [fid_a, fid_b])
    assert len(result) == 2
    ids = {r.file_id for r in result}
    assert fid_a in ids
    assert fid_b in ids
    assert fid_c not in ids


def test_query_by_ids_empty_list_returns_empty(tmp_path):
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.db.file_records import query_library_files_by_ids

    conn = get_connection(str(tmp_path / "empty.db"))
    initialize_schema(conn)
    assert query_library_files_by_ids(conn, []) == []


def test_query_by_ids_returns_library_file_rows(tmp_path):
    """Result items are LibraryFileRow instances (compatible with FileTableModel)."""
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.db.file_records import query_library_files_by_ids, LibraryFileRow

    conn = get_connection(str(tmp_path / "types.db"))
    initialize_schema(conn)
    conn.execute("INSERT INTO storage(name, root_path, status) VALUES ('S', '/s', 'OK')")
    conn.commit()
    sid = conn.execute("SELECT id FROM storage").fetchone()[0]
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (?, 'x.txt', 'OK')",
        (sid,),
    )
    conn.commit()
    fid = conn.execute("SELECT id FROM file").fetchone()[0]

    result = query_library_files_by_ids(conn, [fid])
    assert len(result) == 1
    assert isinstance(result[0], LibraryFileRow)
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_library_file_query.py -v -k "by_ids"
```

Expected: FAIL — `query_library_files_by_ids` not importable.

- [ ] **Step 3: Implement `query_library_files_by_ids`**

In `src/assethub/core/db/file_records.py`, add after `query_library_files`:

```python
def query_library_files_by_ids(
    conn: sqlite3.Connection,
    file_ids: Iterable[int],
) -> List[LibraryFileRow]:
    """Fetch full LibraryFileRow records for a specific set of file IDs.

    Used by the Duplicates view detail panel to feed FileTableModel with
    group members without reloading the full library.

    Args:
        conn: SQLite connection with an initialized schema.
        file_ids: Iterable of file IDs to fetch.

    Returns:
        List of LibraryFileRow ordered by file.id. Empty if file_ids is empty.
    """
    ids = [int(x) for x in file_ids]
    if not ids:
        return []

    ph = _placeholders(len(ids))
    raw_rows = conn.execute(
        _LIBRARY_FILE_SELECT
        + f" WHERE file.id IN ({ph})"
        + " ORDER BY file.id;",
        tuple(ids),
    ).fetchall()

    return [_build_library_row(r) for r in raw_rows]
```

Also add `query_library_files_by_ids` to the imports in any file that needs it (the test already imports it directly).

- [ ] **Step 4: Run the new tests**

```
pytest tests/test_library_file_query.py -v
```

Expected: all tests PASS (including existing ones).

- [ ] **Step 5: Run full suite**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_library_file_query.py src/assethub/core/db/file_records.py
git commit -m "feat: add query_library_files_by_ids helper for duplicates detail panel"
```

---

## Task 5: FileRow `is_duplicate` + Tags column in FileTableModel

This task is UI code. No automated tests. Verify by running pytest for regressions, then visually.

**Files:**
- Modify: `src/assethub/ui/models/file_table_model.py`
- Modify: `src/assethub/ui/views/library_tab.py`

- [ ] **Step 1: Add `is_duplicate` to `FileRow`**

In `src/assethub/ui/models/file_table_model.py`, update the `FileRow` dataclass. Add `is_duplicate` as the last field with a default of `False` so existing code constructing `FileRow` doesn't break:

```python
@dataclass(frozen=True)
class FileRow:
    """A single file record row as displayed in the Library tab."""

    file_id: int
    storage_id: int
    version_id: Optional[int]
    storage_name: str
    relative_path: str
    filename: str
    bound_asset_id: Optional[int]
    bound_asset_name: str
    owned_version_count: int
    integrity_state: str
    size_bytes: Optional[int]
    mtime_unix: Optional[float]
    created_at: str
    is_duplicate: bool = False
```

- [ ] **Step 2: Add Tags column to FileTableModel**

In `FileTableModel.__init__`, append a Tags column to `self._columns`:

```python
            _Column(
                key="tags",
                header="Tags",
                default_visible=True,
                display=lambda r: "Duplicate" if r.is_duplicate else "",
                sort_value=lambda r: 1 if r.is_duplicate else 0,
            ),
```

Add it after the `created_at` column (at the end of the list).

- [ ] **Step 3: Populate `is_duplicate` in LibraryTab.refresh()**

In `src/assethub/ui/views/library_tab.py`, add this import at the top of the file:

```python
from assethub.core.db.duplicates import get_duplicate_file_ids
```

In `LibraryTab.refresh()`, in the Files mode branch, after `result = query_library_files(...)` and before building `file_rows`, add:

```python
        duplicate_ids = get_duplicate_file_ids(conn)
```

Then when constructing each `FileRow`, add `is_duplicate=r.file_id in duplicate_ids`:

```python
            file_rows.append(
                FileRow(
                    file_id=r.file_id,
                    storage_id=r.storage_id,
                    version_id=r.version_id,
                    storage_name=r.storage_name,
                    relative_path=rel_s,
                    filename=filename,
                    bound_asset_id=r.bound_asset_id,
                    bound_asset_name=r.bound_asset_name,
                    owned_version_count=r.owned_version_count,
                    integrity_state=r.integrity_state,
                    size_bytes=r.size_bytes,
                    mtime_unix=r.mtime_unix,
                    created_at=r.created_at,
                    is_duplicate=r.file_id in duplicate_ids,
                )
            )
```

- [ ] **Step 4: Run pytest for regressions**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 5: Visual verification**

Run `python main.py`. Scan a root with duplicate files. In the Library tab Files view, rows for duplicate files should show "Duplicate" in the Tags column.

- [ ] **Step 6: Commit**

```bash
git add src/assethub/ui/models/file_table_model.py src/assethub/ui/views/library_tab.py
git commit -m "feat: add Tags column with Duplicate indicator to Library Files view"
```

---

## Task 6: DuplicatesView widget

This task is UI code. No automated tests.

**Files:**
- Create: `src/assethub/ui/views/duplicates_view.py`

- [ ] **Step 1: Create the DuplicatesView**

Create `src/assethub/ui/views/duplicates_view.py`:

```python
# src/assethub/ui/views/duplicates_view.py
"""Duplicates view — shows file groups that share a SHA-256 checksum."""

from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from assethub.context import AppContext
from assethub.core.db.duplicates import (
    DuplicateGroup,
    count_checksummed_files,
    query_duplicate_groups,
)
from assethub.core.db.file_records import query_library_files_by_ids
from assethub.ui.models.file_table_model import FileRow, FileTableModel


def _fmt_bytes(size: Optional[int]) -> str:
    """Format a byte count as a human-readable string."""
    if size is None:
        return ""
    s = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if s < 1024.0 or unit == "TB":
            return f"{int(s)} {unit}" if unit == "B" else f"{s:.1f} {unit}"
        s /= 1024.0
    return f"{int(size)} B"


class DuplicateGroupTableModel(QAbstractTableModel):
    """Table model for the duplicate groups list.

    Each row represents one group of files with the same SHA-256 checksum.
    Columns: Copies | Size | Overlap | Locations
    """

    _HEADERS = ["Copies", "Size", "Overlap", "Locations"]

    # Column indices
    _COL_COPIES = 0
    _COL_SIZE = 1
    _COL_OVERLAP = 2
    _COL_LOCATIONS = 3

    def __init__(self) -> None:
        super().__init__()
        self._groups: List[DuplicateGroup] = []

    def set_groups(self, groups: List[DuplicateGroup]) -> None:
        self.beginResetModel()
        self._groups = list(groups)
        self.endResetModel()

    def group_at(self, row: int) -> Optional[DuplicateGroup]:
        if 0 <= row < len(self._groups):
            return self._groups[row]
        return None

    # ----- Qt overrides -----

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._groups)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._HEADERS):
                return self._HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:  # noqa: N802
        if not index.isValid():
            return None
        g = self.group_at(index.row())
        if g is None:
            return None
        col = index.column()
        size = g.files[0].size_bytes if g.files else None
        overlap = (g.file_count - 1) * (size or 0)

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self._COL_COPIES:
                return str(g.file_count)
            if col == self._COL_SIZE:
                return _fmt_bytes(size)
            if col == self._COL_OVERLAP:
                return _fmt_bytes(overlap)
            if col == self._COL_LOCATIONS:
                names = sorted({f.storage_name for f in g.files})
                s = ", ".join(names)
                return s[:60] + "…" if len(s) > 63 else s

        if role == Qt.ItemDataRole.UserRole:
            if col == self._COL_COPIES:
                return g.file_count
            if col == self._COL_OVERLAP:
                return overlap
            if col == self._COL_SIZE:
                return size or 0

        return None


class DuplicatesView(QWidget):
    """Library tab Duplicates view.

    Shows duplicate file groups (files sharing a SHA-256 checksum) with a
    detail panel listing all members of the selected group.
    """

    def __init__(self, context: AppContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._context = context
        self._group_model = DuplicateGroupTableModel()
        self._detail_model = FileTableModel()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        # Status banner — shown when unchecksummed files exist.
        self._banner = QLabel("", self)
        self._banner.setVisible(False)
        layout.addWidget(self._banner)

        # Summary line.
        self._summary = QLabel("", self)
        layout.addWidget(self._summary)

        # Vertical splitter: groups table (top) / detail table + button (bottom).
        splitter = QSplitter(Qt.Orientation.Vertical, self)

        # --- Groups table ---
        self._groups_proxy = QSortFilterProxyModel()
        self._groups_proxy.setSourceModel(self._group_model)
        self._groups_proxy.setSortRole(Qt.ItemDataRole.UserRole)

        self._groups_table = QTableView(self)
        self._groups_table.setModel(self._groups_proxy)
        self._groups_table.setSortingEnabled(True)
        self._groups_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._groups_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._groups_table.setAlternatingRowColors(True)
        self._groups_table.verticalHeader().hide()
        self._groups_table.verticalHeader().setDefaultSectionSize(26)
        self._groups_table.horizontalHeader().setStretchLastSection(True)
        self._groups_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Default sort: Overlap descending (column 2).
        self._groups_table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        splitter.addWidget(self._groups_table)

        # --- Detail table + copy button ---
        detail_container = QWidget()
        det_layout = QVBoxLayout(detail_container)
        det_layout.setContentsMargins(0, 0, 0, 0)

        self._detail_proxy = QSortFilterProxyModel()
        self._detail_proxy.setSourceModel(self._detail_model)
        self._detail_proxy.setSortRole(Qt.ItemDataRole.UserRole)

        self._detail_table = QTableView(self)
        self._detail_table.setModel(self._detail_proxy)
        self._detail_table.setSortingEnabled(True)
        self._detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._detail_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._detail_table.setAlternatingRowColors(True)
        self._detail_table.verticalHeader().hide()
        self._detail_table.verticalHeader().setDefaultSectionSize(26)
        self._detail_table.horizontalHeader().setStretchLastSection(True)
        det_layout.addWidget(self._detail_table)

        self._copy_btn = QPushButton("Copy path(s)", self)
        self._copy_btn.setEnabled(False)
        det_layout.addWidget(self._copy_btn)

        splitter.addWidget(detail_container)
        layout.addWidget(splitter, stretch=1)

        # Wire events.
        groups_sel = self._groups_table.selectionModel()
        if groups_sel is not None:
            groups_sel.selectionChanged.connect(self._on_group_selected)

        detail_sel = self._detail_table.selectionModel()
        if detail_sel is not None:
            detail_sel.selectionChanged.connect(self._on_detail_selection_changed)

        self._copy_btn.clicked.connect(self._copy_selected_paths)

    def refresh(self) -> None:
        """Reload duplicate groups from the database."""
        conn = self._context.db_connection
        if conn is None:
            return

        # Status banner.
        checksummed, total = count_checksummed_files(conn)
        missing = total - checksummed
        if missing > 0:
            self._banner.setText(
                f"{missing} file(s) not yet checksummed — run a scan to compute."
            )
            self._banner.setVisible(True)
        else:
            self._banner.setVisible(False)

        # Groups.
        groups = query_duplicate_groups(conn)
        self._group_model.set_groups(groups)

        # Summary line.
        if not groups:
            self._summary.setText("No duplicate files found.")
        else:
            redundant = sum(g.file_count - 1 for g in groups)
            overlap_bytes = sum(
                (g.file_count - 1) * (g.files[0].size_bytes or 0) for g in groups
            )
            self._summary.setText(
                f"{len(groups)} duplicate group(s)"
                f" · {redundant} redundant copies"
                f" · {_fmt_bytes(overlap_bytes)} overlap"
            )

        # Clear detail panel.
        self._detail_model.set_rows([])
        self._copy_btn.setEnabled(False)

    def _on_group_selected(self, _selected, _deselected) -> None:
        idx = self._groups_table.currentIndex()
        if not idx.isValid():
            self._detail_model.set_rows([])
            return

        src_row = self._groups_proxy.mapToSource(idx).row()
        group = self._group_model.group_at(src_row)
        if group is None:
            self._detail_model.set_rows([])
            return

        conn = self._context.db_connection
        if conn is None:
            return

        file_ids = [f.file_id for f in group.files]
        lib_rows = query_library_files_by_ids(conn, file_ids)

        file_rows: List[FileRow] = []
        for r in lib_rows:
            rel_s = r.relative_path
            filename = rel_s.split("/")[-1] if "/" in rel_s else rel_s
            file_rows.append(
                FileRow(
                    file_id=r.file_id,
                    storage_id=r.storage_id,
                    version_id=r.version_id,
                    storage_name=r.storage_name,
                    relative_path=rel_s,
                    filename=filename,
                    bound_asset_id=r.bound_asset_id,
                    bound_asset_name=r.bound_asset_name,
                    owned_version_count=r.owned_version_count,
                    integrity_state=r.integrity_state,
                    size_bytes=r.size_bytes,
                    mtime_unix=r.mtime_unix,
                    created_at=r.created_at,
                    is_duplicate=False,  # Already in a duplicates context; no chip needed.
                )
            )
        self._detail_model.set_rows(file_rows)

    def _on_detail_selection_changed(self, _selected, _deselected) -> None:
        sel = self._detail_table.selectionModel()
        has_selection = sel is not None and bool(sel.selectedRows())
        self._copy_btn.setEnabled(has_selection)

    def _copy_selected_paths(self) -> None:
        conn = self._context.db_connection
        if conn is None:
            return

        sel = self._detail_table.selectionModel()
        if sel is None:
            return

        paths: List[str] = []
        for pidx in sel.selectedRows(0):
            src = self._detail_proxy.mapToSource(pidx)
            row = self._detail_model.row_data(src.row())
            if row is None:
                continue
            db_row = conn.execute(
                """
                SELECT storage.root_path
                FROM file
                JOIN storage ON storage.id = file.storage_id
                WHERE file.id = ?;
                """,
                (row.file_id,),
            ).fetchone()
            if db_row and db_row[0]:
                abs_path = os.path.join(str(db_row[0]), row.relative_path.replace("/", os.sep))
                paths.append(abs_path)

        if paths:
            QApplication.clipboard().setText("\n".join(paths))
```

- [ ] **Step 2: Run pytest for regressions**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/assethub/ui/views/duplicates_view.py
git commit -m "feat: add DuplicatesView widget with groups table and detail panel"
```

---

## Task 7: Wire Duplicates mode into LibraryTab

**Files:**
- Modify: `src/assethub/ui/views/library_tab.py`

- [ ] **Step 1: Add the import**

At the top of `src/assethub/ui/views/library_tab.py`, add:

```python
from assethub.ui.views.duplicates_view import DuplicatesView
```

- [ ] **Step 2: Add the Duplicates mode button in `_build_ui()`**

In `_build_ui()`, after the block that adds `btn_mode_assets` to the button group and `top` layout, add:

```python
        self.btn_mode_duplicates = QToolButton(self)
        self.btn_mode_duplicates.setText("Duplicates")
        self.btn_mode_duplicates.setCheckable(True)

        self._mode_group.addButton(self.btn_mode_duplicates, 2)
        top.addWidget(self.btn_mode_duplicates)
```

- [ ] **Step 3: Add DuplicatesView to the stack**

In `_build_ui()`, after the line `self.stack.addWidget(self.assets_widget)`, add:

```python
        self.duplicates_view = DuplicatesView(self.context, self)
        self.stack.addWidget(self.duplicates_view)
```

- [ ] **Step 4: Update `_on_mode_changed()`**

Replace the two-mode assignment lines:

```python
        self._mode = "files" if int(mode_id) == 0 else "assets"
        self.stack.setCurrentIndex(0 if self._mode == "files" else 1)
```

With:

```python
        mode_map = {0: "files", 1: "assets", 2: "duplicates"}
        self._mode = mode_map.get(int(mode_id), "files")
        stack_map = {"files": 0, "assets": 1, "duplicates": 2}
        self.stack.setCurrentIndex(stack_map[self._mode])
```

Also update the controls enable/disable block at the end of `_on_mode_changed()`:

```python
        self.integrity_combo.setEnabled(self._mode != "duplicates")
        self.chk_show_hidden.setEnabled(self._mode != "duplicates")
        self.chk_unassigned_only.setEnabled(self._mode == "files")
```

- [ ] **Step 5: Update `refresh()` for Duplicates mode**

In `LibraryTab.refresh()`, add a branch at the top of the method (after the Assets mode branch):

```python
        if self._mode == "duplicates":
            self.duplicates_view.refresh()
            return
```

Place this immediately after the Assets mode branch:
```python
        if self._mode == "assets":
            ...
            return

        if self._mode == "duplicates":
            self.duplicates_view.refresh()
            return
```

- [ ] **Step 6: Run pytest for regressions**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 7: Visual verification**

Run `python main.py`.

1. Library tab should now show three mode buttons: **Files | Assets | Duplicates**.
2. Click **Duplicates** — the view switches to the groups table.
3. If no checksums exist yet (fresh DB), status banner says "X files not yet checksummed."
4. After running a scan: groups appear sorted by Overlap descending.
5. Clicking a group row populates the detail table with member files.
6. Select one or more rows in the detail table — **Copy path(s)** button enables.
7. Clicking it copies the absolute path(s) to clipboard.
8. Back in **Files** view: duplicate files show "Duplicate" in the Tags column.

- [ ] **Step 8: Commit**

```bash
git add src/assethub/ui/views/library_tab.py
git commit -m "feat: wire Duplicates view into Library tab as third mode"
```

---

## Done

All tasks complete. Run the full suite one final time and verify the app manually end-to-end:

```
pytest -v
python main.py
```

The checksum deduplication feature is now fully implemented:
- Schema v9 with `file.checksum TEXT`
- Incremental checksumming during scan
- Duplicate groups query helpers in `core/db/duplicates.py`
- "Duplicate" chip in Library Files view Tags column
- Duplicates view with groups table, summary, detail panel, and Copy path(s) action
