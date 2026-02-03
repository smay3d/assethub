# AssetHub — Stage 9.2 Plan (v0.1)
*(Versioning Realism v1 — filename parsing + manual overrides + discard + mismatch resolution)*

## Goal

Make AssetHub’s versioning match real CG workflows:

- Detect version numbers from filenames when present (e.g. v003, v6)
- Allow manual version overrides (number + optional label)
- Keep history, but allow versions to be **discarded**:
  - discarded versions remain in DB
  - discarded versions are treated as intentionally untracked on disk (no missing noise)
- Handle edge case: **multi-file assets with mismatched versions** (e.g. albedo v03, normal v05)
  - detect conflict
  - require user resolution (split vs force)

After 9.2, versioning is “pipeline-believable.”

---

## Scope

### In scope
- Version parsing from file names during asset detection / apply
- Manual editing:
  - edit version number (int) and optional version label (str)
  - resolve mismatched-version cases via UI prompt
- Discard / restore versions in UI + DB, and update health-check behavior
- Minimal schema change(s) to support discard and (optionally) version labels

### Out of scope
- Per-channel versioning rules (texture channel-specific logic)
- Sophisticated ignore rules / version families / semantic “final”
- Automatic “bump version” tooling
- Project logic (Stage 9.4) and checksums (Stage 9.3)

---

## Decisions Locked (from Stage 9 summary)
- Always keep history.
- “Discarded” versions should not participate in disk health checks
  (treated as existing in DB but intentionally not tracked on disk).

---

## Deliverables

### A) Schema v5: Discard + Label (minimal)
Bump:
- `LATEST_SCHEMA_VERSION = 5`

Add migration:
- `_migrate_to_v5()` registered in `_MIGRATIONS`

Schema changes:
- `version` table:
  - Add `is_discarded INTEGER NOT NULL DEFAULT 0`
  - Add `label TEXT NOT NULL DEFAULT ''` *(optional but recommended; enables “final”, “clientDelivery”, etc.)*

Notes:
- Keep changes additive.
- Migration idempotent.

---

### B) Core: Version parsing utilities
Add:
- `src/assethub/core/detection/version_parse.py`

Functions:
- `parse_version_num(name: str) -> int | None`
  - detects common patterns:
    - `v001`, `v1`, `.v12`, `_v12`, `-v12`, `version12` (conservative)
  - returns numeric version (e.g. 6), not padded string
- `format_version_num(n: int, pad: int = 2) -> str`
  - display helper only (e.g. `v06`), used in UI labels

Constraints:
- Parsing should be deterministic and unit-tested.
- If multiple matches occur, choose the last match in the basename (usually closest to extension).

---

### C) Detection/apply: Use parsed versions + detect mismatch conflicts

#### C1) When detecting file membership into versions
Update detection logic (where file→version grouping is created):

- If `parse_version_num(filename)` returns a number:
  - assign/create that version number for that asset
- If no version detected:
  - treat as version “unversioned” (either `None` or a “v01 default” per current design)
  - (Stage 9.2 approach: keep current behavior for no-version files; don’t change semantics unless necessary)

#### C2) Mismatch conflict detection
A “version conflict” exists when:
- Within the same detected asset group, two+ distinct version numbers are present across files.

Stage 9.2 behavior:
- detection step flags conflicts and records:
  - `asset_key` (or temp id)
  - set of versions found (e.g. {3, 5})
  - file lists per version

Apply path must not silently guess.
- The UI should require a resolution choice before apply finalizes.

---

### D) UI: Resolve Version Conflicts (small dialog)
Add dialog:
- `src/assethub/ui/dialogs/version_conflict_dialog.py`

Dialog shows:
- Asset name / key (as detected)
- Versions detected (e.g. v03, v05)
- For each version: list of files (scrollable, short)
- Resolution actions:
  1) **Split** into separate versions (default / recommended)
     - create version rows for each distinct number
     - assign files accordingly
  2) **Force all into one version**
     - user selects target version (radio buttons or dropdown)
     - all files assigned to that version

On accept:
- returns a structured resolution object consumed by apply stage.

Integration point:
- invoked during “Detect Assets” review/apply flow, before committing DB writes
  - ideally as a pre-flight step if conflicts exist
  - avoid per-asset modal spam: allow resolving all conflicts in one pass if possible

---

### E) UI: Version discard + label editing in Asset Detail
Update Asset Detail / Version list UI:
- Add context menu on version entries:
  - “Set label…”
  - “Edit version number…”
  - “Mark discarded”
  - “Restore”
- Add a toggle: “Show discarded versions” (default off)
- Visual indicator for discarded versions when shown (subtle; e.g. gray text + “[discarded]”)

Behavior:
- Discarding does **not** delete DB records.
- Discarding should remove “missing noise” for files under that version in health checks.

---

### F) Health / Missing logic: ignore discarded versions
Update health-check queries/logic so that:
- when evaluating missing files, exclude files that belong to versions where `is_discarded = 1`

Notes:
- This is the critical “power-user correctness” requirement.
- Ensure this affects:
  - targeted checks
  - scan health summaries
  - missing lists
- But DB should still retain those file rows for history/audit.

---

## Files to Add / Modify

### Modify (expected)
- `src/assethub/core/db/schema.py` (v5 migration)
- `src/assethub/core/db/health.py` *(or wherever missing detection lives)* to ignore discarded versions
- `src/assethub/core/db/assets_versions.py` *(or relevant ops)* for label/discard updates
- Detection modules:
  - the module that groups files → assets → versions (Stage 8 detection pipeline)
- UI:
  - version list widget in asset detail
  - detect assets dialog / apply path to inject conflict resolution

### Add
- `src/assethub/core/detection/version_parse.py`
- `src/assethub/ui/dialogs/version_conflict_dialog.py`

Optional (only if needed for cleanliness)
- `src/assethub/core/db/version_ops.py` (small helper for label/discard edits)

---

## Testing Plan

### Unit tests (Qt-free)
Add tests:
- `tests/test_version_parse.py`
  - parses `v01`, `v1`, `_v003`, `.v12`, `version7`
  - does not false-positive on random numbers where possible

Update/add DB tests:
- schema v4 → v5 migration
- version discard flag persists and defaults to 0
- label defaults to ''

Health behavior tests:
- create a version with files, mark discarded
- confirm missing detection excludes those file records

### UI import tests
- Ensure new dialog imports don’t break `tests/test_ui_imports.py`

### Manual test
1) Ingest/detect an asset with versions in filenames:
   - confirm versions are created correctly (v6 stays v6)
2) Create an intentional mismatch:
   - two files same asset, different versions in names
   - detect assets → conflict dialog appears
   - test Split vs Force
3) Mark an older version discarded:
   - confirm it disappears by default
   - confirm health checks don’t report those files missing

---

## Definition of Done

- App migrates DB to schema v5 cleanly.
- Version numbers are parsed from filenames and respected during detection/apply.
- Mismatched-version assets require a user decision (Split/Force) and apply correctly.
- Versions support discard/restore and optional label editing in the UI.
- Health checks ignore files under discarded versions.
- Full pytest suite passes on Windows.
