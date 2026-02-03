# AssetHub — Stage 7.4 Settings Tab (Read-Only) v0.1 Plan

## Goal
Add a **Settings** tab that exposes a clear, read-only overview of what AssetHub is using “under the hood” (paths, DB status, UI behavior defaults), without requiring users to dig through code.

This stage remains **file-level** (no asset/tag/version UI beyond counts). It is primarily a diagnostics and transparency surface.

---

## Scope
### In-scope (v0.1)
- New Settings tab visible in the main UI
- Read-only “About”, “Paths”, and “Database & Index Stats” sections
- Read-only “UI Behavior” section summarizing current defaults/caps
- Buttons for copy/open convenience (paths, diagnostics summary)
- Minimal styling (clear, legible, stable across 1080p/1440p)

### Out-of-scope (v0.1)
- Editing settings (no config writing, no preference saving UI)
- Asset-level controls (tags, versions, asset composition editing)
- Deep log viewer or embedded log tailing
- Migrations UI beyond schema version display

---

## UI Layout (Settings Tab)

### A) About
Read-only fields:
- App version (string)
- DB schema version (from `schema_version` table)
Nice-to-have:
- Python version
- PySide6 version
- Platform / OS

### B) Paths (from AppContext config)
For each path, show read-only text plus utility actions:

Fields:
- Data root (`config.data_root`)
- DB path (`config.db_path`)
- Sidecar root (`config.sidecar_root`)
- Preview cache root (`config.preview_root`)
- Log root (`config.log_root`)

Actions (per path):
- **Copy path**
- **Open folder** (Explorer/Finder)

> Note: these are intentionally read-only to reflect current stage; later stages can decide whether to store in JSON config or QSettings.

### C) Database & Index Stats (computed from DB)
Read-only stats:
- Tracked files count: `COUNT(*) FROM file`
- Missing files count: `COUNT(*) FROM file WHERE integrity_state='MISSING'`
- Storage roots count: `COUNT(*) FROM storage`
- Unmanaged present: boolean (exists in storage table)
- DB file size on disk (human readable)

Actions:
- **Open DB folder**
- **Copy diagnostics summary**
  - a single text blob containing: app version, schema version, key paths, key counts

### D) UI Behavior (read-only transparency)
Library:
- Row cap (10,000)
- Default visible columns (human list)
Preview:
- Supported preview formats: `.png .jpg .jpeg .bmp .gif .webp`
- Preview pixel cap (current constant value)
Layout persistence (informational):
- QSettings keys used for splitter state
- “Saved state present: Yes/No” for each key (if easy)

### E) Advanced (collapsible)
- Raw config UI defaults (theme/language) if present
- Any future internal toggles (placeholder text OK for v0.1)

---

## Data Sources / Implementation Notes

### App version source
- Use a single constant (e.g., `assethub/__init__.py` `__version__`) OR existing window title convention.
- If not already present, add a lightweight constant.

### Config paths source
- Use existing `AppContext.config` fields (already being used by other subsystems).
- Display as plain text; do not attempt to validate existence beyond “Open folder” enabling.

### DB stats source
- Query via existing DB layer (same connection patterns as library/scanner tests).
- Keep queries simple and fast (no joins required for basic counts).

### Open folder action
- Use a small utility function for Windows “open folder” behavior.
- If you already have an explorer helper, reuse it; otherwise add one.

### Copy to clipboard
- Use `QApplication.clipboard().setText(...)`

---

## Files to Add / Modify

### New
- `src/assethub/ui/views/settings_tab.py`
  - Settings tab UI
  - Queries stats and renders sections
- (Optional) `src/assethub/ui/utils/os_open.py`
  - `open_folder(path: str) -> None` cross-platform helper
- (Optional) `src/assethub/ui/utils/formatting.py`
  - `format_bytes`, `format_platform`, etc. (only if you want reuse)

### Modified
- `src/assethub/ui/windows/main_window.py`
  - Add Settings tab to the tab widget
  - Wire AppContext into SettingsTab
- `src/assethub/ui/views/__init__.py`
  - Export SettingsTab
- (Optional) add version constant location if not already present

---

## Refresh Behavior
- Stats should refresh on entering the Settings tab OR via a `Refresh` button.
- For v0.1, simplest: include a **Refresh** button at top of Settings tab.

---

## Testing Plan

### Automated (pytest)
- Add a lightweight test that:
  - Creates temp DB schema
  - Inserts a couple file rows + storage rows
  - Instantiates SettingsTab (skip if PySide6 missing)
  - Calls its “refresh stats” method and asserts key values are computed

### Manual smoke test
- Launch app
- Open Settings tab
- Confirm paths display correctly
- Click “Open” buttons (folders open)
- Click “Copy diagnostics” and paste into a text editor
- Confirm DB counts match what Library/Scan show

---

## Definition of Done
- Settings tab exists and renders without errors
- About section displays app + schema version
- Paths section displays all key configured paths with copy/open actions
- DB stats display tracked files, missing files, storage roots, unmanaged presence, db file size
- UI Behavior section displays row cap, supported preview formats, preview pixel cap
- Tests pass; manual smoke test confirms buttons function

