# AssetHub — Stage 7.6 UI Foundation Extensions (Global Log + Storage Nicknames + Remove Roots) v0.1 Plan

## Purpose of Stage 7.6
Stage 7.6 closes remaining “file-level usability + control surface” gaps discovered during Stage 7 testing, while preserving the no-write-to-user-assets principle and keeping Stage 8 (asset-level) integration smooth.

Stage 7.6 focuses on:
- A **global MainWindow log** that becomes the shared reporting surface for all actions
- **Storage root nicknames** (user-defined display names, no on-disk rename)
- The ability to **remove storage roots from tracking** via the UI (with clear, safe DB-only cascade rules)

## Scope Summary
### New features (Stage 7.6)
1) Global MainWindow Log (low visual weight, bottom split-pane)
2) Storage Root Nicknames (DB + UI + rename action)
3) Remove Roots from Tracking (UI + DB cascade delete + confirmations)

### Explicit non-goals (deferred)
- Watchdog / live filesystem monitoring (defer to Stage 9+)
- Filetype attribute on file records (planned for Stage 8 schema work)
- UI buttons/controls for the log panel (clear/copy/etc. not included yet)

---

## Stage 7.6 Deliverables

### 1) Global MainWindow Log (bottom split-pane)
#### Goal
Provide a universal, low-friction action history log visible from anywhere in the app. This becomes a primary “source of truth” for outcomes and is used immediately during Stage 8 feature development.

#### UX / Layout
- MainWindow becomes a vertical split layout:
  - **Top:** the existing main tab widget (Scan / Library / Settings / etc.)
  - **Bottom:** a **read-only log view** (selectable text)
- Default log pane height should be **small** (low visual weight), but user can drag splitter to expand.
- No log UI buttons (no Clear/Copy/Auto-scroll toggles yet).
- Log text must be selectable so users can copy via system clipboard.

#### Logging API
Add a small logging interface accessible from `AppContext`:
- `ctx.log.info(str)`
- `ctx.log.warn(str)`
- `ctx.log.error(str)`

The implementation should:
- Format each line with timestamp + level + message (keep concise).
- Cap memory usage (retain last N lines, e.g. 500–1000).
- Be safe to call from any thread (enqueue to UI thread for display).

#### Minimum action coverage (v0.1)
Ensure the following actions write summaries to the global log:
- Scan roots (summary of files indexed/updated, timing if available)
- Health check (summary of rows checked/changed)
- Cleanup MISSING Files (summary of missing rows removed)
- Library context actions that mutate DB:
  - targeted health check (changed count)
  - remove missing records from DB (count removed)

*(Goal is not “every message everywhere,” but consistent summary reporting for major outcomes.)*

#### Acceptance criteria
- Log pane appears under tabs; splitter resizes.
- Selecting/copying log text works.
- Triggering the actions above produces readable log entries.
- No regression to existing UI behavior (tabs function normally).

---

### 2) Storage Root Nicknames (display name)
#### Goal
Allow the user to assign a human-friendly name to storage roots for readability throughout the UI, without renaming anything on disk (preserves no-write design principle).

#### Data / DB changes
- Add a new column to `storage` table:
  - `display_name` (or `nickname`) — nullable text
- Schema migration approach:
  - Add column if missing
  - Backward compatible with existing DBs (no destructive changes)

#### Display rules
- If `storage.display_name` is non-empty → use it as the primary display label
- Otherwise → fall back to current storage label behavior (existing name/path logic)

#### UI changes
Update the following UI surfaces to show nickname (with fallback):
- Library table “Storage” column
- Scan tab storage roots listing
- Settings tab (paths/stats) where storage roots are shown

#### Editing nicknames
Add a storage root rename action in Scan tab:
- Right-click storage root → “Rename (display name)…”
- Prompt for new nickname:
  - allow empty to clear nickname and revert to fallback display
- Update DB only; do not touch disk.
- Emit `db_changed(reason="storage_renamed", payload={"storage_id": ..., "old": ..., "new": ...})`
- Log summary line to global log.

#### Acceptance criteria
- Nickname persists after app restart.
- Nickname updates appear immediately in Library + Settings due to EventHub refresh.
- Clearing nickname restores fallback display behavior.

---

### 3) Remove storage roots from tracking (UI + DB cascade)
#### Goal
Provide a safe, explicit UI action to remove a storage root from tracking, including its associated file records, without deleting anything from disk.

#### Rules (v0.1)
- Removing a storage root from tracking:
  1) Deletes all `file` rows associated with that `storage_id`
  2) Deletes the `storage` row
- Must occur within a single DB transaction.
- Does not delete files from disk.

#### UI placement
- Scan tab storage roots list: right-click context menu:
  - “Remove root from tracking…”
- This action should not be exposed elsewhere yet (keeps destructive actions centralized in Scan tools).

#### Confirmation dialog requirements
Before deletion:
- Show storage display name (nickname/fallback) and full path.
- Show count: “This will remove N tracked file records from the database.”
- Explicitly clarify: “This does not delete files from disk.”

#### Signals / updates
- After deletion completes:
  - Emit `db_changed(reason="storage_removed", payload={"storage_id": ..., "files_removed": N})`
  - Log summary line to global log (“Removed root …; removed N file records.”)

#### UI state correctness
- Library selection/current row must gracefully handle removals:
  - If current/selected files were removed, the UI must not crash; it should clear or select the next available row.
- Settings should update counts immediately via EventHub refresh.

#### Acceptance criteria
- Root disappears from Scan roots list immediately.
- Library removes all related file rows immediately without needing a full rescan.
- Settings counts update immediately.
- Pytests cover cascade delete behavior and count correctness.

---

## Patch / Execution Strategy (stability-first)

### Patch 7.6.1 — Global MainWindow Log
Scope:
- MainWindow bottom split-pane log UI
- `AppContext` logging API + UI-safe sink
- Wire major action summaries to log

Verification:
- Manual smoke test for UI + logging
- Unit tests for log formatting/cap behavior (Qt-free)
- All existing tests remain green

### Patch 7.6.2 — Storage Root Nicknames
Scope:
- DB migration + storage display rules
- UI display updates (Library/Scan/Settings)
- Rename action + db_changed + log

Verification:
- Rename persistence and immediate UI refresh
- Migration test (or schema test updates)
- All tests green

### Patch 7.6.3 — Remove Roots from Tracking
Scope:
- Remove root action + confirmation dialog
- Transactional cascade delete (files then storage)
- db_changed + log + UI refresh correctness

Verification:
- Manual smoke test removing a root with files
- Pytest covering cascade counts and invariants
- All tests green

---

## Testing Plan

### Automated tests (pytest)
- Log subsystem:
  - cap behavior (does not grow unbounded)
  - formatting includes timestamp/level/message (exact timestamp format can be loosely asserted)
- Storage nickname:
  - schema includes nickname column
  - updating nickname persists and reflects in snapshot/queries
- Remove root cascade:
  - deleting storage removes associated file records
  - returned/recorded counts match expected
- Ensure no tests instantiate QWidget/QApplication directly (continue Qt-free practice in tests).

### Manual smoke tests
- Confirm log pane resizes and stays low-weight by default.
- Perform: scan → health → cleanup missing → remove missing selection → confirm log entries.
- Rename storage root → verify label changes in Library and Settings immediately.
- Remove root from tracking → confirm Library and Settings update without rescan.

---

## Definition of Done
- Global MainWindow log exists as bottom split-pane; major actions report summaries there.
- Storage roots support a user-defined nickname stored in DB and shown across UI.
- Storage roots can be removed from tracking via Scan tab, with DB-only cascade delete and clear confirmations.
- EventHub refresh keeps all views consistent (Library/Settings/Scan).
- All pytests green; manual smoke tests pass.
