# Raptor Changelog

All notable changes to AssetRaptor are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

Versions:
- **Unreleased** — active development, not yet at a named milestone
- **MVP** — file ingest, manual assignment, search/filter/sort, duplicate detection
- **Beta** — auto asset detection, asset version tracking
- **v1.0** — auto project detection, smart folders

---

## [Unreleased]

### Two-pass scanner — non-blocking background checksumming (2026-05-20)

#### Added
- `Scanner.scan_files_only(cancel_check=None) -> ScanResult` — Stage 1: walks roots and
  upserts file records without computing checksums; new/changed files get `checksum = NULL`;
  unchanged files preserve their existing checksum
- `Scanner.compute_missing_checksums(cancel_check=None) -> ChecksumResult` — Stage 2:
  batch re-query loop (`LIMIT 50`) hashing all `checksum IS NULL` files; `failed_ids` set
  prevents infinite loops on permanently unreadable files
- `ChecksumResult` frozen dataclass (`files_checksummed`, `files_failed`, `canceled`)
- `ChecksumFinished` event on `EventHub` — emitted when Stage 2 completes or is canceled
- `ScanTab._current_checksum_job` and `_checksum_cancel` — second independent job slot;
  never disables any UI button
- `ScanTab._start_checksum_job()`, `_checksum_job()`, `_on_checksum_finished()`,
  `_on_checksum_error()` — Stage 2 lifecycle methods
- `ScanTab._checksum_restart_pending` flag — defers Stage 2 restart when a prior checksum
  worker is still winding down, preventing two concurrent workers
- `tests/test_scanner_two_pass.py` — 9 tests: `scan_files_only` behavior (null-preservation,
  stale-null, unchanged-file preservation, cancel), `compute_missing_checksums` behavior
  (batch overflow, cancel mid-batch, unreadable file skip), and two-pass/single-pass
  equivalence regression guard
- `docs/superpowers/specs/2026-05-20-two-pass-scanner-design.md` — design spec
- `docs/superpowers/plans/2026-05-20-two-pass-scanner.md` — implementation plan
- `docs/raptor/Raptor_Inbox.md` — inbox for observations logged during app use
- `.claude/skills/raptor-inbox/SKILL.md` — project skill for logging inbox entries

#### Changed
- `ScanTab._scan_job` now calls `scanner.scan_files_only()` instead of `scan_all()`;
  Stage 2 starts automatically on completion (or after scan error)
- `ScanTab._on_scan` cancels any in-progress checksum job before starting a new scan
  (no wait — Stage 2 is signaled and proceeds to wind down independently)
- `ScanTab.request_cancel_current_job` extended: ESC cancels Stage 2 when no Stage 1 is running
- `ScanTab._on_cleanup_missing` and `_remove_root_from_tracking` cancel the checksum job
  before their DB write operations
- `.gitignore` updated to exclude `settings.local.json`, `*-workspace/`, `.clone/`, `.superpowers/`
- `CLAUDE.md` hardened: feature branch requirement made explicit in skill table, Feature
  Development Loop, and repository rules — applies to subagent-driven workflows too

#### Fixed
- Unused `Tuple` import removed from `core/events/event_hub.py`
- `_on_job_error` now triggers `_start_checksum_job()` on scan errors, so Stage 2 always
  runs even when Stage 1 fails (files indexed before the error still need checksums)

---

### Checksum deduplication (2026-05-18)

#### Added
- `file.checksum TEXT` column (schema v9, nullable — NULL means not yet computed)
- `idx_file_checksum` index on `file(checksum)` for fast group queries
- `_migrate_to_v9()` migration: idempotent `ALTER TABLE` + index creation
- `core/db/duplicates.py` — Qt-free query helpers:
  - `DuplicateFile`, `DuplicateGroup` frozen dataclasses
  - `query_duplicate_groups(conn)` — groups files by shared checksum, sorted by overlap
  - `get_duplicate_file_ids(conn)` — `frozenset[int]` for O(1) duplicate membership testing
  - `count_checksummed_files(conn)` — returns `(checksummed, total)` for status banner
- `core/db/file_records.py` — `query_library_files_by_ids(conn, file_ids)` helper for
  the Duplicates detail panel
- `ui/views/duplicates_view.py` — `DuplicatesView` widget:
  - Status banner (shown when files lack checksums)
  - Summary line: N groups · M redundant copies · X overlap
  - Groups table (`DuplicateGroupTableModel`) with sortable Copies/Size/Overlap/Locations columns
  - Detail panel reusing `FileTableModel`; multi-select + "Copy path(s)" clipboard action
- `FileRow.is_duplicate: bool = False` field added to `file_table_model.py`
- Tags column added to `FileTableModel` — shows "Duplicate" chip for duplicate files
- `"Tags"` added to `DEFAULT_VISIBLE_FILE_COLUMNS` in `ui_constants.py`
- Library tab gains a third mode button: **Duplicates** (index 2 in `QStackedWidget`)
- Tests: `test_schema_v9.py` (5), `test_scanner_checksum.py` (6), `test_db_duplicates.py` (11),
  plus 3 new tests in `test_library_file_query.py`

#### Changed
- Scanner now computes SHA-256 checksums incrementally during scan:
  checksum is (re)computed only when `size_bytes`, `mtime_unix`, or `checksum` changed/is NULL
- `ScanResult` gains `files_checksummed` and `files_without_checksum` fields
- `Scanner.__init__` accepts optional `log: Optional[AppLog]` parameter;
  `AppContext` now passes `log=self.log` to `Scanner`
- `LibraryTab._on_search_changed` and filter handlers now short-circuit in duplicates mode

#### Fixed
- `sha256_file()` `OSError` during scan no longer clears an existing valid checksum;
  `need_checksum` is set to `False` on failure so the stored value is preserved
- `_on_group_selected` in `DuplicatesView` now uses `selectionModel().selectedRows()`
  instead of `currentIndex()`, preventing stale detail panel on keyboard navigation

---

### Per-root scan exclusion list + Library search fix (2026-05-18)

#### Added
- `storage_scan_exclusion` table (schema v8) — per-storage-root extension exclusion list,
  normalized (lowercase, no dot), FK to `storage` with cascade delete, unique constraint
- `core/db/scan_exclusions.py` — Qt-free helper: `get_exclusions`, `set_exclusions`,
  `add_exclusion`, `remove_exclusion`; extensions normalized on write
- `ui/dialogs/edit_root_dialog.py` — `EditRootDialog`: view and edit exclusions per root,
  comma-separated input, Save/Cancel; no DB write on Cancel
- `tests/test_scan_exclusions.py` — 11 tests for DB helper module
- `tests/test_scanner_exclusions.py` — 5 tests for scanner exclusion behavior,
  including Option A re-scan (already-indexed files not silently removed)
- `core/db/file_records.py` — `query_library_files()`, `LibraryFileRow`, `LibraryQueryResult`:
  server-side SQL LIKE search applied before LIMIT; `LibraryTab` now uses this function
- `tests/test_library_file_query.py` — 10 tests for `query_library_files()`

#### Changed
- Scanner loads all exclusion sets before walking roots; skips files whose extension
  matches the exclusion set for that root (Option A: no automatic cleanup of existing records)
- Scan tab toolbar: "Edit…" button added between Add Root and Remove Root;
  enabled only for managed roots, disabled during active jobs
- Scan tab right-click context menu: "Edit root…" added as first item
- `LibraryTab._on_search_changed` now triggers a full server-side refresh rather than
  client-side proxy filtering, fixing search invisibility for files beyond the 10k row cap

#### Fixed
- Library tab search returned zero results for any file beyond row 10,000.
  Root cause: search was applied in-memory on the already-capped row set.

---

### Workflow and tooling setup (2026-05-13)

#### Added
- `CLAUDE_raptor.md` — Claude Code orientation doc covering project goals, architecture,
  UX doctrines, constraints, skill usage, repo etiquette, and commands
- `docs/raptor/` directory with five core project documents:
  `Raptor_Architecture.md`, `Raptor_Changelog.md`, `Raptor_Status.md`,
  `Raptor_ProjectSpec.md` (v1.0 with full product and engineering requirements)
- `.claude/skills/raptor-session-start/` — skill to orient Claude at session start
- `.claude/skills/raptor-session-end/` — skill to update docs, commit, and push at session end

#### Changed
- Legacy root-level design docs moved to `docs/ARCHIVE/`

---

### Project Reboot (2026-05-13)

AssetHub prototype (Stages 5–9.4, ChatGPT workflow) rebooted as **AssetRaptor** under a
new Claude Code workflow. Decision summary:

- **Kept:** Full `core/` backend (DB, scanner, health, detection, events, models, storage)
- **Rewriting:** `ui/` from scratch in PySide6 with intentional visual design
- **Removed from scope:** Sidecar JSON system
- **New workflow:** Skill-driven iterative development with GitHub Issues + feature branches
- **New docs:** `CLAUDE_raptor.md`, `Raptor_Architecture.md`, `Raptor_Changelog.md`,
  `Raptor_Status.md` (this file)

### Known debt carried forward from prototype (from Audit v1.0)

- `File.version_id` typed `int` but nullable in DB — fix before next feature (P1)
- Dead code to delete: `core/config/defaults.py`, `core/utils/logging.py`,
  `core/utils/paths.py`, `core/sidecar/` (P2)
- `File` model not frozen — verify no mutation sites, then add `frozen=True` (P3)
- `AppConfig.rules_root` always `""` at startup — decide: populate or remove (P3)

---

*Entries above this line are added automatically by `raptor-session-end`.*
*Format per entry: `### Description (YYYY-MM-DD)` with Added / Changed / Fixed / Removed subsections.*
