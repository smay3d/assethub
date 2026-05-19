# Checksum Deduplication — Design Spec

**Date:** 2026-05-18
**Status:** Approved — ready for implementation planning
**Branch:** `raptor`

---

## Overview

Raptor will detect files with identical content across tracked storage roots using SHA-256
checksums. This surfaces two complementary use cases: reducing wasted storage by spotting
redundant copies, and tracking where the same asset is used across projects.

Raptor never modifies files on disk. The feature is read-only — it informs the user and lets
them copy paths; cleanup is their responsibility.

---

## Decisions

| Question | Decision |
|---|---|
| When are checksums computed? | Incrementally during scan — only when `size_bytes` or `mtime_unix` changed |
| Where do duplicates surface? | Duplicates view inside the Library tab + passive chip in Files view |
| What actions are available? | Copy path(s) to clipboard — no deletion, no marking |
| Incomplete checksum progress? | Status banner in the Duplicates view |

---

## Section 1: Schema (v9)

One nullable column added to the `file` table:

```sql
ALTER TABLE file ADD COLUMN checksum TEXT;
CREATE INDEX IF NOT EXISTS idx_file_checksum ON file(checksum);
```

- `NULL` means not yet computed.
- Non-null values are SHA-256 hex digests.
- The index on `checksum` makes the `GROUP BY` duplicate query fast.
- `_migrate_to_v9()` added to `core/db/schema.py`; `LATEST_SCHEMA_VERSION` → 9.
- `File` dataclass gains `checksum: Optional[str]`.
- All existing rows get `checksum = NULL` after migration — filled in on next scan.

---

## Section 2: Scanner (incremental checksumming)

`Scanner._upsert_file()` in `core/scanner/scanner.py` is extended to compute and store
checksums incrementally.

**Logic:** before upserting, check whether the stored `size_bytes` and `mtime_unix` match disk.
If they match, preserve the existing checksum. If either changed (or no record exists),
call `sha256_file()` and write the new checksum. This is expressed directly in the SQL upsert
using a `CASE` expression — no extra SELECT needed:

```sql
INSERT INTO file(storage_id, relative_path, integrity_state, size_bytes, mtime_unix, checksum)
VALUES (?, ?, 'OK', ?, ?, ?)
ON CONFLICT(storage_id, relative_path) DO UPDATE SET
    integrity_state = 'OK',
    checksum = CASE
        WHEN excluded.size_bytes != file.size_bytes
          OR excluded.mtime_unix != file.mtime_unix
        THEN excluded.checksum
        ELSE file.checksum
    END,
    size_bytes = excluded.size_bytes,
    mtime_unix = excluded.mtime_unix;
```

`sha256_file()` is called in the scanner walk loop — already off the UI thread (runs in a
`QThreadPool` worker).

`ScanResult` gains two new fields:
- `files_checksummed: int` — files whose checksum was computed or recomputed this scan
- `files_without_checksum: int` — files that still have `checksum = NULL` after the scan

---

## Section 3: DB query helpers (`core/db/duplicates.py`)

A new Qt-free module following the pattern of `scan_exclusions.py` and `file_records.py`.

### Dataclasses

```python
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
```

### Functions

**`query_duplicate_groups(conn) -> List[DuplicateGroup]`**

Finds all checksums shared by 2+ files, joins to storage for display names, assembles
`DuplicateGroup` objects. Sorted by `file_count DESC`, then `size_bytes DESC` (most overlap
first). Files with `checksum = NULL` are excluded.

Core query:
```sql
SELECT f.id, f.storage_id,
       COALESCE(NULLIF(s.display_name, ''), s.name),
       f.relative_path, f.size_bytes, f.integrity_state, f.checksum
FROM file f
JOIN storage s ON s.id = f.storage_id
WHERE f.checksum IN (
    SELECT checksum FROM file
    WHERE checksum IS NOT NULL
    GROUP BY checksum HAVING COUNT(*) > 1
)
ORDER BY f.checksum, f.storage_id, f.relative_path;
```

The SQL `ORDER BY f.checksum` groups rows by checksum for efficient Python-side assembly.
After assembly, groups are sorted in Python by `file_count DESC`, then `size_bytes DESC`.

**`get_duplicate_file_ids(conn) -> frozenset[int]`**

Returns the set of file IDs that share a checksum with at least one other file.
Used by the Library tab's Files view to decorate the tags column.
O(1) membership testing per row.

**`count_checksummed_files(conn) -> tuple[int, int]`**

Returns `(checksummed, total)`. Used by the Duplicates view status banner.

---

## Section 4: Library tab — Files view chip

`FileTableModel` calls `get_duplicate_file_ids()` once at load time and stores the result
as `self._duplicate_ids: frozenset[int]`.

In the tags column `data()` method, if `file_id in self._duplicate_ids`, a **"Duplicate"**
chip is appended using the existing QSS tag styling. The chip is passive — no click action.

`_duplicate_ids` is refreshed whenever the Library tab reloads its data (after a scan
completes). No live mid-session refresh.

---

## Section 5: Library tab — Duplicates view

The Library tab's view-switcher row (Files / Assets) gains a third option: **Duplicates**.
Selecting it swaps the main content area via a `QStackedWidget`. The `DuplicatesView`
widget lives at `ui/views/duplicates_view.py`.

### Layout (top to bottom)

1. **Status banner** (conditionally visible)
   Shown when `files_without_checksum > 0`. During an active scan: `"Checksumming in
   progress — X of Y files done."` After a scan with incomplete coverage: `"X files not
   yet checksummed — run a scan to compute."` Hidden when all files have checksums.

2. **Summary line**
   `"N duplicate groups · M redundant copies · X GB overlap"`
   Derived from `query_duplicate_groups()`. Updates after each scan.

3. **Groups table** (`QAbstractTableModel` + `QSortFilterProxyModel`)
   One row per duplicate group. Columns:
   - **Copies** — number of files sharing this checksum
   - **Size** — size of one copy
   - **Overlap** — `(copies - 1) × size`
   - **Locations** — compact summary of storage root names, e.g. `"ProjectA, Archive"`

   Default sort: **Overlap** descending. Empty state: `"No duplicate files found."`

4. **Detail panel** (shown when a group row is selected)
   Flat file list reusing `FileTableModel` — one row per file in the group, showing
   `storage_name`, `relative_path`, `integrity_state`. Multi-select supported.
   **"Copy path(s)"** button copies absolute paths of selected files to the clipboard.

   `FileTableModel` expects `LibraryFileRow` objects. When a group is selected, the
   detail panel calls `query_library_files_by_ids(conn, file_ids)` — a new helper in
   `file_records.py` that wraps `_LIBRARY_FILE_SELECT` with `WHERE file.id IN (...)`.
   This is the only addition to `file_records.py`.

---

## Section 6: Error handling & edge cases

| Scenario | Behavior |
|---|---|
| `sha256_file()` raises `OSError` | Logged via `AppLog`; `checksum` stays `NULL`; scan continues |
| File with `checksum = NULL` | Excluded from all duplicate groups |
| Unmanaged root file in a group | Appears normally; storage name column makes location clear |
| Group drops to 1 member after rescan | Disappears from Duplicates view automatically |
| No duplicate groups | Empty-state message: `"No duplicate files found."` |

---

## Section 7: Testing

All tests are Qt-free, run headless via `pytest`.

| File | Coverage |
|---|---|
| `tests/test_checksum.py` | Confirm `sha256_file()` returns consistent digests; raises `OSError` on missing file |
| `tests/test_scanner_checksum.py` | New file → checksum computed; unchanged file → checksum preserved (poison test); changed mtime → recomputed; unreadable file → `NULL`, no crash; `ScanResult` counts correct |
| `tests/test_db_duplicates.py` | `query_duplicate_groups()` correct groups and sort order; `NULL` checksums excluded; `get_duplicate_file_ids()` correct frozenset; `count_checksummed_files()` correct tuple; empty DB → no crash |
| `tests/test_schema_v9.py` | v8 DB migrates to v9; `file.checksum` column is nullable; index exists |

No UI tests — consistent with the existing headless test suite.

---

## Files Affected

| Action | Path |
|---|---|
| Modify | `core/db/schema.py` — v9 migration, bump `LATEST_SCHEMA_VERSION` |
| Modify | `core/model/file.py` — add `checksum: Optional[str]` |
| Modify | `core/scanner/scanner.py` — incremental checksum in `_upsert_file()`, update `ScanResult` |
| Create | `core/db/duplicates.py` — query helpers |
| Modify | `ui/views/library_tab.py` — view switcher, `QStackedWidget`, wire Duplicates view |
| Create | `ui/views/duplicates_view.py` — `DuplicatesView` widget |
| Modify | `ui/models/file_table_model.py` — duplicate chip in tags column |
| Modify | `core/db/file_records.py` — add `query_library_files_by_ids(conn, file_ids)` helper |
| Create | `tests/test_scanner_checksum.py` |
| Create | `tests/test_db_duplicates.py` |
| Create | `tests/test_schema_v9.py` |
| Modify | `tests/test_checksum.py` — confirm/extend existing coverage |
