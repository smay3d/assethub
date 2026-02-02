# AssetHub — Stage 9 Handoff Snapshot (through Stage 9.2 Ext)
Date: 2026-02-02  
Purpose: Snapshot of Stage 9 progress + current blocking bugs to fix in next patch thread.

---

## 1) Where Stage 9 Started (Intent)
Stage 9 re-centered AssetHub toward **power-user CG pipeline organization**:
- Main flow: Storage Roots → Scan → Detect Assets/Versions → Tag Assets (bulk, semantic colors)
- Sub flow: Projects (metadata-first) deferred; linting/enforcement deferred to Stage 10+

---

## 2) Stage 9.1 Completed (Tagging v1) — Working & Stable
**Features delivered**
- Asset-level tags (file-level tagging deferred)
- Tag Manager (CRUD tags only; assignment stays in Library)
- Semantic tag colors stored as `#RRGGBB`
- Library → Assets: Tags column with readable chip rendering (no wrapping)
- Bulk tagging via a unified **“Edit tags…”** dialog using tri-state checkboxes
- Multi-select persistence through right-click (hotfix chain ended at 9.1.6)

**Notable fixes completed**
- Multiple iterations to fix selection collapsing on right-click in Assets view
- Resolved a typo import crash and several UI regressions
- Pytests green after stabilization

---

## 3) Stage 9.2 Completed (Versioning Realism v1) — Mostly Working
**Features delivered**
- Schema v5 added:
  - `version.is_discarded` (ignored by health checks)
  - `version.user_label` (user-visible label)
- Version parsing from filenames (e.g. `_v02`, `.v12`, `version7`)
- Detect Assets mismatch handling for composite sets:
  - Version conflict dialog appears when versions differ within a grouped set
  - Supports “Split” and “Force one version”
- UI:
  - Version label editing
  - Discard/restore versions
  - “Show discarded” checkbox
- Health check correctly ignores discarded versions
- DB lock bug fixed in 9.2.1:
  - root cause: `version_change_log` inserts were not committed in some version-edit code paths
  - fix: ensure commits occur after all writes

**Additional bug fixes**
- PySide6 QInputDialog keyword mismatch fixed (min/max → minValue/maxValue)
- Storage root removal FK failure addressed (added correct removal behavior/dialog)

---

## 4) Stage 9.2 Extension Implemented (Version-up Merge v1) — Partially Working
**Goal of extension**
When new files appear that match an existing asset identity (e.g. same texture_set base name),
Detect Assets should propose an update that:
- creates a new asset version (when appropriate)
- and (for composite assets) produces a complete “latest set” snapshot.

**What is currently working**
- Detect Assets can propose partial texture_set updates instead of demoting them to generic assets.
- Apply can create new versions for existing assets and attach the incoming file.

**What is NOT working (Current Blockers)**
### A) Snapshot carry-forward is not happening
Observed behavior in human tests:
- New version is created (e.g., v02/v03/v05) but contains only the newly ingested file.
- Logs show: `carried 0 files; attached 1 files` for texture_set updates.

Expected behavior for composite assets (texture_set, image_sequence):
- Every asset version should represent a **complete set snapshot**:
  - new version should include all roles (albedo/normal/roughness/ao/height) by carrying forward unchanged files.
  - changed role overrides older role in the new version (old remains in older version for history).

### B) Lower-version bug (non-monotonic asset versions)
Observed:
- If latest version for asset is v05 and an incoming update is `_v04`, system creates a **new v04** version beneath v05.
Expected:
- Composite assets should have **monotonic asset versions**.
- Incoming files with a version number lower than latest should **merge into latest** (or prompt), not create a new lower version.

---

## 5) Why These Bugs Matter
Without snapshot carry-forward and monotonic version behavior:
- Composite assets are hard to use in pipelines (“v05 is not the set, it’s just a delta file”)
- Version ordering becomes confusing and breaks “latest set” mental model
- Future features (Deploy/export, project linting, checksum reconcile) become harder

---

## 6) What Needs to Be Done Next (Next Patch Thread)
Target: **Stage 9.2.4 hotfix** (or equivalent) to address both blockers.

### Required fixes
1) **Texture_set snapshot carry-forward**
   - When creating a new version for a texture_set update:
     - Build membership as a complete snapshot by role.
     - Source role-membership from the latest available files (prefer highest parsed file version per role).
     - Attach the incoming file(s) and remove older role entry from the new version only (keep in old version).

2) **Prevent lower-version creation**
   - If incoming file version `new_v` is less than asset’s latest version_num:
     - default to merge into latest version (update snapshot), not create `new_v` version.
   - New version creation only occurs when `new_v > latest_v` (or when forced by user, later feature).

### Useful diagnostics for implementation verification (optional but recommended)
- SQL queries to inspect:
  - version rows for the target asset ordered by `version_num`
  - membership counts per version
- Confirm membership table allows file records to be referenced by multiple versions (if not, schema change may be required)

---

## 7) Status Summary
- Stage 9.1: ✅ Done, stable, pytests green, human tests pass.
- Stage 9.2: ✅ Done, stable after 9.2.1, mismatch resolution works, discard/labels work, locking resolved.
- Stage 9.2 Extension (version-up merge): ⚠️ Partially working.
  - ✅ detects partial updates and creates new versions
  - ❌ does not carry forward complete texture set membership
  - ❌ can create lower version numbers beneath latest

---

## 8) Next Action
Start a new patch thread using the latest repo state and implement the Stage 9.2.4 fixes:
- enforce monotonic composite version behavior
- implement snapshot carry-forward for texture_set updates (complete set per version)
