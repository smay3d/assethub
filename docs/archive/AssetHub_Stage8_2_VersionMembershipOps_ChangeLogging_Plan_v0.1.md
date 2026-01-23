# AssetHub — Stage 8.2 Plan (v0.1)

## Goal

Add **version membership operations** (attach / detach / repair / fork) with **accountable change logging** via `version_change_log`.

In ship terms: after 8.2, the backend can safely modify `file.version_id` in bulk and record a per-action history row that later UI actions (8.4+) can call into.

---

## Scope

### In scope
- DB-layer ops for modifying version membership
- `version_change_log` row creation (one row per operation)
- Single-line, user-facing summaries returned to callers (caller logs to MainWindow log)
- Minimal unit tests for ops + log writes

### Out of scope
- UI actions / dialogs / context menus (Stage 8.4+)
- Detection engine integration (Stage 8.3)
- Checksums (not present in schema v3; we log size/availability notes instead)

---

## Deliverables

### A) DB helpers: version membership ops

Create a new module:

- `src/assethub/core/db/version_membership.py`

Provide these operations (all **transactional** and **non-destructive** on error):

1) **Attach**
   - `attach_files_to_version(conn, version_id, file_ids, enforce_unowned=False) -> AttachResult`
   - Behavior:
     - If `enforce_unowned=True`, only attach files where `file.version_id IS NULL`.
     - Always skip files already attached to the target version.
     - Update `file.updated_at=CURRENT_TIMESTAMP` for modified rows.
     - Update `version.updated_at=CURRENT_TIMESTAMP` for the target version.
   - Result counts include: `attached`, `skipped_owned`, `skipped_already_attached`, `missing_file_rows`.

2) **Detach**
   - `detach_files(conn, file_ids, only_from_version_id=None) -> DetachResult`
   - Behavior:
     - Sets `file.version_id=NULL` (optionally only if it matches `only_from_version_id`).
     - Updates `file.updated_at` for modified rows.
     - Updates `version.updated_at` for any impacted version ids (if known).
   - Result counts include: `detached`, `skipped_not_attached`, `missing_file_rows`.

3) **Repair in place**
   - `repair_version_membership(conn, version_id, old_file_id, new_file_id, enforce_unowned=False) -> RepairResult`
   - Behavior:
     - Detach `old_file_id` from `version_id` (expected MISSING but not required).
     - Attach `new_file_id` to `version_id` (optionally enforce unowned).
     - Records a note if:
       - old record wasn’t MISSING, or
       - `size_bytes` differs when both known, or
       - size data missing.
     - Updates `file.updated_at` + `version.updated_at`.

4) **Fork new version**
   - `fork_version(conn, source_version_id, *, label=None, include_missing=False, replacement_file_ids=None, enforce_unowned=False) -> ForkResult`
   - Behavior:
     - Creates a new version on the same asset with `sort_key = max(sort_key)+1` and default label `vNN` when label is None.
     - Copies membership from the source version:
       - default: include only files where `integrity_state != 'MISSING'`
       - if `include_missing=True`, include missing too.
     - Attaches any `replacement_file_ids` to the new version.
     - Leaves the source version unchanged (“preserve old”).
     - Updates `version.updated_at` on the new version (and optionally on source if we decide to mark activity later—**not in 8.2**).

### B) Change logging

Add helper:

- `write_version_change_log(conn, version_id, action_type, summary, payload: dict) -> int`

Rules:
- One log row per operation (per target version).
- `payload_json` is compact JSON containing:
  - `added_file_ids`, `removed_file_ids`, `replaced` (list of `{old,new,note}`),
  - optional `notes` array,
  - `skipped_owned`, `skipped_already_attached` where relevant,
  - `source_version_id` for forks.
- No schema changes (table exists from 8.1).

### C) Caller-facing summaries (for MainWindow log)

Each op returns a short `summary` string, e.g.:
- `Attached 12 files → version 7 (skipped 3 owned)`
- `Detached 4 files (2 were not attached)`
- `Repaired version 7: replaced file 10 → 22 (size mismatch old=123 new=456)`
- `Forked version 7 → new version 8 (copied 15, added 1 replacement)`

(Logging happens at action/service layer; DB layer returns summaries.)

### D) Tests

Add a focused test module:
- `tests/test_db_version_membership_ops.py`

Covers:
- attach honors `enforce_unowned`
- detach clears membership + updates counts
- repair swaps membership + writes a log row with a `replaced` payload
- fork creates new version with incremented `sort_key`, copies membership, and writes fork log row

---

## Implementation notes

- All ops must use a single transaction (`with conn:`) so partial updates roll back.
- Validate inputs early (version exists, file ids list non-empty, etc.).
- Use safe bulk updates with `WHERE id IN (...)` and computed placeholders.
- Keep SQL portable and simple; prefer correctness over cleverness.

---

## Definition of Done

- `python -m pytest` passes on Windows.
- Running the app shows schema v3 and no regressions in Stage 7 flows.
- All four ops work in isolation against a fresh DB and record `version_change_log` rows with valid JSON.

---

## Expected file changes (high level)

- `src/assethub/core/db/version_membership.py` (new)
- `src/assethub/core/db/__init__.py` (export if needed)
- `tests/test_db_version_membership_ops.py` (new)
