# Raptor Status

**Last updated:** 2026-05-18
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
| Duplicate file detection | Not started | New feature for Raptor |
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

**Phase:** Active feature development — `raptor` branch is clean, all tests passing (74).

**Next action:** Address P1/P2 audit debt (Open Items #1–2) before the next feature,
or continue with next MVP feature from the milestone tracker.

---

## Last Session Summary

**Date:** 2026-05-18
**Session type:** Feature implementation + bug fix

Completed:
- **Library search bug fixed** — search was filtered client-side against a capped 10k-row
  set; files beyond the cap were invisible. Fixed via `query_library_files()` in
  `core/db/file_records.py` (SQL LIKE before LIMIT). `LibraryTab` now calls this function.
  10 new tests in `tests/test_library_file_query.py`.
- **UI freeze logged** — smay3d/assethub#1: synchronous `QImageReader.read()` on UI thread
  during rapid scrolling of 180k-file library causes "(not responding)". Deferred to UI rewrite.
- **Per-root scan exclusion list** (smay3d/assethub#2, PR #3, merged to `raptor`):
  - Schema v8: `storage_scan_exclusion` table (FK cascade, unique constraint)
  - `core/db/scan_exclusions.py`: Qt-free CRUD helpers; extensions normalized on write
  - Scanner: loads exclusion sets before walk, skips matching files (Option A re-scan behavior)
  - `ui/dialogs/edit_root_dialog.py`: new `EditRootDialog` — view/add/remove exclusions
  - `ui/views/scan_tab.py`: "Edit…" toolbar button + "Edit root…" right-click menu entry
  - 16 new tests (11 DB helper + 5 scanner)
  - Manually verified: add exclusion → scan → absent from Library; remove → rescan → re-indexed
- Deleted legacy root-level prototype docs (`AssetHub_DevLog_*.md`, `AssetHub_Stage9_*.md`,
  `AssetHub_DesignSummary_v1.9.md`)

Next session should start with:
- Address Open Items #1–2 (P1/P2 audit debt: `File.version_id` type fix, dead code deletion)
- Or continue MVP features — see Milestone Tracker

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
