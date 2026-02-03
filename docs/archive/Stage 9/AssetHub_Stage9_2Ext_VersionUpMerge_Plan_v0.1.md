# AssetHub — Stage 9.2.2 Plan (v0.1)
*(Version-up Merge v1 — integrate new files into existing assets as new versions)*

## Goal

Make versions *useful in practice* by supporting **incremental updates**:

When new file(s) are detected that match an **existing asset identity** (same detection base key),
AssetHub should propose (and apply) a **version-up merge** instead of creating a new asset.

Example:
Existing texture_set asset has latest v04. A new `*_normal_v05.tif` appears.
AssetHub should propose:
- create version v05 for that asset
- attach the updated normal_v05 file
- carry forward unchanged files from v04 into v05 membership
- keep history intact (v04 remains)

This is the “pipeline-believable” update loop.

---

## Scope

### In scope
- During Detect Assets, identify candidates that match existing assets by base key.
- For those candidates, generate merge proposals:
  - “Create new version and carry forward previous files”
  - “Replace files within an existing version” (limited v1 support; mostly warn/skip)
- UI supports reviewing and applying merges alongside normal proposals.
- Minimal DB changes if required to support “carry forward” semantics safely.

### Out of scope
- Checksum-based matching (Stage 9.3 remains checksum reconcile)
- Deep diff UI for arbitrary assets beyond a simple file list preview
- Automatic project association behavior
- Advanced policies (e.g., per-channel version families, ignore sets)

---

## Key Decisions (Locked for v1)

1) **Match identity by detection base key**, not filename literal:
   - For texture sets: the same normalized base key used in detection (version tokens stripped)
   - For generic assets: base key is the normalized asset name currently used in detection

2) **Latest version** is determined by highest `version_num` on that asset
   - Discarded versions are ignored for “latest” unless no non-discarded versions exist.

3) **Version-up trigger (v1 rules)**
   - If incoming file(s) have a parsed version number `new_v`:
     - If `new_v > latest_v` → propose **version-up merge**
     - If `new_v == latest_v` → propose **replace-in-same-version** (warn + optional apply)
     - If `new_v < latest_v` → default to **do not merge** (treat as separate candidate) for v1
   - If incoming has **no parsed version**:
     - v1: do not auto-merge; treat as normal proposal (future enhancement can offer manual merge)

4) **Carry-forward semantics**
   - New version membership should include:
     - all files from the previous “source version” (typically latest_v)
     - plus incoming updated files (which override same “role” if identifiable)
   - If we cannot identify “role” reliably (e.g., generic assets), carry-forward is still allowed:
     - v1 rule: carry-forward all previous files, then attach new file(s) (may create duplicates).
     - UI will show the resulting membership list for user review.

5) **No file duplication on disk** (DB membership only)
   - This is a pure database operation: we’re linking existing file records into a new version.

---

## DB / Data Model Requirements

### A) Confirm membership constraints
We need to confirm whether `version_file` (or equivalent) allows:
- the same file_id to be linked to multiple versions, OR
- only one active membership

**If multi-version membership is already allowed:**
- no schema change needed.

**If not allowed:**
- implement carry-forward by *copying membership rows* but referencing the same file record,
  which requires allowing the same file_id to be linked to multiple versions.
- If current schema forbids this, we must adjust constraints in the membership table.

Deliverable:
- A DB-level helper to “clone” version membership from source_version → new_version.

### B) New DB helpers (Qt-free)
Add module (or extend existing version ops):
- `src/assethub/core/db/version_merge.py` *(name flexible)*

Functions:
- `find_existing_asset_by_key(conn, *, asset_type: str, asset_name: str, detection_key: str | None) -> int | None`
  - Implementation may use existing asset lookup methods; keep deterministic.
- `get_latest_version_for_asset(conn, *, asset_id: int, include_discarded: bool = False) -> Version | None`
- `clone_version_membership(conn, *, src_version_id: int, dst_version_id: int) -> int`
  - returns count of memberships cloned
- `apply_version_up_merge(conn, *, asset_id: int, new_version_num: int, src_version_id: int, attach_file_ids: list[int]) -> ApplyResult`
  - creates new version
  - clones membership
  - attaches incoming file_ids
  - logs changes (version_change_log if present) and **commits correctly** (no lock regression)

---

## Detection Pipeline Changes

### A) Enrich proposals with a stable “merge key”
When detection produces an asset proposal, also compute:
- `match_key` (string) used to identify existing assets
  - texture_set: normalized base key (strip channel + strip version token)
  - generic: normalized name (strip version token)

Store `match_key` in the proposal model so apply can use it.

### B) Merge candidate identification at detect/apply time
During “Detect Assets” review / before apply:
- For each proposed asset group, query DB:
  - does an existing asset already exist with the same `match_key` and same asset_type?
- If yes, and files are not already owned:
  - compute new_v (parsed max version among incoming files if present)
  - compute latest_v for existing asset
  - if v1 trigger rule matches, mark proposal as a **merge proposal**.

### C) Conflict interaction (Stage 9.2 behavior)
If a proposal is both:
- a version mismatch set (multiple versions within incoming files)
- and also matches an existing asset

Then:
1) run the existing mismatch resolver first (Split vs Force)
2) treat each resolved group as a candidate merge proposal with a single version number

---

## UI / UX Changes

### A) Detect Assets review UI
Extend the detect assets table to show when a proposal will merge:
- Column or badge: “MERGE → existing asset”
- Show existing asset name + latest version number (read-only)

Actions/controls:
- For merge proposals, default action is “Merge (version-up)”
- Allow user to switch to:
  - “Create new asset instead” (escape hatch)
  - “Skip” (existing behavior)

### B) Apply output logging
After apply:
- Log per merge:
  - asset name
  - source version → new version
  - carried-forward count
  - attached updated file count

No filesystem operations.

---

## Testing Plan

### Unit tests (Qt-free)
Add:
- `tests/test_version_merge.py`

Coverage:
1) Given existing asset with v04 and 5 files:
   - incoming file normal_v05 → apply merge creates v05
   - v05 has 5+ memberships (carried + updated)
2) Ensure carried-forward cloning works and is deterministic.
3) Ensure apply commits properly (regression test for “database is locked”):
   - run a merge, then immediately run a scan/health DB write in the test harness (or simulate by opening new connection and writing) without lock errors.

### Manual test
1) Create texture_set v04 in DB, with mixed versions allowed historically.
2) Drop a single updated file `*_normal_v05` into storage root.
3) Detect assets:
   - proposal should show “merge into existing”
4) Apply:
   - v05 created
   - v05 includes previous set + updated file
   - UI shows versions with correct numbers

---

## Definition of Done

- Detect identifies when incoming files match an existing asset identity and proposes merge.
- Apply can create a new version and carry forward previous membership + attach incoming updates.
- Existing Stage 9.2 mismatch dialog still works and integrates correctly with merging.
- No DB locking regressions.
- Full pytest suite passes on Windows.
