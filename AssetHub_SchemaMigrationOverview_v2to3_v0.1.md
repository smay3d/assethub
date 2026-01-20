# AssetHub — Schema Migration Record (v2 → v3)

Stage 8 Design Draft — **DB Schema Upgrade: Asset/Version Foundations + Change Logging**

## Purpose

Schema v3 upgrades AssetHub from a file-only workflow into an asset-aware system that supports:

- **Explicit asset typing** (`generic`, `image_sequence`, `texture_set`) derived from rules.
- **Stable auto-detect identity** via `asset.key` (rule-derived) distinct from user-facing `asset.name`.
- **Storage-scoped uniqueness** to avoid collisions across messy drives.
- **Artist-friendly versioning** with:
    - internal monotonic integer (`sort_key`)
    - user-facing label defaulting to **vNN** (`label`, `scheme`)
- **Mutable versions with accountability** via a per-action **version change log** table.

This migration is designed to be **idempotent**, **safe**, and compatible with rescans (disk remains authoritative).

---

## Summary of Changes

### New Concepts Introduced

- Asset identity is explicitly represented by:
    - `asset.type` (rule-derived category)
    - `asset.key` (stable grouping key from filename/rules)
    - `asset.name` (user-facing display name; editable)
- Version identity is represented by:
    - `version.sort_key` (integer, internal truth)
    - `version.label` (user-facing label, default `v01`)
    - `version.scheme` (default `vNN`)
- All version membership modifications are recorded as **one log row per action** in `version_change_log`.

---

## Schema Changes in Detail

## 1) Table: `asset` (ALTER)

### Add columns

- `storage_id INTEGER NOT NULL`
    - FK → `storage(id)`
    - Defines uniqueness boundary; assets are scoped per storage root.
- `type TEXT NOT NULL DEFAULT 'generic'`
    - Rule-derived: `generic | image_sequence | texture_set`
- `key TEXT NOT NULL`
    - Stable rule-derived grouping identity (e.g., sequence base without frame token)
- `updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`

### Constraints / indexes

- Add uniqueness constraint:
    - `UNIQUE(storage_id, type, key)`

### Notes

- `name` remains the **user-facing display name**.
- `slug` may remain present but is not relied on for v0 asset identity.

---

## 2) Table: `version` (REBUILD)

Schema v2 assumes semver as the primary version value. Schema v3 shifts to a more flexible model: internal monotonic integer + user-facing label.

### New / replacement columns

- `label TEXT NOT NULL`
    - Default display label (`v01`, `v02`, …)
- `sort_key INTEGER NOT NULL`
    - Internal version order (1, 2, 3…)
- `scheme TEXT NOT NULL DEFAULT 'vNN'`
    - Version label scheme (v0 defaults to `vNN`; semver support remains possible later)
- `updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`

### Constraints / indexes

- Add uniqueness constraint:
    - `UNIQUE(asset_id, sort_key)`
- Index:
    - `idx_version_asset_sort (asset_id, sort_key)`

### Migration mapping (v2 → v3)

For existing rows:

- If old `semver` is present:
    - Set `label = semver` (no parsing required for v0 safety)
    - Set `scheme = 'vNN'` (initial default; can be refined later)
    - Set `sort_key = 1` (v0 safe fallback)
- If no `semver`:
    - Set `label = 'v01'`
    - Set `scheme = 'vNN'`
    - Set `sort_key = 1`

**Rationale:** since current DB is test data and disk is authoritative, we prefer a deterministic, low-risk mapping. Future work may parse legacy version strings into `sort_key` if needed.

---

## 3) Table: `version_change_log` (NEW)

Records all version membership edits. **One row per user action.**

### Columns

- `id INTEGER PRIMARY KEY`
- `version_id INTEGER NOT NULL`
    - FK → `version(id)`
- `action_type TEXT NOT NULL`
    - Examples: `attach_files`, `detach_files`, `repair_in_place`, `fork_new_version`
- `summary TEXT NOT NULL`
    - Short human description
- `payload_json TEXT NOT NULL`
    - JSON describing changes, e.g.:
        - `added_file_ids: []`
        - `removed_file_ids: []`
        - `replaced: [{missing_file_id, new_file_id, old_checksum?, new_checksum?}]`
        - `checksum_mismatch: true/false`
- `created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`

### Index

- `idx_log_version_id (version_id)`

---

## 4) Table: `file` (optional v0 enhancement)

No behavioral changes; `file.version_id` remains the relationship anchor (one version per file).

Optional (recommended for auditing):

- Add `updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`

Index (if not already present):

- `idx_file_version_id (version_id)`

---

## Optional Future Table (Not required for v3)

### `file_checksum` cache (deferred unless needed)

A caching layer to store computed checksums:

- `file_id` (PK/FK)
- `algo`, `checksum`, `size_bytes`, `mtime_unix`, `computed_at`

**Not required for v3 migration**; detection v0 can be name/rule based, with checksums used opportunistically later.

---

## Migration Procedure (Recommended Steps)

## Step 0 — Preconditions

- Ensure schema initialization and migration are idempotent:
    - v2 should migrate cleanly to v3 without double-applying changes.

## Step 1 — Bump Schema Version

- Set `LATEST_SCHEMA_VERSION = 3`
- Add a migration entry: `migrate_2_to_3()`

## Step 2 — ALTER `asset`

- Add `storage_id`, `type`, `key`, `updated_at`
- Backfill `updated_at` to current timestamp (default handles new rows)
- Backfill required values if needed (in test DB only):
    - If existing `asset` rows exist, they need:
        - `storage_id` assigned (choose the storage root that contains its files, or default to first storage in test data)
        - `type='generic'`
        - `key` derived from `name` or placeholder (`key = slug or name`)
            
            *(Given test DB context, placeholder is acceptable; real population comes from detection/manual actions.)*
            

## Step 3 — REBUILD `version`

SQLite constraint changes generally require a rebuild:

1. Create `version_new` with v3 columns and constraints.
2. Copy data from `version` to `version_new`:
    - Map fields as described above.
3. Drop old `version`.
4. Rename `version_new` → `version`.
5. Recreate indices.

## Step 4 — CREATE `version_change_log`

- Create table + index.

## Step 5 — Optional ALTER `file`

- Add `updated_at` if we adopt it now.
- Create index on `version_id` if missing.

## Step 6 — Post-migration integrity checks

- All FKs valid:
    - `version.asset_id` exists
    - `file.version_id` references `version.id` or is NULL
- Uniqueness respected:
    - `(storage_id, type, key)` unique
    - `(asset_id, sort_key)` unique

---

## Behavioral Guarantees After Migration

- Existing file-level workflows remain intact.
- Assets are now:
    - **typed** (for detection semantics)
    - **storage-scoped** (reduces collisions)
    - **keyed** (stable identity)
- Versions are:
    - **mutable** (artist-friendly repair)
    - **tracked** (change log provides accountability)
    - **internally sortable** via `sort_key`
    - **displayed** via `label` (default vNN)

---

## Notes for Stage 8 Implementation

- Auto-detect will only assign **unowned** files (`file.version_id IS NULL`).
- Repair flows will support:
    - “Repair in place” (mutable) with warning + log if checksum mismatch
    - “Fork new version” (creates next `sort_key`, label `vNN`, logs action)
- Detect Assets entry point lives in **Scan tab** and opens a **modal proposals dialog**