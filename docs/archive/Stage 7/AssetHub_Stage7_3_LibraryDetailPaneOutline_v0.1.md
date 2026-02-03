# AssetHub — Stage 7.3 Library Detail Pane (Preview + File Details) v0.1 Plan

## Purpose of Stage 7.3
Stage 7.3 completes the Stage 7 “backend becomes usable UI” loop by adding a **master–detail** layout to the **Library** tab:

- **Left:** Library table (already implemented in 7.2)
- **Right:** A **Detail Pane** that shows an entry’s preview + read-only file details

### Forward-looking distinction (important)
- **Library tab (now):** browsing **files**; detail pane shows **file preview + file metadata**
- **Library tab (later):** browsing **assets**; detail pane becomes a “composition” view (preview for single-file assets, and a list of associated files for multi-file assets)
- **Top-level Details tab (later):** repurpose into an **Asset Breakdown / Versions workbench** for richer controls affecting multiple files/versions

---

## Stage 7.3 Deliverables

### 1) Master–detail layout inside Library tab
- Replace the single-table layout with a `QSplitter`:
  - Left: existing table + search/filter controls
  - Right: new `FileDetailPane`
- The splitter is user-resizable; dragging can effectively collapse either side.

### 2) FileDetailPane (right side)
A read-only panel showing:

#### A) Preview area (top)
- **Preview what we can**:
  - Supported formats: `.png .jpg .jpeg .bmp .gif .webp`
  - Image previews shown via `QPixmap` scaled to fit
- If preview is not available:
  - Show message: **“Preview unavailable. Supported formats: .png .jpg .jpeg .bmp .gif .webp”**
- If file is missing:
  - Show same fallback message (plus integrity state in metadata area)

#### Preview scaling + performance cap
- Preview area scales with the detail pane as the splitter resizes.
- Preview is capped so it never dominates the pane:
  - **UI cap:** sensible maximum height for the preview container
  - **Decode/display cap:** scale pixmap to a maximum pixel area roughly ~¼ of 1440p (≈0.9MP) to avoid huge texture decodes.
- Higher-resolution previews are deferred to a future dedicated view if needed.

#### B) Metadata area (below preview)
Always visible, user-facing fields:
- Filename
- Integrity state (OK / MISSING / UNRESOLVED)
- Storage name + root path
- Relative path
- Absolute resolved path (computed from storage root + relative path, when resolvable)
- Size (human readable)
- Modified time (human readable)

#### C) Advanced section (collapsible)
A clean expander for raw/internal fields (no checkbox):
- file.id
- storage_id
- version_id
- raw size_bytes
- raw mtime_unix
- created_at
- any other currently stored raw fields

#### D) Empty state (nothing selected)
When no row is selected:
- Show centered message: **“Select a file in Library to view details”**
- Low contrast, using palette/disabled-text styling (avoid hard-coded theme colors)

---

## Interaction Rules

### Selection behavior
- Selecting a row in the table updates the detail pane immediately.
- The selection uses stable `file_id` as the canonical identity.

### Preserve selection on refresh
When the Library model refreshes (manual refresh or after scan/health):
- Attempt to reselect the previously selected `file_id` if it still exists.
- If it no longer exists, clear selection and show the empty-state message.

### Context menu (right-click) on library rows
Use a context menu rather than page buttons.

Menu items (when absolute path can be resolved):
- **Copy absolute path** (available even if file is missing)
- **Open in Explorer** (open containing folder; available even if file is missing)
- (Optional) Copy relative path (nice-to-have; include if trivial)

Hide these items if **absolute path cannot be resolved** (e.g., storage root unavailable).

> Note: For v0.1 “Open in Explorer” does not need to select/highlight the file, just open the folder.

---

## Wiring / Data Flow

### Detail pane loading
On selection change:
1. Query DB for the selected file record by `file_id`
2. Join `storage` to get root path/name
3. Compute `absolute_path = join(storage.root_path, file.relative_path)`
4. Render metadata + preview (best-effort)

### Refresh triggers
- Manual refresh (existing button)
- Auto-refresh after Scan/Health completes (already wired through MainWindow)
- After refresh, apply the “Preserve selection on refresh” rule above.

---

## Files to Add/Modify (expected)

### New
- `src/assethub/ui/views/file_detail_pane.py` (FileDetailPane widget)
  - Preview widget + metadata form + advanced expander + empty state
- (Optional) `src/assethub/ui/utils/explorer.py`
  - Helper to open folder in Explorer safely on Windows

### Modified
- `src/assethub/ui/views/library_tab.py`
  - Wrap table + detail pane in `QSplitter`
  - Forward selection changes to `FileDetailPane`
  - Add table context menu actions
  - Preserve selection on refresh logic

- Possibly `src/assethub/ui/windows/main_window.py`
  - Only if needed for refresh/selection signal routing (aim to keep changes minimal)

---

## Testing Plan

### Automated (pytest)
- If PySide6 available:
  - Instantiate Library tab + detail pane widgets
  - Insert sample DB rows and verify:
    - selection loads correct absolute path fields
    - refresh preserves selection by `file_id`
    - context menu enablement logic matches “resolvable vs not”

### Manual smoke test
1. Scan a folder with a mix of images + non-images
2. Click rows; confirm detail pane updates instantly
3. Confirm image previews display and scale
4. Confirm non-preview files show the fallback supported-formats message
5. Delete a file on disk → run Health check → confirm integrity updates while selection preserved
6. Right-click row:
   - Copy absolute path works
   - Open in Explorer opens folder (even if file missing)
   - Items hide only when path cannot be resolved

---

## Definition of Done
- Library tab shows master–detail split view
- Detail pane updates from selection without tab switching
- Preview works for supported image formats; fallback message otherwise
- Advanced section collapses/expands
- Empty-state message displays when nothing selected
- Context menu Copy/Open works and is conditionally available based on path resolvability
- Selection preserved across refresh when possible
- Tests pass
