# AssetHub — Stage 8.0 Docstrings + Tests + Logging Coverage Audit (Stage 8 Readiness) v0.1 Plan

## Purpose of Stage 8.0
Stage 8 introduces asset-level browsing and operations on top of the Stage 7 file-level UI. Stage 8.0 is a stability-first audit pass to ensure the repo is ready to evolve without:
- stale or misleading docstrings
- brittle or deprecated tests
- unclear schema/migration behavior
- action outcomes that are hard to observe or debug

Stage 8.0 is intentionally **low-refactor**: we fix what is obviously wrong, standardize what is inconsistent, and record what must change for Stage 8.

---

## Scope Summary
### Deliverables (Stage 8.0)
1) Docstring standard + repo-wide audit and updates
2) Test suite audit (remove/repair deprecated tests; assess Stage 8 compatibility)
3) Migration readiness check (schema/migration behavior is explicit, idempotent, and tested)
4) Asset-level readiness audit (confirm Stage 7 patterns extend cleanly to Stage 8)
5) Logging coverage audit (ensure every user-facing action logs a single-line outcome)

### Explicit non-goals (deferred)
- Large-scale renaming, file moves, or architecture rewrites
- UI polish unrelated to Stage 8 readiness
- Performance optimization (unless an audit reveals an immediate correctness risk)
- Introducing new Stage 8 asset features (assets begin in Stage 8.1+)

---

## Stage 8.0 Deliverables

### 1) Docstring standard + audit
#### Goal
Make docstrings consistent, accurate, and useful as “truth” during Stage 8 refactors.

#### Standard (v0.1)
Apply a consistent style across modules/classes/functions:
- One-line summary sentence first.
- Follow with a brief description only when it adds clarity.
- For public functions:
  - Args / Returns / Raises (when applicable)
- Prefer precise terms:
  - "file record" (DB row) vs "file on disk"
  - "asset" reserved for Stage 8 concepts
- Avoid implementation commentary that will drift quickly.

#### Audit checklist
- Remove inaccurate claims (e.g., “deletes from disk” when it is DB-only).
- Update references to schema versions (now at least v2).
- Ensure EventHub usage is described consistently where relevant.
- Ensure logging expectations are described where relevant (summary logging for actions).
- Mark truly private helpers with minimal docstrings (or none), keep public APIs documented.

#### Acceptance criteria
- No obvious docstring contradictions with current behavior.
- Public/core interfaces (AppContext, StorageManager, Scanner/Health, DB helpers, UI actions) have standardized docstrings.
- No docstring introduces Stage 8 concepts prematurely (unless explicitly labeled “Stage 8 forthcoming”).

---

### 2) Test suite audit + Stage 8 compatibility notes
#### Goal
Ensure tests are current, meaningful, and structured so Stage 8 changes can be made safely.

#### Audit checklist
- Identify and remove/repair tests that are:
  - redundant (testing the same thing multiple ways)
  - brittle (dependent on UI widgets, timing, or local machine paths)
  - deprecated (testing behavior that no longer exists)
- Ensure tests remain **Qt-free** (no QApplication/QWidget instantiation).
- Ensure core invariants are covered:
  - DB schema/migration invariants
  - storage root rules (unmanaged invariants)
  - cascade delete rules (DB-only)
  - EventHub reason/payload patterns where unit-testable

#### Stage 8 readiness evaluation
Produce short notes (in a Stage 8.0 summary file) on:
- which tests will likely need refactoring when the Library becomes asset-level
- where test fixtures should be expanded (e.g., sample DB with asset-ish groupings)

#### Acceptance criteria
- Pytests remain green after cleanup.
- Any removed tests are justified in the Stage 8.0 summary notes.
- Clear list of “tests to revise when asset-level views land.”

---

### 3) Migration readiness check (DB + sidecars)
#### Goal
Confirm schema/migration logic is explicit and safe, since Stage 8 will almost certainly add new tables/relationships.

#### Audit checklist
- Confirm schema version handling is:
  - monotonic (never decreases)
  - idempotent (safe to run on already-migrated DB)
  - tested (at least one migration test)
- Identify where migrations live and document the pattern for adding v3+.
- Sidecars:
  - confirm current “sidecar is authoritative for project metadata” principle remains intact
  - record what Stage 8 might need from sidecars (do not implement yet)

#### Acceptance criteria
- At least one pytest covers an “older schema -> migrate -> verify columns/tables” path.
- A short “How to add migrations” note exists (either in docstrings or Stage 8.0 summary).

---

### 4) Asset-level readiness audit (Stage 7 patterns)
#### Goal
Verify Stage 7’s action plumbing, selection model, and signals can extend to assets cleanly.

#### Audit checklist
- Action plumbing:
  - Inventory existing actions and identify which are file-only vs will become asset-aware.
- Selection model:
  - Identify assumptions that selection == file_id.
  - Note where “selection abstraction” might be needed for assets.
- EventHub:
  - Inventory reason strings and payload shapes.
  - Ensure they’re consistent and extensible (e.g., storage_removed, storage_renamed).

#### Minimal refactor rule
Only refactor if:
- it removes a clear Stage 8 blocker, or
- it eliminates a near-certain drift point (e.g., hardcoded file-only naming in shared action helpers)

#### Acceptance criteria
- Stage 8.0 summary includes a clear list of “Stage 8 expects these surfaces to change” with file pointers.
- No speculative redesign work lands in code.

---

### 5) Logging coverage audit
#### Goal
Ensure every user-facing action produces a single-line, human-readable outcome in the global log.

#### Audit checklist
- Inventory all UI actions across tabs:
  - Scan
  - Library (context menu actions)
  - Detail pane (if any action buttons exist)
  - Settings (read-only currently, so likely none)
- For each action, confirm it logs:
  - INFO for routine success
  - WARN for successful but destructive/high-impact outcomes
  - ERROR for failures/exception paths
- Ensure log messages consistently distinguish:
  - DB deletes vs disk deletes
  - record counts where available

#### Acceptance criteria
- A checklist table exists in the Stage 8.0 summary showing action -> log coverage -> notes.
- Missing log coverage is addressed with minimal code changes.

---

## Patch / Execution Strategy (stability-first)

### Patch 8.0.1 — Docstring standard + audit
Scope:
- Repo-wide docstring edits (no functional changes intended)
- Add/update small doc notes where needed

Verification:
- Pytests remain green
- Manual smoke: launch app; perform one action per tab; confirm no regressions

### Patch 8.0.2 — Test suite cleanup + readiness notes
Scope:
- Remove/repair deprecated tests
- Improve fixtures only when clearly helpful
- Record Stage 8 “tests likely to change” notes

Verification:
- Pytests green

### Patch 8.0.3 — Migration readiness
Scope:
- Confirm migration pattern
- Add/adjust at least one migration test
- Minimal code edits if migration behavior is unclear or fragile

Verification:
- Pytests green

### Patch 8.0.4 — Logging coverage audit and fixes
Scope:
- Inventory actions
- Add missing summary log lines
- Adjust levels (INFO/WARN/ERROR) to match conventions

Verification:
- Manual smoke: trigger every action at least once; confirm log output
- Pytests green

---

## Testing Plan
### Automated (pytest)
- No Qt widget instantiation in tests.
- Add/keep migration test coverage.
- Keep existing unit tests stable; expand only where necessary.

### Manual smoke
- Launch app.
- Trigger representative actions:
  - Scan: add root, scan, health, cleanup missing, rename, cascade remove
  - Library: open/reveal/copy, targeted health, remove missing selection
- Confirm each action produces a readable single-line log entry.

---

## Stage 8.0 Artifacts
- `AssetHub_Stage8_0_DocAndTestAuditOutline_v0.1.md` (this plan)
- `AssetHub_Stage8_0_AuditSummary_v0.1.md` (created during execution)
  - Docstring changes summary
  - Test cleanup summary
  - Migration readiness notes
  - Asset-level readiness notes
  - Logging coverage checklist

---

## Definition of Done
- Docstrings standardized and corrected across core modules.
- Tests audited; deprecated/brittle tests removed or repaired; Stage 8 compatibility notes recorded.
- Migration behavior is explicit, idempotent, and has at least one pytest covering an upgrade path.
- Asset-level readiness audit is recorded (clear “what will change in Stage 8” notes).
- Logging coverage checklist completed; missing action logs added with minimal code edits.
- Pytests green; manual smoke passes.
