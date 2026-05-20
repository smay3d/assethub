# Raptor Status

**Last updated:** 2026-05-20 (end of two-pass scanner session)
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

**Phase:** Active feature development — `raptor` is clean and synced to `origin/raptor`.
106 tests passing (2 pre-existing failures in `test_settings_tab_*` unrelated to recent work).

**Next action:** Address Open Items #1–2 (P1/P2 audit debt), or investigate the DB lock
bug (Open Item #7) discovered while testing the two-pass scanner.

---

## Last Session Summary

**Date:** 2026-05-20
**Session type:** Full feature implementation — two-pass scanner (non-blocking checksumming)

Completed — 12 commits pushed to `origin/raptor`, 106 tests passing:

- **`Scanner.scan_files_only()`** (`core/scanner/scanner.py`): Stage 1 of the two-pass
  scan — walks roots, upserts file records, never calls `sha256_file()`. New/changed files
  get `checksum = NULL`; unchanged files preserve their existing checksum. `scan_all()`
  left completely unchanged.
- **`Scanner.compute_missing_checksums()`** (`core/scanner/scanner.py`): Stage 2 —
  batch re-query loop (`SELECT ... WHERE checksum IS NULL LIMIT 50`) with `failed_ids`
  exclusion to prevent infinite loops on unreadable files. Cancel-safe.
- **`ChecksumResult` dataclass** (`core/scanner/scanner.py`): `files_checksummed`,
  `files_failed`, `canceled`.
- **`ChecksumFinished` event** (`core/events/event_hub.py`): emitted by `ScanTab` when
  Stage 2 completes or is canceled.
- **`ScanTab` two-slot orchestration** (`ui/views/scan_tab.py`): second job slot
  (`_current_checksum_job` / `_checksum_cancel`) runs Stage 2 silently — never disables
  UI buttons. Stage 2 always starts after Stage 1 (even on scan error). `_checksum_restart_pending`
  flag prevents two concurrent checksum workers when a new scan fires while Stage 2 is
  winding down. ESC cancels Stage 2 when Stage 1 is not running.
- **Tests**: `tests/test_scanner_two_pass.py` — 9 tests covering `scan_files_only` and
  `compute_missing_checksums` behavior, including two-pass/single-pass equivalence guard.
- **Tooling**: `.gitignore` updated; `CLAUDE.md` hardened with explicit feature branch
  policy for subagent-driven workflows; `Raptor_Inbox.md` and `raptor-inbox` skill added.

Next session should start with:
- Investigate Open Item #7 (DB lock when adding a root during Stage 2 checksum pass)
- Address Open Items #1–2 (P1/P2 audit debt: `File.version_id` type fix, dead code deletion)
- **Remember:** Create a GitHub Issue and feature branch before any implementation work

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
| 7 | Fix DB lock when adding a root during Stage 2 checksum pass | P2 | Observed during testing 2026-05-20; `_on_cleanup_missing` cancel guard covers removal but "add root" path not addressed |
| 8 | Fix pre-existing test failures in `test_settings_tab_refresh.py` and `test_settings_tab_stats.py` | P2 | `NotADirectoryError` during Windows temp dir cleanup in `shutil.rmtree`; 2 tests failing, 106 passing |
| 9 | Create `raptor-triage` skill and wire into pipeline | P2 | Skill not yet built. Four wiring points pending once created: (1) `CLAUDE.md §2` — add `Raptor_Inbox.md` to Documentation System table; (2) `CLAUDE.md §6` — add `raptor-triage` to Skill Usage Reference; (3) `raptor-session-start` — add inbox check step; (4) `raptor-session-end` — add optional triage prompt before Status update pass |
