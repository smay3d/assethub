# AssetHub — Stage 9.3.1 Manual Asset–File Assignment (v0.1)
*(Authoritative Binding v1 — user intent over detection)*

## Purpose

Stage 9.3.1 introduces **manual asset–file assignment** as an authoritative layer on top of AssetHub’s detection system.

This sub-stage completes the core asset-version system by giving the user **absolute control** over asset membership, while preserving all benefits of automatic detection and version carry-forward.

Detection remains heuristic and evolvable.  
Manual assignment is explicit, durable, and never changes without user intent.

---

## Design Doctrine (Locked)

This sub-stage formalizes the following rules:

- Detection answers: **“What signals does this file emit?”**
- Manual assignment answers: **“What does the user say this file is?”**
- Manual signals override all automatic signals.
- Detection may change its mind forever.
- Manual assignments must never change unless the user changes them.
- A file manually assigned to an asset **automatically carries forward** into all future non-discarded versions of that asset.

---

## Scope

### In Scope
- Manual file → asset binding (authoritative)
- Automatic carry-forward of bound files across asset versions
- Detection respecting manual bindings (skip / exclude)
- UI for assigning files to assets and versions
- Files view workflow improvements to support assignment

### Out of Scope
- Version snapshot editor UI
- Checksum reconcile
- Project-level logic
- File-level tagging
- Any disk write or rename operations

---

## Core Concepts

### Manual Binding
A **manual binding** represents explicit user intent that a file belongs to an asset.

Bindings are:
- explicit
- durable
- authoritative
- version-agnostic by default

Once bound, a file:
- is treated as “owned” by that asset
- participates in all future version snapshots automatically
- is excluded from reassignment by detection

---

## Database Changes

### Schema v7 — Manual Binding Table

Add new table:

**`file_binding`**
- `file_id INTEGER PRIMARY KEY REFERENCES file(id) ON DELETE CASCADE`
- `asset_id INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE`
- `created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`

Notes:
- One file may be bound to **at most one asset**.
- Version membership is still handled via `version_file`.
- Binding is asset-level, not version-level, in v1.

### Migration
- Bump schema version to v7
- Create `file_binding`
- No backfill required (manual bindings are user-created only)

---

## Detection System Integration

### Proposal Generation
When scanning or generating detection proposals:
- Files with an entry in `file_binding` are treated as **locked**:
  - excluded from asset grouping
  - excluded from version mismatch resolution
  - excluded from reassignment

### Apply Phase
- Detection must never:
  - detach a bound file
  - reassign a bound file to a different asset
- If a detection proposal includes a bound file:
  - proposal entry is skipped
  - log: `skipped_locked_files=N`

### Updated File Detection
If detection finds a new file that matches a role already occupied by a bound file:
- This is treated as a **normal update**:
  - new asset version is created
  - snapshot carry-forward applies
  - role is replaced in the new version
- The binding remains valid at the asset level.

---

## Version Carry-Forward Rules

When a new asset version is created:
1. Clone membership from latest non-discarded version
2. Ensure **all bound files for the asset** are included
3. Apply role-aware overrides from detection
4. Persist snapshot via `version_file`

This guarantees:
- bound files never “fall off” future versions
- user intent scales with asset evolution

---

## UI Design

### Entry Points

#### Files View (multi-select)
Context menu:
- **Assign selected to asset/version…**

Used for:
- inbox-style cleanup
- bulk organization
- assigning unowned files

#### Assets View (single asset target)
Context menu:
- **Assign files to this asset…**

Used for:
- adding files directly into a known asset

Both entry points invoke the same dialog.

---

### Assign Dialog (Shared)

**Title:** Assign files to asset

#### Sections
1. **Target Asset**
   - searchable asset list
   - required

2. **Target Version**
   - default: latest non-discarded version
   - informational only (binding is asset-level)

3. **Behavior**
   - Manual assignment is implicit and authoritative
   - If file already bound:
     - confirmation required to rebind

#### Footer
- Apply / Cancel
- Summary:  
  “Assigning N files to Asset ‘X’ (will carry forward to future versions)”

---

## Files View Workflow (Inbox Direction)

Stage 9.3.1 introduces the conceptual shift toward Files view as an **assignment inbox**:

- Add filter: **Unassigned files only**
- Bound files are considered “resolved”
- Unassigned files are surfaced for:
  - detection
  - manual assignment

This aligns with the long-term goal that *every file belongs to an asset*.

---

## Logging

All manual assignment actions must be logged:
- file_ids
- target asset_id
- timestamp
- operation type (bind / rebind / unbind)

Logs must clearly distinguish:
- manual actions
- detection actions

---

## Testing Plan

### Unit Tests (Qt-free)
- Create manual binding and verify persistence
- Bound files excluded from detection proposals
- Bound files carry forward across version creation
- Attempted reassignment via detection is skipped

### Integration Tests
- Assign files manually → run detection → confirm no changes
- Assign file → introduce updated version → asset versions up correctly

### Manual Test
1. Ingest loose files
2. Assign file to asset manually
3. Version up asset via detection
4. Confirm bound file appears in new version automatically
5. Confirm detection does not reassign bound file

---

## Definition of Done

- Users can manually assign files to assets via UI
- Manual bindings persist across version ups
- Detection respects manual bindings as authoritative
- Files view supports bulk assignment workflows
- No regressions in version snapshot behavior
- Full pytest suite passes on Windows

---

## Notes

This sub-stage intentionally precedes checksum reconcile and version snapshot editing.  
Manual authority must exist before automated repair systems are introduced.
