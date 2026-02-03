# AssetHub — Stage 8.1 Plan (v0.1)

## Goal

Land **schema v3** (assets/versions foundations + change log) and a **minimal, testable DB API surface** for asset/version operations, while preserving all Stage 7 file-level workflows.

In “ship terms”: after 8.1, the app can safely run on a v3 database and has the backend primitives we’ll use to build detection + asset UI in later 8.x sub-stages.

---

## Deliverables

### A) Schema v3 migration (v2 → v3)

1) **Bump** `LATEST_SCHEMA_VERSION = 3`.
2) Add `_migrate_to_v3()` and register it.
3) Apply the v3 changes:

- **asset**
  - Add: `storage_id INTEGER NOT NULL`, `type TEXT NOT NULL DEFAULT 'generic'`, `key TEXT NOT NULL`, `updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
  - Add uniqueness: `UNIQUE(storage_id, type, key)`
  - Migration approach: **table rebuild** (preferred) so `storage_id NOT NULL` is enforceable and existing rows can be backfilled safely.

- **version** (rebuild)
  - Replace semver model with:
    - `label TEXT NOT NULL`
    - `sort_key INTEGER NOT NULL`
    - `scheme TEXT NOT NULL DEFAULT 'vNN'`
    - `updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
  - Constraints:
    - `UNIQUE(asset_id, sort_key)`
    - `idx_version_asset_sort (asset_id, sort_key)`

- **version_change_log** (new)
  - `id INTEGER PRIMARY KEY`
  - `version_id INTEGER NOT NULL` FK
  - `action_type TEXT NOT NULL`
  - `summary TEXT NOT NULL`
  - `payload_json TEXT NOT NULL`
  - `created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
  - Index: `idx_log_version_id (version_id)`

- **file**
  - Add: `updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
  - Keep existing FK structure: `file.version_id` stays the anchor.

**Notes / constraints**
- We currently expect **no legacy `version` rows**, but migration logic must be future-safe:
  - If legacy `version.semver` exists, map it to `label` (no parsing in v0).
  - Assign a deterministic `sort_key` ordering (e.g., `ROW_NUMBER() OVER (ORDER BY id)` or equivalent stable order when copying).
- Migration must be **idempotent** and **forward-only**.

### B) DB Layer Core APIs (Qt-free)

Add small DB helpers (module-level functions and/or slim classes) to support:

- **Assets**
  - `create_asset(storage_id, type, key, name, slug=None) -> Asset`
    - storage-scoped uniqueness: create-or-fetch by `(storage_id, type, key)`
  - `get_asset(asset_id) -> Asset | None`
  - `list_assets_for_storage(storage_id) -> list[Asset]`

- **Versions**
  - `create_version(asset_id, *, label=None, scheme='vNN') -> Version`
    - chooses next `sort_key` (= max+1, else 1)
    - default label from scheme: `vNN` → `v01`, `v02`, ...
  - `get_version(version_id) -> Version | None`
  - `list_versions_for_asset(asset_id) -> list[Version]` (sorted by `sort_key`)

- **Resolution helpers**
  - `resolve_file_to_asset_version(file_id) -> (asset, version) | None`
    - uses joins through `file.version_id → version.asset_id → asset`

### C) Minimum logging for schema writes

- Log on startup (via `AppContext.initialize_core_services`) a single summary line after schema initialization, e.g.:
  - `INFO DB schema ready (v3)`

(We keep DB helpers pure; later UI/actions will log outcomes per operation.)

---

## In Scope

- Schema v3 migration implementation in `assethub.core.db.schema`.
- Adding new DB helper modules for asset/version primitives.
- Updating core model dataclasses for `Asset` and `Version` to reflect v3.
- Updating any tests and settings snapshot expectations impacted by schema v3.

## Out of Scope

- Detection engine / rules loader (8.3).
- Any UI for assets/versions (8.4–8.5).
- Version membership operations and change log writes from user actions (8.2).
- Any file system writes/moves/renames.

---

## Data Flow / Wiring

- **Startup:**
  1) DB connection opens.
  2) `initialize_schema(conn)` ensures tables + runs migrations.
  3) Context logs: `DB schema ready (v3)`.

- **Later sub-stages:**
  - Detection/apply and manual operations will call these DB helpers and emit user-facing log messages at the UI/action layer.

---

## Files to Add / Modify

### Modify
- `src/assethub/core/db/schema.py`
- `src/assethub/context.py` (startup log line)
- `src/assethub/core/model/asset.py`
- `src/assethub/core/model/version.py`
- Any tests that assert schema version values (expected to change from `2` → `3`).

### Add
- `src/assethub/core/db/assets.py` (or similar)
- `src/assethub/core/db/versions.py` (or similar)

---

## Testing Plan

1) **Schema init / migration**
- Fresh in-memory DB: `initialize_schema()` results in schema version `3`.
- Simulated v1/v2 DB: `initialize_schema()` migrates to `3` and is idempotent (second call is a no-op).

2) **DB helper smoke**
- Create storage row(s) and create asset/version; validate uniqueness and ordering:
  - `create_asset()` returns same asset for same `(storage_id, type, key)`
  - `create_version()` returns `sort_key` 1 then 2, and `label` `v01`, `v02` by default.

3) **Stage 7 regression**
- Run full pytest suite; ensure no UI import tests break.

---

## Definition of Done

- App launches on:
  - a fresh DB (creates schema v3)
  - an existing v2 DB (migrates to v3)
- Stage 7 file workflows still operate normally (scan, library, health, delete-missing).
- Tests pass (updated expectations for schema version `3`).
- Startup log shows a clear schema-ready message.
