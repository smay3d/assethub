# AssetHub — Stage 8 Plan (v0.1)

Stage 8 transitions AssetHub from a file-record browser into an asset-aware system that can (a) group files into assets, (b) track versions reliably, and (c) propose safe, rule-driven auto-detection from messy storage roots.

This plan assumes Stage 8.0 (repo + docs + tests audit) is complete.

---

## Stage 8 Goals

1) **Asset semantics become real (DB + UI):** introduce `asset` + `version` meaningfully while preserving the Stage 7 file workflow.

2) **Artist-friendly versioning:** versions are **mutable** (repairable) but **accountable** via a per-action change log.

3) **Rule-driven auto-detection:** on-demand, storage-root scoped detection with a **modal proposal review** workflow.

4) **Asset-level browsing:** add an **Asset Library** view while keeping File Library available for repair and manual control.

---

## Stage 8 Non-Goals (deferred)

- User-editable rule UI (Stage 9)
- Sidecar JSON authoring/reading for assets/versions (Stage 9+)
- Project directories with enforced naming conventions (Stage 9)
- AI/heuristic “guessing” beyond explicit rules
- Writing/renaming/moving user files on disk

---

## Core Design Decisions (Locked)

### Version policy
- Versions are **mutable by default**.
- Any membership edit is **logged** (one log row per user action).
- Repair supports two explicit paths:
  - **Repair in place** (may warn if checksum mismatch)
  - **Fork new version** (create vNN next; preserves prior state)

### Asset identity
- `asset.type`: rule-derived category (`generic`, `image_sequence`, `texture_set`)
- `asset.key`: stable rule-derived grouping key (not user-editable; derived from filenames/rules)
- `asset.name`: user-facing display name (editable)
- Assets are **scoped by storage root**: uniqueness boundary `(storage_id, type, key)`

### Detection scope + safety
- Detection is **on-demand** and runs **per storage root** (Scan tab action).
- Only **unowned** files may be assigned by detection: `file.version_id IS NULL`.
- Results shown in a **modal proposals dialog**; user may edit name/type and remove files; confirm/cancel.

### Rules file
- Developer-configurable rules stored in user config: `rules/detection_rules.json`.
- `.tx` and `.rat` are explicitly excluded from detection/tracking.

---

## Schema Migration (v2 → v3)

### Objectives
- Enable asset typing, stable keys, storage scoping
- Replace semver-only version model with label+sort_key+scheme
- Add `version_change_log`

### Tables
- `asset`: add `storage_id`, `type`, `key`, `updated_at`; add unique `(storage_id, type, key)`
- `version`: rebuild to include `label`, `sort_key`, `scheme`, `updated_at`; unique `(asset_id, sort_key)`
- `version_change_log`: new
- `file`: optional `updated_at` (recommended)

A migration record should be maintained separately (see schema migration record drafted in design discussion).

---

## Stage 8 Sub-Stages

### 8.1 — Schema v3 + DB Layer Core
**Goal:** Land schema v3 migration and core DB APIs for assets/versions.

**Deliverables**
- Migration `v2 → v3` implemented and idempotent.
- DB repository/services for:
  - create asset (storage-scoped)
  - create version (sort_key + vNN label)
  - query asset/version by ids
  - list assets for storage root
  - list versions for asset
  - resolve file → (asset, version)

**Definition of Done**
- App launches on fresh DB and upgraded v2 DB.
- All existing Stage 7 workflows still pass manual smoke.
- All DB writes log outcomes to the MainWindow log.

**Patch scope guidance**
- Keep changes surgical; no test suite modifications in this sub-stage unless required.

---

### 8.2 — Version Membership Ops + Change Logging
**Goal:** Support attach/detach/repair/fork behaviors with logged change history.

**Deliverables**
- Core operations:
  - attach file_ids → version_id (unowned constraint optional for manual ops; detection enforces it)
  - detach file_ids (set `version_id=NULL`)
  - repair in place (replace missing file with a new file; warn on checksum mismatch)
  - fork new version (next sort_key; attach replacement; preserve old)
- `version_change_log` writes:
  - one row per action
  - JSON payload includes added/removed/replaced file ids and checksum notes when available

**Definition of Done**
- Operations produce clear, single-line user-facing log entries.
- Errors are non-destructive and leave DB consistent.

---

### 8.3 — Detection Rules Loader + Detection Engine (Preview)
**Goal:** Implement the deterministic rules engine that can propose asset groupings.

**Deliverables**
- Load order:
  1) user config `rules/detection_rules.json`
  2) fallback bundled default rules
- v0 matching:
  - `image_sequence`: safe separators + frame token, any padding length ≥2
  - `texture_set`: channel tokens; qualifies at **2+ files**
  - `generic`: fallback
  - exclude `.tx`, `.rat` always
- Detection output as proposal objects (no DB writes):
  - type, key, suggested_name, file_ids, reason
  - summary counts: total considered, skipped owned, skipped excluded

**Definition of Done**
- Running detection produces proposals deterministically for a chosen storage root.
- No DB modifications occur in this sub-stage.

---

### 8.4 — Modal Proposals Dialog + Apply
**Goal:** Present proposals safely and apply them atomically when confirmed.

**Deliverables**
- Scan tab action: **Detect Assets…** (on selected storage root)
- Modal dialog:
  - proposals list + detail pane
  - editable name
  - type override dropdown
  - file checklist (remove files)
  - auto-demote: `texture_set` → `generic` if edited below 2 files
  - shows a summary count of skipped owned files (no listing)
- Apply behavior (Confirm):
  - create assets as needed
  - create v01 versions
  - attach selected files (enforce unowned)
  - write change-log row per created/assigned batch
  - main log summary: created assets, attached files, skipped owned

**Definition of Done**
- Cancel performs no writes.
- Confirm performs all writes consistently; partial failures roll back the transaction.
- EventHub refreshes relevant views.

---

### 8.5 — Asset Library View v0 (Files | Assets toggle)
**Goal:** Add asset-level browsing without removing file-level repair capability.

**Deliverables**
- Library tab toggle: **Files | Assets**
- Asset list model:
  - shows asset name, type, latest version label, counts (versions/files), basic health summary
- Detail pane for selected asset:
  - versions list (sorted by sort_key)
  - files for selected version
  - jump-to-files action (optional but valuable)

**Definition of Done**
- File Library remains unchanged and available.
- Asset Library responds to EventHub refresh and uses MainWindow log for actions.

---

### 8.6 — UI Cleanup
**Goal:** Bug fixes and UI improvements to implemented features.

**Deliverables**
- 8.6.1 Assets view: selection reliability + search/filter + hidden/integrity handling + auto-select + persist per-mode + health derived from missing_count
- 8.6.2 Context menus: assets list + files list in assets view
- 8.6.3 Detect dialog: multi-select proposals + keyboard shortcuts (Space toggle, Ctrl+A) + disable Apply when no-op

**Definition of Done**
- Bug fix and feature additions from stage 8.1-8.5 human testing analysis addressed.

---

### 8.C — Settings + Docs Wrap
**Goal:** Transparency and documentation.

**Deliverables**
- Settings tab path list includes:
  - `rules/detection_rules.json`
- DesignSummary updated to reflect Stage 8 design and plan reference.
- DevLog entries added as sub-stages land.

---

## Patch Strategy

- Default: one patch per sub-stage (8.1, 8.2, …) for stability and review.
- Tests should pass on each patch boundary.
- If a sub-stage touches a wide surface area, split into “backend” then “UI” patches.

---

## Testing Strategy

- Keep existing Stage 7 tests passing throughout.
- Add new tests incrementally alongside the sub-stage that introduces the behavior.
- Focus initial tests on:
  - schema migration idempotency
  - version sort_key/label behavior
  - detection rule matching (pure functions)
  - apply transaction correctness (unowned constraint, rollback)

---

## Open Items (tracked for Stage 9)

- User-editable rules UI and validation
- Sidecar JSON authoring/reading for asset/version metadata
- Project roots with enforced conventions (and any no-write implications)
- Advanced heuristics (sequence split, gap analysis, channel completeness scoring)
