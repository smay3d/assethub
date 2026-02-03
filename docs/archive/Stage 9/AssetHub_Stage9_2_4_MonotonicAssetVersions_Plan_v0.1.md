# AssetHub — Stage 9.2.4 Plan (v0.1)
*(Composite Snapshot Fix v1 — monotonic asset versions + true snapshot carry-forward)*

## Goal

Fix the two Stage 9.2 Extension blockers for composite assets (texture_set, image_sequence):

1) **Snapshot carry-forward**
- When a composite asset updates, the new asset version must be a **complete set snapshot**:
  - unchanged files are carried forward from the **latest non-discarded** version
  - changed/added files override or extend the snapshot cleanly
  - older versions remain intact and still represent their historical snapshot

2) **Monotonic asset versions**
- Composite assets must have strictly monotonic asset versions:
  - we **never** create a new asset version “below” the latest
  - incoming filename “vNN” is treated as *file metadata*, not as the asset’s version driver

This restores the “pipeline-believable” model:
- **Asset version** = set revision (monotonic snapshot history)
- **File version tokens** = per-file authoring label (informational; may not match other roles)

---

## Scope

### In scope
- Introduce a DB-backed membership model that supports **the same file being part of multiple versions**.
- Update composite version-up merge apply logic to:
  - base from latest non-discarded version
  - create new asset version (latest+1)
  - build snapshot membership by carry-forward + overrides
- Update all reads (Library Assets view, health aggregation, Detect review summaries) to use the membership model.

### Out of scope
- Any new UI to “force asset version to match file version” (we are locking the monotonic snapshot model).
- Sidecar snapshot export/import.
- Checksum reconcile (Stage 9.3).
- Advanced per-role conflict UI beyond what we already have.

---

## Key Decisions (Locked for 9.2.4)

1) **Base snapshot = latest non-discarded asset version**
- All carry-forward membership is taken from that version only.
- Discarded versions are ignored for base selection.

2) **Composite asset version creation is independent of file version tokens**
- For composite updates, if any change is applied:
  - create `new_asset_version = latest_non_discarded.sort_key + 1`
- Incoming parsed file versions do not affect asset version numbering.

3) **True snapshot history requires multi-version membership**
- A file must be able to appear in multiple asset versions without “moving” it out of older versions.
- Therefore, we will **not** implement snapshot carry-forward by reassigning `file.version_id` (because that destroys history).

---

## DB / Data Model Changes

### A) Schema bump: v5 → v6
Add a join table to represent version membership:

**New table: `version_file`**
- `version_id INTEGER NOT NULL REFERENCES version(id) ON DELETE CASCADE`
- `file_id    INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE`
- `added_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` *(optional but useful)*
- `PRIMARY KEY (version_id, file_id)` *(or UNIQUE on pair)*

#### Migration steps
1) Create `version_file`.
2) Backfill membership from the existing single-owner model:
   - For each `file` where `file.version_id IS NOT NULL`:
     - insert `(version_id, file_id)` into `version_file`.
3) Keep `file.version_id` temporarily for compatibility, but **treat it as deprecated**:
   - all *reads* of version membership must switch to `version_file`
   - all *writes* for membership must update `version_file`
4) Decide removal timing for `file.version_id`:
   - **v6:** keep column but stop using it for membership logic
   - future schema: remove column once stability is proven

**Important invariant after v6:**
- “Which files are in version X?” == query `version_file`.
- `file.version_id` no longer defines membership.

---

## Core Implementation Work

### 1) Membership helper layer (Qt-free)
Create/extend a DB module (name flexible):
- `src/assethub/core/db/version_membership.py`

Functions:
- `get_file_ids_for_version(conn, version_id) -> list[int]`
- `add_files_to_version(conn, version_id, file_ids, *, ignore_duplicates=True) -> int`
- `remove_files_from_version(conn, version_id, file_ids) -> int`
- `clone_version_membership(conn, src_version_id, dst_version_id) -> int`
- `get_latest_non_discarded_version(conn, asset_id) -> Version | None`
- Update existing membership ops to use `version_file` (attach/detach/repair/fork).

### 2) Detection apply: composite version-up merge uses snapshot membership
In `src/assethub/core/detection/apply.py` (or extracted helper):
- When proposal targets an existing composite asset:
  1) find `base_version = latest_non_discarded_version(asset_id)`
  2) create `new_version = create_version(sort_key_override = base_version.sort_key + 1)`
  3) `clone_version_membership(base_version → new_version)`
  4) apply incoming changes:
     - **texture_set:** override by role
       - compute role for each carried file + incoming file
       - remove old role members from `new_version` only
       - add incoming members
     - **image_sequence:** override by sequence identity (key)
       - replace sequence members in `new_version` only
  5) write `version_change_log` with payload:
     - `source_version_id`, `carried_forward_file_ids`, `removed_file_ids`, `added_file_ids`
  6) ensure commit paths are correct (avoid prior “DB locked” regressions)

**Critical:**
- No `UPDATE file SET version_id=...` for snapshot carry-forward paths.

### 3) Reads updated to membership table
Update query sites that assume `file.version_id` means membership:
- Library Assets view: “files in selected version”
- Version file counts shown in UI
- Any “missing count per version” logic
- Health aggregation should determine file membership via `version_file`

### 4) Health check behavior with discarded versions
Existing rule: discarded versions are ignored by health checks.
With `version_file`, ensure that:
- “files considered for health aggregation” is based on versions where `is_discarded=0`
- (exact implementation depends on current health query structure)

---

## UI / UX Changes (Minimal)

No new UI features required for 9.2.4.

However:
- Any UI panel that displays “files for a version” must now query via membership table.
- Confirm that existing “discard/restore” + “show discarded” toggles still behave correctly.

---

## Testing Plan

### Unit tests (Qt-free)
Add: `tests/test_version_membership_v6.py`

Coverage:
1) **Migration backfill**
- Create a v5-style DB state with `file.version_id`.
- Run migration to v6.
- Assert `version_file` contains expected pairs.

2) **Snapshot carry-forward (texture_set)**
- Existing asset with v01 containing 5 roles.
- Incoming new normal map (file token may be “lower” or “higher”, doesn’t matter).
- Apply merge:
  - creates v02 (or latest+1)
  - v02 contains full 5-role snapshot
  - v01 still contains its original 5-role snapshot

3) **Monotonic behavior**
- Existing asset latest is v05 (sort_key 5).
- Incoming file named `_v04`:
  - new version created is v06 (sort_key 6), not v04.

4) **No DB lock regression**
- Apply merge, then perform another write operation using a fresh connection in the test harness.

### Manual test
Re-run the user’s scenario suite:
- CTRL, MISVER1, MISVER2, VER cases from the handoff
- Verify:
  - new version includes carried-forward roles
  - no lower-version insertion beneath latest
  - older versions still show complete snapshots

---

## Files to Add / Modify (expected)

### Add
- `src/assethub/core/db/version_membership.py` (or similar)
- new schema migration code for v6
- `tests/test_version_membership_v6.py`

### Modify
- `src/assethub/core/db/schema.py` (schema version bump + create table)
- `src/assethub/core/db/migrations.py` (or migration runner)
- `src/assethub/core/detection/apply.py` (composite merge apply logic)
- Library Assets view / version file list query modules that currently rely on `file.version_id`
- Any membership ops modules referenced by UI actions

---

## Definition of Done

- Composite asset updates produce **complete snapshot versions** via carry-forward + override.
- Older versions remain intact and still represent their snapshot membership.
- Composite assets never create a new version below the latest (monotonic set revision).
- No DB locking regressions.
- Full pytest suite passes on Windows.
