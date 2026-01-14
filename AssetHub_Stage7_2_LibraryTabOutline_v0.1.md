# AssetHub — Stage 7.2 Library Tab v0.1 Implementation Plan

## Goal
Expose the indexed `file` records in a **Library** tab that supports:

- Display of DB-tracked files (from `file` + `storage` tables)
- Sorting by column header
- Search (primarily by **filename**, also by relative path)
- Basic dropdown filters (storage root, integrity state)
- A developer toggle to show/hide “hidden” columns (IDs, raw fields)
- Emits selection signal (`file_id`) for Stage 7.3 Detail tab

---

## Design Notes Incorporated

### 1) “Show hidden attributes” dev toggle
Add a **checkbox**: `Show hidden columns`.

- Default **OFF** (user-facing view)
- When ON: reveal hidden columns like IDs and raw timestamps/created_at

Implementation detail: keep all columns in the model, and toggle visibility in the view using `QTableView.setColumnHidden()`.

### 2) Search should support filename
Search should primarily match **filename**, not storage root.

- We’ll add a **Filename** column (computed from `relative_path` basename).
- Search matches:
  - Filename (primary)
  - Relative path (secondary)
- Storage root filtering belongs in the **Storage filter dropdown** (not in search).

---

## UI Layout (Library Tab)

### Top Bar
- Search box: `Search filename or path…`
- Dropdown: `Storage` (All + each registered root)
- Dropdown: `Integrity` (All / OK / MISSING / UNRESOLVED)
- Checkbox: `Show hidden columns`
- Button: `Refresh`

### Main Table
- `QTableView` (Model/View)
- Single-row selection
- Column sorting enabled (click headers)

### Footer / Status
- Label: `Showing N files (of M)` (M optional; N required)

---

## Data Model Approach

### Recommended stack
- `FileTableModel(QAbstractTableModel)` holds all rows currently loaded.
- `QSortFilterProxyModel` provides:
  - Sorting
  - Search + dropdown filtering (override `filterAcceptsRow`)

Why:
- Scales better than QTableWidget
- Clean separation of “what data exists” vs “how it’s filtered/sorted”

---

## Columns

### User-facing (default visible)
1. Storage (storage.name)
2. Filename (basename of relative_path)
3. Relative path (file.relative_path)
4. Size (human readable, derived from size_bytes)
5. Modified (formatted, derived from mtime_unix)
6. Integrity (file.integrity_state)

### Hidden/dev columns (visible when checkbox ON)
- File ID (file.id)
- Storage ID (file.storage_id)
- Version ID (file.version_id)
- Raw size_bytes
- Raw mtime_unix
- created_at

> Note: We keep raw fields available for debugging and to avoid losing information that might matter later.

---

## DB Query (Stage 7.2)

Single query to load rows for the table model:

- Join storage name for display:
  - `SELECT file.id, file.version_id, file.storage_id, storage.name, file.relative_path,
           file.integrity_state, file.size_bytes, file.mtime_unix, file.created_at
     FROM file
     JOIN storage ON storage.id = file.storage_id`

The Filename column is computed in Python from `relative_path`.

### Optional safety limit (recommended)
Add a hard cap (e.g., 10,000 rows) in v0.1 to prevent UI lockups on massive libraries.
If capped, show a warning in the footer: `Showing first 10,000 files`.

---

## Filtering and Sorting Rules

### Storage filter
- Dropdown selects a storage_id (or All)
- Filter is exact match on `storage_id`

### Integrity filter
- Dropdown selects integrity state (or All)
- Filter is exact match on `integrity_state`

### Search
- Case-insensitive “contains” match against:
  - Filename (primary)
  - Relative path (secondary)

### Sorting
- Proxy model sorting enabled
- Ensure numeric sorting for:
  - size_bytes
  - mtime_unix
Implementation approach:
- Provide sort-role data for those columns as numeric (even if display is formatted)

---

## Selection Signal (for Stage 7.3)
On selection change:
- emit `file_selected(file_id: int)` (from the *source model* record)
- MainWindow will store `current_file_id`
- Detail tab will use `current_file_id` to load and display details

---

## Integration with Scan Tab (Refresh Behavior)
Library tab should support both:

1. Manual refresh (`Refresh` button)
2. Automatic refresh after scan/health completes:
   - ScanTab emits `scan_completed`
   - ScanTab emits `health_completed`
   - MainWindow wires these to `LibraryTab.refresh()`

---

## Threading / Performance
For v0.1:
- Library refresh can run on UI thread if the query is small/limited.
- If you expect large datasets, move refresh query to a worker (later refinement).

---

## Testing Plan

### Automated (pytest)
- Create temp DB schema
- Insert:
  - 1–2 storage roots
  - a handful of file rows with different integrity/paths
- Instantiate FileTableModel and verify:
  - row count
  - a few key cell values
- Instantiate proxy and verify:
  - integrity filter works
  - storage filter works
  - filename search matches expected rows

### Manual smoke test
1. Use Scan tab to register a root and scan files
2. Open Library tab and hit Refresh
3. Confirm:
   - rows appear
   - sorting works
   - integrity filter works (after deleting a file and running health check)
   - hidden checkbox reveals IDs/raw fields

---

## Definition of Done
- Library tab displays file records from DB
- Sorting works by header click
- Search matches filename + relative path
- Storage + integrity filters work
- Hidden columns toggle works
- Selection emits `file_id` for detail tab integration
