# AssetHub — Stage 7.5 UI Foundation (Signals + Multi-Select + Library Actions + Missing Cleanup) v0.1 Plan

## Purpose of Stage 7.5

Stage 7.5 is a **scalability foundation pass** that strengthens the file-level UI so Stage 8 (asset-level handling) can be integrated smoothly without UI drift or action spaghetti.

Stage 7.5 focuses on:

- **Centralized change signaling** so all views stay in sync
- **Multi-selection** and scalable “action plumbing” in Library
- A robust **context menu action set** (open/reveal/copy/health/delete-missing)
- A bulk maintenance control: **Remove all MISSING records** from Scan tab

### Forward-looking distinction (important)

- **Stage 7 (now):** file-level browsing and diagnostics; actions operate on **file records**
- **Stage 8 (later):** asset-level browsing; many actions become **asset-aware** and will reuse the same event hub + selection/action infrastructure from 7.5

---

## Stage 7.5 Deliverables

### 1) Centralized app-wide signals (EventHub)

Add a lightweight, non-Qt event dispatcher attached to `AppContext` that provides:

- `db_changed(reason: str, payload: dict)`
- `scan_finished(summary: dict)`
- `health_finished(summary: dict)`

**Emission rules:**

- Emit `db_changed` whenever DB rows are modified by scan/health/delete actions.
- For health operations, emit `db_changed` **only if** the health check actually changes any tracked file row state (e.g., integrity state changes).

**Subscriber rules:**

- Library view listens to `db_changed` to refresh its model/view.
- Settings listens to `db_changed`, `scan_finished`, and `health_finished` to refresh snapshot.

---

### 2) Library multi-selection + scalable action plumbing

Upgrade Library table selection to standard desktop behavior:

- Selection mode: **ExtendedSelection**
- Selection behavior: **SelectRows**
- Supports:
    - Shift-range select
    - Ctrl toggle select
    - Single click selects one

Add a small selection utility layer:

- `get_selected_file_ids()` (stable identity via `file_id`)
- `get_current_file_id()` (the most recently interacted “current” row)

Add a “LibraryActions” layer to keep UI clean and future-proof:

- A dedicated module/class that performs actions given `file_ids: list[int]`
- UI code should call `LibraryActions.*` instead of embedding DB logic in the view
- Actions emit EventHub signals (directly or via shared backend functions that do)

---

### 3) Detail pane behavior update for multi-selection (preview stays useful)

When selection changes:

- **Preview always shows the “current/last interacted” item** (Qt current index).
- The metadata area below preview becomes:
    - **Single selection:** show normal file details (existing Stage 7.3 behavior)
    - **Multi selection:** show a **selection summary** panel while preview still shows the current file

This preserves the “did I select the right file?” feedback even during multi-select.

**Selection summary contents (v0.1):**

- Selected count
- Total size (sum of size_bytes; human readable)
- Integrity breakdown (OK/MISSING/UNRESOLVED counts)
- Storage breakdown (count per storage root name)

---

### 4) Library context menu actions (approved set)

Implement a right-click context menu for selected rows. It operates on the current selection set (one or many).

### Top-level actions

- **Open file with system default**
- **Open file location (reveal in Explorer)**
- **Open storage root location**

### Copy submenu

- Copy file name
- Copy absolute path (directory only; file name excluded)
- Copy relative path (directory only; file name excluded)
- Copy checksum

### Other actions

- **Run health check** (targeted to selection)
    - Runs health check only for selected file ids
    - If any integrity state changes → emits `db_changed`
- **Remove from database** (MISSING-only)
    - Enabled only if **all selected rows are MISSING** (otherwise disabled/greyed)
    - Confirmation dialog required
    - Deletes those file records from DB
    - Emits `db_changed(reason="file_records_deleted", payload={"count": N})`

**Menu enablement rules (v0.1):**

- Actions requiring a resolvable absolute path should be disabled if the path can’t be built (e.g., missing storage root).
- For “Open file with system default”:
    - If file missing → disabled (or show a message). Prefer disabled.

**Clipboard formatting (multi-select):**

- Copy actions should produce a newline-separated list (one item per selected file).

---

### 5) Scan tab bulk cleanup: Remove all MISSING records

Add a Scan tab maintenance button (near existing ingest/health tools):

- Button label: **Remove all MISSING records from database…**
- On click:
    1. Query missing count
    2. Confirm dialog: “Found N missing records. Remove?”
    3. Delete all missing file rows
    4. Emit `db_changed(reason="missing_records_purged", payload={"count": N})`

This is a bulk “cleanup tracking” tool and fits naturally alongside Scan tab’s other mass operations.

---

## Interaction Rules

### A) Current vs Selected (important for preview behavior)

- **Current** row drives the preview (last interacted item).
- **Selected set** drives the selection summary and context menu target list.

### B) Preserve selection and current row on refresh

When Library refreshes due to `db_changed`:

- Attempt to reselect the previously selected `file_id`s if they still exist.
- Attempt to restore the current row (prefer last current `file_id`).
- If removed (e.g., deleted missing record), gracefully fall back:
    - Current becomes first remaining selected item, otherwise empty state.

### C) Remove-from-database safety

- Action enabled only if *all* selected are MISSING.
- Confirmation dialog always required.
- Does **not** delete files from disk—only stops tracking.

---

## Wiring / Data Flow

### EventHub integration points

- `AppContext` owns the EventHub instance.
- Scanner/health operations emit:
    - `scan_finished(summary)`
    - `health_finished(summary)`
    - `db_changed(...)` when rows change

Library and Settings subscribe at construction time (or via `bind_context()`).

### Targeted health check flow (Library context menu)

1. UI obtains `file_ids` from selection utility
2. UI calls `LibraryActions.run_health_check(file_ids)`
3. Action calls existing health logic in “targeted mode”
4. Health updates DB integrity states
5. If changed rows > 0 → emit `db_changed`
6. Library model refreshes; Settings snapshot refreshes

### Missing removal flow (Library context menu)

1. UI obtains `file_ids` from selection utility
2. UI checks all are MISSING (or action disabled already)
3. Confirmation dialog
4. Action deletes file rows by id
5. Emit `db_changed`
6. Library + Settings update immediately

### Bulk missing removal (Scan tab)

Same delete function as Library (shared action/service), just with different selection source (query all missing).

---

## Files to Add / Modify (expected)

> Note: filenames below reflect intent; actual modules should align with current repo layout.
> 

### New

- `src/assethub/core/event_hub.py` (or similar non-Qt location)
    - Simple subscribe/emit mechanism (no Qt signals)
- `src/assethub/ui/actions/library_actions.py`
    - Open/reveal/copy/health/delete logic based on `file_ids`
- (Optional) `src/assethub/ui/utils/selection_utils.py`
    - Helper functions to extract selected/current file_ids cleanly

### Modified

- `src/assethub/core/app_context.py`
    - Owns `event_hub`
    - Provides accessors / lifetime management
- `src/assethub/ui/views/library_tab.py`
    - Enable multi-select
    - Install context menu + actions wiring
    - Subscribe to `event_hub.db_changed` to refresh
    - Preserve selection/current on refresh
- `src/assethub/ui/views/file_detail_pane.py` (or equivalent)
    - Preview updates from “current file”
    - Add selection summary panel for multi-select
- `src/assethub/ui/views/settings_tab.py`
    - Subscribe to EventHub events for auto-refresh
- `src/assethub/ui/views/scan_tab.py`
    - Add “Remove all MISSING…” button and wiring to shared delete action
- `src/assethub/core/health_service.py` (or wherever health is implemented)
    - Add targeted mode (if not already) and return `changed_count`
    - Ensure `db_changed` emitted when `changed_count > 0`

---

## Testing Plan

### Automated (pytest) — avoid Qt widget instantiation

Principle: test through **services/snapshot/action layer**, not through QWidget creation.

1. **EventHub smoke test**
- Subscribe two handlers; emit `db_changed`; assert both called with expected payload.
1. **Targeted health check test (logic-level)**
- Seed DB with one file marked OK.
- Manipulate filesystem state (or mock) to force missing/unmissing transition.
- Run targeted health on that file_id.
- Assert:
    - DB row updated
    - returned `changed_count` matches
    - `db_changed` emitted only if changed_count > 0 (can be validated via a test subscriber)
1. **Remove missing selection test**
- Insert a mix of missing and non-missing records.
- Attempt delete with non-missing included:
    - ensure action refuses (or caller guard prevents)
- Delete missing-only:
    - rows removed
    - count returned correct
    - `db_changed` emitted once
1. **Bulk missing purge test**
- Insert missing rows; run purge-all.
- Assert all missing rows gone; non-missing remain.

### Manual smoke test

1. Scan a folder; open Library tab
2. Multi-select with Shift/Ctrl:
    - preview follows current row
    - summary panel updates for selection count/size/breakdowns
3. Context menu:
    - Open file with system default works for present files
    - Reveal in Explorer opens correct folder
    - Open storage root opens root folder
    - Copy submenu copies expected values (multi-select produces multi-line)
4. Remove missing:
    - Delete a file on disk → run health → row becomes MISSING
    - Select only missing rows → “Remove from database” enabled and works
    - Selecting mixed rows → delete disabled/greyed
5. Scan tab:
    - “Remove all MISSING…” shows correct count and removes
6. Confirm Settings updates automatically after each operation (no tab switching required)

---

## Definition of Done

- EventHub exists on AppContext and is used as the canonical change-notification mechanism.
- Library supports multi-select and preserves current/selection across refresh when possible.
- Detail pane preview follows current row even under multi-select; summary shown for selection set.
- Library context menu implements the approved actions and obeys enablement rules.
- Targeted health check emits `db_changed` only if it changes DB state.
- Remove-from-database works for MISSING-only selection; bulk missing purge works from Scan tab.
- Pytests pass on Windows; manual smoke test passes.