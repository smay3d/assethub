# AssetHub — Stage 8.3 Plan (v0.1)

## Goal

Implement the **deterministic detection rules loader** and **preview detection engine** that can propose asset groupings for a chosen storage root.

**Important:** Stage 8.3 performs **NO DB writes**. It produces proposal objects only.

---

## Scope

### In scope
- Rules loading (user-config override → bundled defaults)
- Deterministic detection engine that:
  - scans a **single storage root**
  - considers only **unowned** files (`file.version_id IS NULL`)
  - excludes `.tx` and `.rat` always
  - produces proposal objects:
    - `type`, `key`, `suggested_name`, `file_ids`, `reason`
  - includes summary counts:
    - `total_considered`, `skipped_owned`, `skipped_excluded`

### Out of scope
- UI actions / modal dialog / apply (Stage 8.4)
- Any DB mutations (asset/version creation, attaching files)
- Checksums / content hashing

---

## Deliverables

### A) Config: rules directory path

Add `rules_root` to `AppConfig` (default empty string), and include it in:
- defaults (`build_default_config`)
- Settings snapshot paths (so it appears on the Settings tab)

**Default path** (when `rules_root` is empty):
- `Path(data_root) / "rules"`

This keeps all user-editable rules under the existing data root.

---

### B) Rules loader

New module:
- `src/assethub/core/detection/rules_loader.py`

New dataclass:
- `DetectionRuleset`
  - `excluded_exts: set[str]` (always includes `{"tx","rat"}`)
  - `image_sequence: {separators: list[str], min_digits: int}`
  - `texture_set: {separators: list[str], channel_tokens: list[str], min_files: int}`
  - `generic: {group_by_stem: bool}` (v0: True)

Load order:
1) user config file: `{rules_root}/detection_rules.json`
2) bundled default rules (package resource)

Validation:
- If user file is missing or invalid JSON → fall back to defaults.
- If user file loads but is missing keys → fill from defaults.

Bundled defaults:
- Add package dir `src/assethub/resources/`
  - `__init__.py`
  - `detection_rules_default.json`

---

### C) Detection engine (preview)

New module:
- `src/assethub/core/detection/engine.py`

Dataclasses:
- `DetectionProposal`:
  - `type: str`
  - `key: str`
  - `suggested_name: str`
  - `file_ids: list[int]`
  - `reason: str`
- `DetectionSummary`:
  - `total_considered: int`
  - `skipped_owned: int`
  - `skipped_excluded: int`
- `DetectionResult`:
  - `proposals: list[DetectionProposal]`
  - `summary: DetectionSummary`

Entry point:
- `detect_proposals_for_storage(conn, storage_id: int, rules: DetectionRuleset) -> DetectionResult`

Determinism rules:
- Input scan ordered by `file.id ASC`
- Group keys normalized with forward slashes
- `file_ids` sorted ascending
- Proposals sorted by `(type, key)`

Matching behavior (v0):

1) **image_sequence**
- Match filenames with a trailing frame token:
  - safe separators + digits with padding length ≥ `min_digits`
  - examples:
    - `foo.0001.exr`
    - `foo_0001.exr`
- Group key:
  - `"{dir}/{base}{ext}"` (dir may be empty)
- `suggested_name = base`
- `reason` includes the detected separator and digits length.

2) **texture_set**
- Match channel tokens separated by safe separators:
  - example: `rock_albedo.png`, `rock-normal.exr`
- Group key:
  - `"{dir}/{base}"` where base is filename stem minus the channel token
- Only emit a `texture_set` proposal if the group contains **>= 2** files (rule `min_files`)
- `suggested_name = base`

3) **generic**
- Fallback grouping for remaining files:
  - group by `"{dir}/{stem}"` (stem without extension)
- `suggested_name = stem`

Always-excluded extensions:
- `.tx`, `.rat` (case-insensitive)

Owned skip:
- any row where `version_id IS NOT NULL` is counted as `skipped_owned` and never proposed.

---

### D) Tests

New test module:
- `tests/test_detection_engine_preview.py`

Covers:
- loads defaults when user config file missing
- respects excluded extensions and owned-file skipping
- image_sequence groups correctly and deterministically
- texture_set emits only when >=2 files
- fallback generic grouping behavior
- deterministic ordering of proposals and file_ids

---

## Definition of Done

- `python -m pytest` passes on Windows.
- Running detection against a test DB produces deterministic proposals.
- Stage 8.3 performs no DB writes (verified in tests by checking asset/version tables remain empty).

---

## Expected file changes (high level)

New:
- `src/assethub/core/detection/__init__.py`
- `src/assethub/core/detection/rules_loader.py`
- `src/assethub/core/detection/engine.py`
- `src/assethub/resources/__init__.py`
- `src/assethub/resources/detection_rules_default.json`
- `tests/test_detection_engine_preview.py`

Modified:
- `src/assethub/context.py` (AppConfig adds `rules_root`)
- `src/assethub/config/defaults.py` (default rules_root path)
- `src/assethub/ui/views/settings_snapshot.py` (expose rules_root path)

