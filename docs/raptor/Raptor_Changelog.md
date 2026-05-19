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
