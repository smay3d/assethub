# AssetHub — Stage 9.3.3 Manual Assignment Verification + Auto Version-Up (Plan v0.1)

**Depends on:** Stage 9.3.1 + 9.3.2 complete (schema v7, binding APIs, initial UI actions)  
**Source doctrine:** Manual binding is authoritative; binding changes must be visible, durable, and never surprising.

---

## Goal (Ship Terms)

Make manual binding **provably functional** for the user:

- In **Files view**, the user can see **which asset** a file is bound to, and whether it is **owned by N versions**.
- In **Assets view**, binding/unbinding causes the asset to **version up automatically** (snapshot carry-forward + bound set enforced), and the versions/files panes **refresh immediately** so results are visible.
- Replace the nonsensical Assets view “bind selection to this asset” action (from the version file pane) with the correct action on the **asset row**: “Bind files to this asset…”.

This patch prioritizes correctness + verifiability over fancy UX (asset dropdown remains for now).

---

## In Scope

### A) Files View Table: Verification Columns
1. Add a visible column: **Bound Asset**
   - Displays the bound asset display name (fallback label if needed).
   - Empty if unbound.
2. Add a visible column: **Owned by Versions**
   - Displays an integer count: number of **non-discarded** versions the file belongs to.
   - This replaces (or de-emphasizes) any legacy “version_id” single-value display that no longer reflects `version_file`.

### B) Assets View Refresh & Selection Preservation
- After bind/unbind operations:
  - Assets list, versions list, and version-file list **refresh**
  - Selection is preserved when possible (asset_id + version_id heuristics)

### C) Auto Version-Up on Bind/Unbind (Semantics 2)
Binding/unbinding is an asset membership change and must create a new snapshot:

- **Bind files to asset**:
  - Create a **new version** for the asset (next monotonic sort_key / label).
  - Clone membership from **latest non-discarded** version.
  - Ensure all **bound files** for the asset are present in the new version snapshot.
  - Persist membership via `version_file`.
- **Unbind files from asset**:
  - Also version up (same mechanism), but the newly created snapshot should:
    - be cloned from latest non-discarded
    - include current bound set (after unbind)
    - (important) should not retroactively change older versions, including discarded ones

**Note:** This patch does **not** attempt “role-guess re-evaluation on bind” (explicitly deferred).

### D) Assets View Entry Point Fix (Correct UX)
- Remove/disable the version-file pane context action:
  - “Bind selection to this asset” (nonsensical in that pane)
- Add to the **asset table** context menu:
  - “Bind files to this asset…” → opens the existing file assignment dialog with target asset preselected
  - “Unbind selected files…” (if file list selection is provided via dialog; see below)

### E) Logging
- Global log messages must clearly describe:
  - bind/unbind counts
  - rebind counts
  - version-up creation: new version label/id
  - any skipped files due to locked binding constraints
- Detection logs remain unchanged in this patch (aside from any incidental better refresh behavior).

---

## Out of Scope

- Replacing the asset dropdown with a searchable table (deferred; planned future patch)
- New “file picker” subsystem beyond what already exists (keep it minimal)
- Any changes to detection rules / detection UI beyond respecting bindings (already in 9.3.1)
- Version snapshot editor UI
- Checksum reconcile / project workflows

---

## UX / UI Details

### Files View
- Add columns (visible by default):
  - **Bound Asset** (string)
  - **Owned by Versions** (int)
- “Unassigned only” filter continues to mean:
  - not manually bound AND owned_by_versions == 0

### Assets View
- Asset table right-click:
  - **Bind files to this asset…**
    - Uses existing selection dialog
    - Target asset locked to the clicked asset row
- Version-file pane right-click:
  - Remove bind action
  - Keep file-level actions (open/reveal/copy, health, etc.)

---

## Data Flow / Wiring

### Files View model data requirements
- `bound_asset_id` and `bound_asset_name`
  - From `file_binding` join `asset`
- `owned_version_count`
  - Count of `version_file` rows joined to `version`
  - Only count versions where `version.is_discarded = 0` (or equivalent)
  - (If the schema uses a different discarded flag, use the canonical “non-discarded” predicate used elsewhere)

### Bind/Unbind actions (LibraryActions)
1. User triggers bind/unbind
2. Call DB binding APIs (already exist)
3. **Immediately version-up** the affected asset(s)
   - For bind: version-up the target asset(s)
   - For unbind: version-up the asset(s) that previously owned those bindings
4. Emit `EventHub.db_changed(...)` with reason(s) that cause:
   - Files view to refetch row data (for new bound asset name + owned count)
   - Assets view to refresh versions/files

---

## Threading / Performance Notes

- Keep operations synchronous for now (like existing DB-only actions), but ensure:
  - The version-up snapshot creation is transactional and reasonably efficient.
- Any heavy aggregate queries (owned count) should be designed to avoid per-row N+1 queries:
  - Prefer a single query returning counts keyed by file_id for the current page/selection if feasible,
  - Or extend the model’s base query to include a `COUNT(...)` subquery/grouping.

(We’ll prefer correctness first, but avoid obvious slow paths.)

---

## Implementation Tasks

### 1) Extend Files Query / Model
- Add joined field for bound asset name
- Add computed `owned_version_count` for non-discarded versions
- Update headers and display roles (tooltip, sort)

### 2) Add “Bind files to this asset…” in Assets table context menu
- Preselect target asset in existing dialog (no UX upgrade yet)
- Remove/disable the redundant bind action from version-file pane

### 3) Implement Auto Version-Up Helpers
- Add/extend a DB-layer function:
  - `version_up_asset_due_to_binding_change(asset_id, reason, actor)`
- Ensure it:
  - creates new version number/label using existing monotonic rules
  - clones membership from latest non-discarded snapshot
  - enforces bound set
  - persists via `version_file`
- Call this from bind/unbind action flows.

### 4) Refresh + selection preservation
- Ensure Assets view updates versions list and selects the newly created latest version (best-effort)
- Ensure Files view reflects new columns immediately (best-effort)

---

## Files to Modify / Add (Expected)

**Likely modify**
- `src/assethub/ui/models/file_table_model.py`
- `src/assethub/ui/views/library_tab.py` (columns, filter predicate uses owned count)
- `src/assethub/ui/actions/library_actions.py` (bind/unbind now triggers version-up)
- `src/assethub/ui/views/assets_library_widget.py` (context menu changes + refresh behavior)

**Likely modify/add in DB layer**
- `src/assethub/core/db/versions.py` (or wherever version creation/fork helpers live)
- `src/assethub/core/db/file_bindings.py` (may remain unchanged, but could gain helper wrappers)
- Potential new helper module if needed:
  - `src/assethub/core/db/versioning_binding_hooks.py` (only if it keeps responsibilities clean)

---

## Testing Plan

### Unit / Integration Tests (pytest)
1. **Owned-by-versions count**
   - Create file with membership in 2 non-discarded versions → count == 2
   - Mark one version discarded → count decreases accordingly
2. **Bind triggers version-up**
   - Bind a file to asset A
   - Assert a new latest non-discarded version exists and includes:
     - carry-forward members
     - the newly bound file
3. **Unbind triggers version-up**
   - Unbind file from asset A
   - Assert new version exists and does NOT include the file unless it is still a member for other reasons
   - Assert older versions remain unchanged
4. **UI smoke (import-level)**
   - Ensure new columns/context menu wiring does not break imports

(Full UI automation remains out of scope; we rely on your human verification pass as usual.)

---

## Definition of Done

- Files view shows:
  - **Bound Asset** (name)
  - **Owned by Versions** (count of non-discarded memberships)
- “Unassigned only” filter works correctly with these semantics
- Binding/unbinding:
  - creates a **new latest** asset version snapshot automatically
  - carries forward prior membership
  - enforces bound set
  - does not mutate historical versions (including discarded)
- Assets view updates immediately after binding/unbinding so the user can verify:
  - a new latest version exists
  - the version’s file list reflects the change
- All pytests pass on Windows
- Global log entries are clear and specific (bind/unbind counts + version label created)

---
