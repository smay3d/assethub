# AssetHub — Stage 8.4 Plan (v0.1)

## Goal

Add the **Scan tab “Detect Assets…”** workflow:

1) Run Stage 8.3 detection for a selected storage root  
2) Show results in a **modal proposals dialog** with safe edits  
3) **Apply** proposals atomically (DB writes) using Stage 8.1 + 8.2 helpers  
4) Refresh views via EventHub

This is the first Stage 8 step that is expected to be **visually noticeable**.

---

## Scope

### In scope
- Scan tab action: **Detect Assets…** (enabled when exactly one storage root is selected)
- Modal dialog: proposals list + detail editor
- Apply logic:
  - create asset as needed (storage-scoped identity)
  - create v01 version
  - attach selected file ids (**enforce unowned**)
  - write `version_change_log` rows (one per created version; action_type=`detect_apply`)
- Post-apply refresh:
  - emit EventHub signals so Library/Detail/Scan views update

### Out of scope
- Asset library view / Files|Assets toggle (8.5)
- Advanced heuristics (sequence split, channel completeness scoring)
- Any “edit rules” UI

---

## UX Requirements (from Stage 8 plan)

Dialog must provide:
- Proposals list + detail pane
- Editable **name**
- **Type override** dropdown
- **File checklist** (uncheck to remove)
- Auto-demote: `texture_set → generic` if edited below 2 files
- Show summary count of **skipped owned** files (no listing)

---

## Architecture & Files

### A) UI — Detect Assets dialog

New:
- `src/assethub/ui/dialogs/detect_assets_dialog.py`

Dialog structure:
- Left: proposals list (QListView or QTreeView)
- Right: detail editor
  - Name: QLineEdit
  - Type: QComboBox (`image_sequence`, `texture_set`, `generic`)
  - Files: QListWidget with checkboxes (display `relative_path`)
  - Read-only: reason text + key + counts

Internal dialog model objects:
- `EditableProposal` (ui-layer dataclass)
  - `type: str`
  - `key: str`
  - `suggested_name: str` (editable)
  - `file_ids: list[int]`
  - `checked_file_ids: set[int]` (editable)
  - `reason: str`
  - `demoted_from: Optional[str]` (for UX trace)

Rules:
- When type is `texture_set` and checked files drop below 2:
  - auto-switch type to `generic`
  - set `demoted_from="texture_set"`
- Keep proposals deterministic order; UI preserves that ordering.

### B) Scan tab integration

Modify Scan tab view to add:
- Toolbar button or context menu item: **Detect Assets…**
- Enabled when one storage root selected (and storage id is valid)
- On trigger:
  1) load rules (Stage 8.3 loader)
  2) run detection (Stage 8.3 engine) to produce proposals + summary
  3) open dialog, passing:
     - storage root label/path
     - summary (skipped_owned, skipped_excluded)
     - proposals
  4) if user confirms Apply:
     - call apply function (below)
     - log user-facing summary to MainWindow log
     - emit EventHub refresh signals

### C) Core apply logic (testable, non-UI)

New:
- `src/assethub/core/detection/apply.py`

Dataclasses:
- `ApplyItem` (normalized from EditableProposal)
  - `type: str`
  - `key: str`
  - `name: str`
  - `file_ids: list[int]` (checked only)
- `ApplyResult`
  - `created_assets: int`
  - `created_versions: int`
  - `attached_files: int`
  - `skipped_owned: int`
  - `skipped_missing_rows: int`
  - `summaries: list[str]` (one per proposal)

API:
- `apply_detection_proposals(conn, storage_id: int, items: list[ApplyItem]) -> ApplyResult`

Behavior:
- Single transaction (`with conn:`) for the entire apply.
- For each item:
  - `create_asset` (storage_id, type, key, name)
  - `create_version` on that asset (default label `v01`)
  - `attach_files_to_version(..., enforce_unowned=True)`
  - write `version_change_log` row on the created version:
    - `action_type="detect_apply"`
    - summary string
    - payload_json includes:
      - `added_file_ids`
      - `skipped_owned`
      - `source="detection"`
      - optional `notes`
- If any item fails (e.g., bad ids, constraint error), roll back all changes.
- No attempt to “partially apply”.

Notes:
- Attach should treat already-owned rows as skipped (not an error).
- If an item ends with 0 checked files, it is skipped (and not treated as failure).

### D) EventHub refresh

After a successful apply, emit:
- storage stats refresh (Scan tab)
- file table refresh (Library)
- (future) asset/versions view refresh (8.5)

Implementation will use existing EventHub signals:
- prefer existing “db_changed”/“library_changed” signal(s) rather than adding new ones
- if no suitable signal exists, add **one** minimal `db_changed` style signal with a narrow meaning

---

## Testing

### Unit tests (Qt-free)

New:
- `tests/test_detection_apply_transaction.py`

Covers:
1) **Happy path**
   - unowned files become attached to new versions
   - assets created with correct (storage_id,type,key)
   - version labels start at `v01`
   - `version_change_log` rows exist and payload JSON includes `added_file_ids`

2) **Enforce unowned**
   - if a file is already attached to an existing version, it is skipped and counted
   - apply still succeeds

3) **Rollback**
   - include an invalid file_id in one item
   - assert: no assets/versions/log rows created (transaction rolled back)

### Minimal UI smoke (optional)
- Keep UI tests minimal; rely on unit tests for correctness.
- Manual human test:
  - Select a storage root → Detect Assets… → see proposals → Apply → verify new version membership in DB / health checks.

---

## Definition of Done

- `python -m pytest` passes on Windows.
- Dialog opens from Scan tab, shows proposals and skipped-owned summary.
- Apply creates assets + v01 versions and attaches unowned files, with `version_change_log` rows.
- MainWindow log shows a concise summary and EventHub refreshes the UI.

---

## Expected file changes (high level)

New:
- `src/assethub/ui/dialogs/detect_assets_dialog.py`
- `src/assethub/core/detection/apply.py`
- `tests/test_detection_apply_transaction.py`

Modified:
- `src/assethub/ui/views/scan_tab.py` (or equivalent Scan view module)
- `src/assethub/ui/main_window.py` (only if needed for wiring/logging)
- Potentially `src/assethub/core/event_hub.py` (only if a minimal refresh signal is missing)

