# AssetHub — Stage 9.1 Plan (v0.1)
*(Tagging v1 — Tag Manager + Bulk Assignment + Semantic Colors)*

## Goal

Make AssetHub meaningfully usable as a **power-user organization tool** by introducing a first-class **asset tagging system**:

- Users can define a personal tag taxonomy (names + semantic colors)
- Users can apply/remove tags **in bulk** from the **Library → Assets** view
- Tags are visible in the asset list via lightweight **chips/dots** (not full-row coloring)

In “ship terms”: after 9.1, a user can ingest/detect assets (Stage 8), then quickly organize them with tags and see that organization in the Library list.

---

## Scope

### In scope
- Asset-level tags only (no file-level tagging in Stage 9)
- Schema update to support **tag colors** (`#RRGGBB`)
- Core DB helpers for tag CRUD + asset_tag assignments
- Tag Manager UI (manage tags only; assignment stays in Library)
- Library (Assets mode) updates:
  - multi-selection support
  - bulk add/remove tags actions
  - tag display column using chips/dots
- EventHub + logging for tag operations

### Out of scope
- File-level tagging
- Deep tag taxonomy features (hierarchies, namespaces, tag groups)
- Advanced filtering UI (“filter by tag” panels, saved searches)
- Any filesystem writes/moves/renames
- Project association / linting (Stage 9.4+ / Stage 10+)

---

## Deliverables

### A) Schema v4: Tag colors

1) Bump:
- `LATEST_SCHEMA_VERSION = 4`

2) Add migration:
- `_migrate_to_v4()` registered in `_MIGRATIONS`

3) Apply v4 changes:
- **tag**
  - Add column: `color TEXT NOT NULL DEFAULT '#808080'`
  - Existing rows (if any) are backfilled automatically via SQLite default.

**Notes / constraints**
- Colors are stored as a hex string `#RRGGBB` (confirmed decision).
- Migration must be forward-only and idempotent.

---

### B) Core DB helpers: Tags + AssetTag operations (Qt-free)

Add a small DB module:
- `src/assethub/core/db/tags.py`

Core dataclass update:
- `src/assethub/core/model/tag.py` → include `color: str`

APIs (names flexible, but keep them small and testable):

#### Tag CRUD
- `list_tags(conn) -> list[Tag]` (ORDER BY lower(name), id)
- `create_tag(conn, *, name: str, color: str) -> Tag`
  - validates:
    - non-empty name
    - hex format `#RRGGBB` (basic validation only)
  - enforces uniqueness by name (existing schema already has UNIQUE(name))
- `rename_tag(conn, *, tag_id: int, new_name: str) -> None`
- `set_tag_color(conn, *, tag_id: int, color: str) -> None`
- `delete_tag(conn, *, tag_id: int) -> None`
  - cascades through `asset_tag` via FK

#### Assignment helpers (bulk-first)
- `list_tags_for_asset_ids(conn, asset_ids: list[int]) -> dict[int, list[Tag]]`
  - returns mapping `{asset_id: [Tag, ...]}`
  - deterministic ordering of tags per asset: `ORDER BY lower(tag.name), tag.id`
- `add_tags_to_assets(conn, *, asset_ids: list[int], tag_ids: list[int]) -> int`
  - uses INSERT OR IGNORE into `asset_tag`
  - returns count of new rows inserted (best effort)
- `remove_tags_from_assets(conn, *, asset_ids: list[int], tag_ids: list[int]) -> int`
  - deletes matching join rows
  - returns count deleted (best effort)
- Optional convenience:
  - `set_asset_tags_exact(conn, *, asset_id: int, tag_ids: list[int]) -> None`
    - useful later, but not required for v0.1

**Notes**
- All helpers must be safe for multi-select workflows (asset_ids list may be large).
- No tagging logic in scanner/detector; tags are user organization metadata.

---

### C) UI: Tag Manager dialog (manage tags only)

Add:
- `src/assethub/ui/dialogs/tag_manager_dialog.py`

Requirements:
- Purpose is managing tag definitions, not assignment.
- Shows a simple list/table of tags with:
  - Name
  - Color swatch (and/or hex text)
- Actions:
  - Add Tag (name + color)
  - Rename Tag
  - Change Color (color picker)
  - Delete Tag (confirm)
- Lightweight and stable:
  - No duplicate asset listing here.
  - No per-asset assignment UI here.

Behavior:
- When tags are changed:
  - emit `EventHub.db_changed` with reason `"tags_changed"` (payload includes basic counts / ids)
  - write a user-visible log line (e.g. `Created tag "final" (#ff8800)`)

---

### D) Library → Assets mode: Bulk assignment + Tags display

#### D1) Enable multi-selection in assets table
Update `AssetsLibraryWidget` so the assets table supports standard desktop multi-select:
- `ExtendedSelection`
- Right-click behavior must preserve existing selection (match Stage 7.5.2 pattern used in file list)

Selection model:
- Current row still drives detail pane (versions/files)
- Selected set drives bulk actions (tag assign/remove)

#### D2) Assets context menu actions
Extend the asset context menu to include:

- **Tags → Add…**
- **Tags → Remove…**
- **Manage Tags…** (opens Tag Manager dialog)

“Add/Remove” opens a small selection dialog (not the manager) that:
- lists existing tags
- supports quick search (optional but recommended)
- allows selecting multiple tags
- Apply / Cancel

On apply:
- call DB helpers (`add_tags_to_assets` / `remove_tags_from_assets`)
- log result:
  - e.g. `Added tags [final, progress] to 12 asset(s).`
- emit `db_changed` with reason `"asset_tags_changed"`

#### D3) Display tags in the asset list (chips/dots)
Add a **Tags** column to the Assets table.

Implementation approach (v0.1 acceptable):
- Store per-row tag payload in model user roles (e.g. list of `(name, color)` or a compact JSON string)
- Render:
  - simple text fallback: `final, progress, ...`
  - plus a lightweight visual: chips/dots via `QStyledItemDelegate` for the Tags column
    - keep it subtle (no full-row background)
    - if too many tags: draw first N (e.g. 3) + `+X`

Data flow:
- On `refresh()`, after `list_assets(...)`:
  - gather all asset_ids in the view
  - call `list_tags_for_asset_ids(...)`
  - populate the Tags column display + cached payload

**Notes**
- This stage does not require tag-based filtering UI, but search may optionally include the tag text if easy.
- Ensure the Tags column does not destabilize the current filter proxy assumptions (update proxy column indices if needed).

---

## Data Flow / Wiring

1) User creates/edits tags in Tag Manager:
- DB mutations via `core/db/tags.py`
- UI logs outcome
- `EventHub.db_changed(reason="tags_changed")`

2) User selects assets in Library → Assets:
- context menu → Add/Remove tags
- DB mutations via `core/db/tags.py`
- UI logs outcome
- `EventHub.db_changed(reason="asset_tags_changed")`

3) `AssetsLibraryWidget` listens to db_changed (already does) and refreshes:
- `list_assets(...)`
- `list_tags_for_asset_ids(...)`
- update Tags column + chips rendering

---

## Files to Add / Modify

### Modify
- `src/assethub/core/db/schema.py` (schema v4 + migration)
- `src/assethub/core/model/tag.py` (add `color`)
- `src/assethub/ui/views/assets_library_widget.py`
  - multi-select
  - tags column + context menu actions
  - refresh flow calls tag query helper(s)

### Add
- `src/assethub/core/db/tags.py`
- `src/assethub/ui/dialogs/tag_manager_dialog.py`
- `src/assethub/ui/dialogs/tag_select_dialog.py` *(or equivalent lightweight picker used by add/remove actions)*
- `src/assethub/ui/delegates/tag_chips_delegate.py` *(optional but recommended for clean chips/dots rendering)*

### Optional / only if needed
- `src/assethub/core/events/event_hub.py` (only if a more specific signal is required; prefer reusing `db_changed`)
- `tests/...` additions (see below)

---

## Testing Plan

### Unit tests (Qt-free)
Add:
- `tests/test_db_tags.py`

Coverage:
1) Migration:
- Fresh DB initializes at schema v4
- v3 → v4 migration adds `tag.color` and is idempotent

2) Tag CRUD:
- create_tag enforces uniqueness
- rename_tag updates name
- set_tag_color updates color
- delete_tag removes tag and cascades asset_tag rows

3) Assignment:
- add_tags_to_assets inserts expected rows and is idempotent (INSERT OR IGNORE)
- remove_tags_from_assets deletes expected rows
- list_tags_for_asset_ids returns deterministic ordering

### Manual smoke test (Windows)
1) Launch app on existing DB (auto-migrates) and fresh DB (creates v4)
2) Library → Assets:
- create 2–3 tags (distinct colors)
- select multiple assets → add tags
- verify Tags column updates and chip visuals are subtle/readable
- remove tags from selection
3) Confirm no regressions in:
- Files mode in Library
- Scan/Detect flows
- App log displays tag operation summaries

---

## Definition of Done

- App launches cleanly on fresh DB and migrates v3 → v4 without errors.
- Tag Manager can create/rename/recolor/delete tags.
- Library → Assets supports multi-select and can bulk add/remove tags.
- Assets list shows a Tags column with readable chip/dot styling (text fallback acceptable).
- Tag operations emit `db_changed` and produce clear log entries.
- `python -m pytest` passes on Windows.
