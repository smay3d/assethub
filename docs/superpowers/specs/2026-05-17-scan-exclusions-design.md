# Design: Per-Root Scan Exclusion List

**Date:** 2026-05-17
**Issue:** smay3d/assethub#2
**Status:** Approved — ready for implementation

---

## Summary

Add a per-storage-root extension exclusion list so users can prevent specific file
types from being indexed during scanning. Files matching an exclusion are silently
skipped; they never enter the `file` table. Already-indexed files of an excluded
type are left untouched when exclusions are added after a scan.

---

## Motivation

A registered storage root may contain thousands of files irrelevant to asset
tracking (game engine temp files, OS metadata, logs, etc.). Without exclusions,
these pollute the library, slow searches, and generate permanent health-checker
noise when the files are later deleted.

A view-time filter alone is insufficient: it does not prevent health checker noise
from indexed files that subsequently disappear from disk.

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Storage strategy | New normalized table | Follows all existing codebase patterns; DB-enforced uniqueness; cascade cleanup |
| Exclusion scope | Per storage root | Different roots warrant different profiles |
| Re-scan behaviour | Option A — no automatic cleanup | Consistent with "no silent side effects" doctrine |
| UI entry point | "Edit root…" dialog | Extensible as roots gain more settings; keeps table readable |
| Dialog access | Toolbar button + right-click context menu | Two consistent entry points |

---

## Schema — v8 Migration

New table:

```sql
CREATE TABLE storage_scan_exclusion (
    id          INTEGER PRIMARY KEY,
    storage_id  INTEGER NOT NULL REFERENCES storage(id) ON DELETE CASCADE,
    extension   TEXT NOT NULL,
    UNIQUE(storage_id, extension)
);
CREATE INDEX idx_scan_exclusion_storage ON storage_scan_exclusion(storage_id);
```

- Extensions stored lowercase, no leading dot (`log`, not `.LOG`)
- `UNIQUE(storage_id, extension)` enforces deduplication at the DB level
- `ON DELETE CASCADE` cleans up exclusions when a root is removed
- Registered as `_migrate_to_v8` in `schema.py`; `LATEST_SCHEMA_VERSION` → 8

---

## DB Helper Module — `core/db/scan_exclusions.py`

Qt-free. Four functions:

| Function | Signature | Purpose |
|---|---|---|
| `get_exclusions` | `(conn, storage_id) -> frozenset[str]` | Load exclusion set for one root |
| `set_exclusions` | `(conn, storage_id, extensions: Iterable[str]) -> None` | Replace full exclusion set (delete + re-insert) |
| `add_exclusion` | `(conn, storage_id, extension: str) -> None` | Add a single extension |
| `remove_exclusion` | `(conn, storage_id, extension: str) -> None` | Remove a single extension |

**Normalization** (strip leading dot, lowercase) is applied inside the helper on
all writes. Callers never need to normalize.

---

## Scanner Changes — `core/scanner/scanner.py`

At the start of `scan_all`, load exclusion sets for all roots before walking:

```python
exclusions: dict[int, frozenset[str]] = {
    root.id: get_exclusions(conn, root.id)
    for root in roots
}
```

During the file walk, skip excluded extensions before calling `_upsert_file`:

```python
ext = os.path.splitext(fname)[1].lstrip(".").lower()
if ext in exclusions.get(root.id, frozenset()):
    continue
```

No other changes to the scanner. Already-indexed files of a newly excluded type
are left untouched in the DB (Option A — no silent deletions).

---

## UI

### `EditRootDialog` — `ui/dialogs/edit_root_dialog.py`

New dialog. Opens pre-populated with the root's current exclusion list.

**Contents:**
- Root name and path (read-only, at top)
- List of current excluded extensions, each with a remove (×) button
- Text input + "Add" button — normalizes input (strips dot, lowercases, ignores duplicates)
- "Save" / "Cancel" buttons

**On Save:**
- Calls `set_exclusions()` with the dialog's current list
- Emits `DbChanged(reason="scan_exclusions_updated", payload={"storage_id": ...})`
- Caller refreshes the root table

**On Cancel:** discards all changes, no DB writes.

### Scan Tab Integration — `ui/views/scan_tab.py`

Two entry points, both opening `EditRootDialog`:

1. **Toolbar button** — "Edit…" button alongside existing Add/Remove, enabled when exactly one root row is selected
2. **Right-click context menu** — "Edit root…" option on any root row

The root table refreshes after the dialog closes via Save.

---

## Re-Scan Behaviour

When exclusions are added to a root that was already scanned:

- The next scan **stops indexing new files** of excluded types
- Previously-indexed files of those types **remain in the DB unchanged**
- No automatic purge, no MISSING flag — the user decides what to do with them
- If excluded files are later deleted from disk, the health checker will mark them MISSING, at which point the existing "Remove from database" Library context menu action becomes available
- If excluded files remain on disk, there is currently no mechanism to remove them from the DB — this is an accepted out-of-scope gap for this feature

---

## Testing

Qt-free backend tests only.

### `tests/test_scan_exclusions.py`

- `get_exclusions` returns empty frozenset for root with no exclusions
- `set_exclusions` replaces the full set (add, overwrite, clear to empty)
- Extensions normalized on write (dot stripped, lowercased)
- Removing a storage root cascades and deletes its exclusions
- `add_exclusion` / `remove_exclusion` work correctly in isolation

### `tests/test_scanner_exclusions.py`

- Files with an excluded extension are not indexed
- Files with a non-excluded extension are indexed normally
- Exclusions are per-root: excluded on root A does not affect root B
- Already-indexed files of a newly excluded type remain in DB after re-scan (Option A)

---

## Files Created / Modified

| File | Change |
|---|---|
| `src/assethub/core/db/schema.py` | Add `_migrate_to_v8`, bump `LATEST_SCHEMA_VERSION` to 8, add DDL for `storage_scan_exclusion` |
| `src/assethub/core/db/scan_exclusions.py` | **New** — DB helper module |
| `src/assethub/core/scanner/scanner.py` | Load exclusions, skip excluded files during walk |
| `src/assethub/ui/dialogs/edit_root_dialog.py` | **New** — Edit Root dialog |
| `src/assethub/ui/views/scan_tab.py` | Add "Edit…" button + right-click menu entry |
| `tests/test_scan_exclusions.py` | **New** — DB helper tests |
| `tests/test_scanner_exclusions.py` | **New** — Scanner exclusion tests |
