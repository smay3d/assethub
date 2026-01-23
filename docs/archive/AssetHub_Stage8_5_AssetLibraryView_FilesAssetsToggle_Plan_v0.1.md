# AssetHub — Stage 8.5 Plan (v0.1)
*(Asset Library View v0 — Files | Assets toggle)*

## Goal

Add **asset-level browsing** in the Library tab **without removing** the existing file-level workflow.

After 8.5, the user can switch the Library tab between:
- **Files** (current Stage 7 behavior, unchanged)
- **Assets** (new v0 asset browser with versions + files per version)

---

## Scope

### In scope
- Library tab toggle: **Files | Assets**
- New Asset Library view (v0):
  - asset list table
  - asset detail pane:
    - versions list (sorted by `sort_key`)
    - files list for selected version
- Basic “jump to files” affordance (optional, but valuable):
  - select a file row in asset version view → jump/select it in Files view

### Out of scope
- Full “Assets-first” navigation everywhere (Stage 8.6+)
- Complex asset health analytics (only basic summary strings in v0)
- Bulk asset actions beyond navigation (later)

---

## UX Requirements

### Toggle
- Visible at the top of Library tab: **Files | Assets** (segmented control / tabs / combo).
- Default is **Files** (preserve Stage 7 user expectation).

### Asset list columns (v0)
Minimum columns:
- **Name**
- **Type**
- **Latest Version**
- **Versions** (count)
- **Files** (count)
- **Health** (simple summary: e.g. `OK`, `1 MISSING`, `3 MISSING`)

Sort:
- Default: Name ascending
- Optional: allow clicking column headers for sorting if it’s already easy with current model.

### Detail pane (Asset mode)
- Top: selected asset name + type (read-only)
- Left: versions list (label + sort_key; label displayed, sort_key internal)
- Right: files list for selected version (relative_path + integrity_state)

---

## Architecture

### A) UI wiring: Library view split by mode

Modify existing Library view module to host a small mode switch + stacked content:
- `FilesLibraryWidget` (existing)
- `AssetsLibraryWidget` (new)

Implementation approach:
- Add a `QButtonGroup` with two `QToolButton`s (checkable) or a `QTabBar` with 2 tabs.
- Add a `QStackedWidget` to swap between the two widgets.
- When switching to **Assets**, run a refresh query and populate the assets model.

**Definition of “unchanged” for Files mode:** no behavior regressions in selection, context menu, health actions, etc.

---

### B) DB query helpers for asset browsing

Add DB helpers (minimal, read-only) to support the asset view efficiently.

New module (recommended):
- `src/assethub/core/db/asset_library.py`

Dataclasses (core layer or ui layer — prefer core for testability):
- `AssetRow`:
  - `asset_id: int`
  - `storage_id: int`
  - `name: str`
  - `type: str`
  - `key: str`
  - `latest_version_id: Optional[int]`
  - `latest_version_label: str`
  - `version_count: int`
  - `file_count: int`
  - `missing_count: int`

Functions:
1) `list_assets_for_storage(conn, storage_id: int) -> list[AssetRow]`
   - Computes:
     - version_count: `COUNT(version.id)`
     - latest_version: max `sort_key` per asset
     - file_count + missing_count: join through versions → files
   - Deterministic order: `ORDER BY LOWER(asset.name), asset.id`

2) `list_versions_for_asset(conn, asset_id: int) -> list[Version]`
   - Ordered by `sort_key ASC`

3) `list_files_for_version(conn, version_id: int) -> list[dict]`
   - Fields: `file_id`, `relative_path`, `integrity_state`, `size_bytes`, `mtime_unix`
   - Ordered by `relative_path ASC` (or `id ASC` if you prefer stable insert order)

Notes:
- Keep queries readable; correctness > micro-optimizing.
- These helpers are pure reads and safe to call often.

---

### C) Assets Library widget

New:
- `src/assethub/ui/views/assets_library_widget.py`

Responsibilities:
- Shows asset list (table view + model)
- On asset selection:
  - query versions for asset
  - select latest version by default (highest sort_key)
  - display files for selected version
- Exposes a signal/callback for “jump to file(s)” (if implemented)

Model strategy:
- Use `QAbstractTableModel` (preferred) or `QStandardItemModel` to keep implementation light.
- Store `asset_id`/`version_id` as user roles in items to simplify selection plumbing.

---

### D) EventHub refresh behavior

Asset Library should refresh on the same events that currently refresh Files view after:
- scan updates
- detection apply (8.4)
- version membership edits (8.2 via future UI actions)

Implementation:
- Subscribe Assets Library widget to the existing “db changed / library refresh” signal(s).
- On refresh: re-query `list_assets_for_storage` for the currently-selected storage root (or unmanaged if none).

If there is no single, stable “db changed” signal already:
- add **one** minimal signal on EventHub (e.g. `db_changed`) and emit it from:
  - detection apply (8.4)
  - any future version membership UI action (8.6+)

---

## Testing

### Unit tests (Qt-free)
New:
- `tests/test_db_asset_library_queries.py`

Covers:
- `list_assets_for_storage` returns correct counts and latest label
- missing_count computed correctly
- versions ordered by sort_key
- files listed for version are deterministic

Test data:
- 1 storage root
- 2 assets, each with 2 versions
- mix of OK and MISSING files

### Manual smoke test
1) Run app → Library tab → switch to **Assets**
2) Confirm asset rows appear after applying detection in Scan tab
3) Select asset → versions list populates → selecting versions updates files list
4) Switch back to **Files** and verify file workflow unchanged

---

## Definition of Done

- `python -m pytest` passes on Windows.
- Library tab shows **Files | Assets** toggle.
- Assets view displays assets with latest version label + counts + basic missing summary.
- Selecting an asset shows versions (sorted by sort_key) and files for selected version.
- Files mode remains unchanged and stable.

---

## Expected file changes (high level)

New:
- `src/assethub/core/db/asset_library.py`
- `src/assethub/ui/views/assets_library_widget.py`
- `tests/test_db_asset_library_queries.py`

Modified:
- Library tab view module (to add toggle + stacked widget)
- Possibly EventHub (only if a single “db_changed” signal is missing)

