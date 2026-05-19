# Raptor Status

**Last updated:** 2026-05-18 (end of checksum dedupe session)
**Active branch:** `raptor`
**Current milestone:** Pre-MVP — active feature development

---

## Milestone Tracker

### MVP
File ingest + disk tracking · Manual file → asset assignment · Search, filter, sort · Duplicate detection

| Feature | Status | Notes |
|---|---|---|
| File ingest + disk tracking | Carried over (complete) | Core backend retained from prototype |
| Manual file → asset assignment | Carried over (complete) | Backend retained; UI to be rewritten |
| Search, filter, sort | Carried over (complete) | Backend retained; UI to be rewritten |
| Duplicate file detection | Complete | Schema v9 + incremental checksumming + Duplicates view |
| UI rewrite (PySide6) | Not started | Replacing prototype UI from scratch |
| `.exe` distribution (PyInstaller) | Not started | Required before any beta testing |

### Beta
Auto asset detection · Asset version tracking

| Feature | Status | Notes |
|---|---|---|
| Auto asset detection | Carried over (complete) | Backend retained; UI to be rewritten |
| Asset version tracking | Carried over (complete) | Backend retained; UI to be rewritten |

### v1.0
Auto project detection · Smart folders

| Feature | Status | Notes |
|---|---|---|
| Auto project detection | Not started | |
| Smart folders | Not started | |

---

## Current Work

**Phase:** Active feature development — `raptor` branch is clean, all tests passing (97).

**Next action:** Address P1/P2 audit debt (Open Items #1–2), or open a PR to land the
checksum dedupe feature on `raptor` (branch is clean and complete).

---

## Last Session Summary

**Date:** 2026-05-18
**Session type:** Full feature implementation — checksum deduplication (MVP)

Completed — all 13 commits on `raptor`, 97 tests passing:

- **Schema v9** (`core/db/schema.py`, `core/model/file.py`): `file.checksum TEXT` nullable
  column + `idx_file_checksum` index; `File.checksum: Optional[str] = None` field added;
  `_migrate_to_v9()` idempotent migration.
- **Incremental checksumming** (`core/scanner/scanner.py`, `context.py`): Scanner computes
  SHA-256 per file only when `size_bytes`, `mtime_unix`, or `checksum` changed/is NULL.
  `ScanResult` gains `files_checksummed` and `files_without_checksum`. `AppLog` injected
  into Scanner via `context.py`. OSError during hashing preserves existing checksum.
- **Duplicate query helpers** (`core/db/duplicates.py`): `DuplicateFile`, `DuplicateGroup`
  dataclasses; `query_duplicate_groups()`, `get_duplicate_file_ids()`,
  `count_checksummed_files()`. Qt-free.
- **`query_library_files_by_ids`** (`core/db/file_records.py`): bridges `DuplicateFile`
  IDs → `LibraryFileRow` objects for `FileTableModel` reuse in the detail panel.
- **Tags column** (`ui/models/file_table_model.py`, `ui/ui_constants.py`): `FileRow.is_duplicate`
  field; "Duplicate" chip shown in Tags column for duplicate files. `DEFAULT_VISIBLE_FILE_COLUMNS`
  updated.
- **`DuplicatesView` widget** (`ui/views/duplicates_view.py`): status banner, summary line,
  groups table (`DuplicateGroupTableModel`, sortable by Copies/Size/Overlap/Locations),
  detail panel (reuses `FileTableModel`), "Copy path(s)" clipboard action.
- **LibraryTab wiring** (`ui/views/library_tab.py`): Duplicates as third mode (index 2 in
  `QStackedWidget`); filter/search handlers short-circuit for duplicates mode.
- **Tests**: `test_schema_v9.py` (5), `test_scanner_checksum.py` (6), `test_db_duplicates.py`
  (11), plus 3 new tests in `test_library_file_query.py`. Total suite: 97 passing.

Next session should start with:
- Open a PR to merge `raptor` → `raptor` (or tag the checksum dedupe work)
- Address Open Items #1–2 (P1/P2 audit debt: `File.version_id` type fix, dead code deletion)
- Begin UI rewrite or next MVP feature — see Milestone Tracker

---

## Open Items

| # | Item | Priority | Notes |
|---|---|---|---|
| 1 | Fix `File.version_id: int` → `Optional[int]` | P1 | Audit finding; fix before next feature |
| 2 | Delete dead code: `core/config/defaults.py`, `core/utils/logging.py`, `core/utils/paths.py`, `core/sidecar/` | P2 | Audit findings; sidecar removed from scope |
| 3 | Decide `AppConfig.rules_root` handling | P3 | Populate from defaults or remove the field |
| 4 | Fix UI freeze (smay3d/assethub#1) | P2 | Async preview loading needed; defer to UI rewrite |
| 5 | Design UI visual style | Medium | Deferred to UI design stage; stub at `docs/raptor/Raptor_StyleGuide.md` |
| 6 | Write `raptor-build` skill | Low | Needed before first beta distribution |
