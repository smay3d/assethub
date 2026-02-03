# AssetHub — Stage 9 Outline Summary (High-Level) v0.1
Date: 2026-01-23  
Purpose: Re-center AssetHub toward **power-user CG pipeline organization workflows** now that Stage 8 asset ingest is working.

---

## 0) Stage 9 North Star
Stage 9 shifts focus from “asset ingest exists” to “daily-driver organization tool for power users.”

Primary user value pillars:
- **Fast organization primitives** (tags, bulk actions, filters, visual clarity)
- **Identity + reconcile** (checksum-based healing of missing records; dupe warnings)
- **Version semantics that match real pipelines** (non-1 starting versions, discard/hide old versions, mismatched multi-file versions)
- **Project context (metadata-first)** (project association + scanning updates; linting deferred)

---

## 1) Core User Flows (Aligned)
### 1.1 Main Flow (Primary)
Register Storage Roots → Scan/Ingest Files → Detect Assets/Versions → User Tags Assets (personal taxonomy, bulk)

### 1.2 Sub Flow (Projects)
Register Storage Roots → Scan/Ingest Files → Detect Project Directories → Associate Assets to Projects → (Later) Lint/Conventions

---

## 2) Tagging System v1 (Stage 9 priority)
### 2.1 Scope
- **Asset-level tags only** for Stage 9.
- File-level tagging is explicitly deferred (low ROI; “generic assets” cover single-file cases).
- Tags are **user-defined taxonomy** and **semantic colors** (user-chosen).

### 2.2 UX Decisions
- **Tag Manager UI** is for *managing tags only* (create / rename / delete / recolor).
  - No duplicate “asset assignment” workspace in Tag Manager.
- Tag assignment happens in **Library (Assets view)**:
  - Multi-select → context menu actions: “Add Tag…”, “Remove Tag…”
  - Designed for **bulk apply/remove**
- Tag display uses **chips/dots** to avoid flooding list view with solid color.

### 2.3 Data Decisions
- Tag color storage: **hex string `#RRGGBB`** (confirmed).

---

## 3) Checksum Ingest + Missing-Reconcile v1
### 3.1 Goal
When ingesting files, compute checksum and compare against **MISSING** records:
- If match: offer reconcile options to prevent DB drift and duplicate “missing” noise.

### 3.2 Scope (Stage 9)
- **Option A**: checksum only **newly ingested files** (not “hash everything” by default).
- **Checksum algorithm**: **SHA-256** (confirmed).

### 3.3 Staleness Policy (Critical Decision)
If checksums are stored, do **not** assume they remain true forever.
- Store checksum plus a lightweight “validity fingerprint” at time of hashing:
  - file **size** + **mtime** (or mtime_ns)
- A stored checksum is considered **valid only if** current (size, mtime) still match.
- If mismatch: checksum is treated as **stale/unknown** and recalculated **only when needed**.

### 3.4 Dupe Scenario
- If checksum matches an *existing non-missing* record: **warn only** (for now).
- User is always allowed to keep duplicates.
- Multi-path identity model is deferred.

### 3.5 UX Decision
- No modal spam. Use a **single bulk reconcile dialog** (table-based),
  visually similar to (or reused design language from) the Detect Assets review dialog.

---

## 4) Versioning Upgrades v1
### 4.1 Goals
- Versions should match reality:
  - support assets received at v6 (do not force starting at v1)
  - parse version tokens from filenames when present
  - keep history; allow “discarded” versions

### 4.2 Detection Behavior
- If version number is present in name: assign/create that version number.
- Manual overrides allowed (version number/label edits).

### 4.3 Discarded Versions (Behavior)
- Always keep history.
- Versions can be marked **discarded**:
  - treated as “exists in DB but intentionally not tracked on disk”
  - health checks should **not** report discarded-version files as missing/noisy
  - UI can hide discarded versions by default, with a toggle to show them

### 4.4 Edge Case: Multi-file Version Mismatch
Example: texture set where albedo is v03 and normal is v05.
Stage 9 approach:
- Detect mismatch and flag as **version conflict**.
- Require user resolution with simple choices:
  1) **Split into separate versions** based on file version numbers found
  2) **Force into one version** (user chooses target version)
- More complex rules (per-channel versioning, ignore rules) are deferred.

---

## 5) Projects v0 (Metadata-First; No Linting Yet)
### 5.1 Identification
- Detect project roots using **workspace.mel** (simple, reliable first target).
- Houdini project extraction ($JOB from .hip) is deferred.

### 5.2 Storage + Updates
- Project directories are stored **internally** (DB/config) and updated on scan.
- Manual “Register Project Root” flow (similar to storage roots) is included.

### 5.3 Assignment
- Assets detected under a project root become associated with that project.
- Library supports sorting/filtering by project.

### 5.4 Deferred to Stage 10+
- Project lawmaking UI (tree/block system)
- Linting and convention enforcement
- Automatic renames/moves/restructure
- Any write operations that violate the no-write-by-default principle

---

## 6) Stage 9 Trajectory (Sub-stage Ordering)
Agreed high-level ordering:
1) **Stage 9.1 — Tagging v1** (Tag Manager + bulk assignment + chips + filter/sort hooks)
2) **Stage 9.2 — Versioning realism v1** (parse/override + discard + conflict resolution)
3) **Stage 9.3 — Checksum reconcile v1** (new-file hashing + missing-reconcile dialog + dupe warnings)
4) **Stage 9.4 — Projects v0** (workspace.mel detection + internal storage + assignment + basic UI)

---

## 7) Guardrails / Non-Goals (Stage 9)
- No file-moving/renaming enforcement (maintain no-write-by-default)
- No deep “project laws” editor or linter execution
- No multi-path identity model for duplicates
- No Houdini project parsing (Stage 10+)
- No file-level tagging (deferred)

---

## 8) Next Step
Use this summary as the reference document when drafting the first concrete sub-stage plan:
- Draft **Stage 9.1 Tagging v1 Plan** with deliverables, UI surfaces, schema changes, tests, and Definition of Done.
