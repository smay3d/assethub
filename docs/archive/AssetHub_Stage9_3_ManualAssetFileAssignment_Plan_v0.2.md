# AssetHub — Stage 9.3 Manual Asset–File Assignment (v0.2)
*(Authoritative Binding v1 — backend authority + UI workflow split)*

## Purpose

Stage 9.3 introduces **manual asset–file assignment** as the authoritative layer on top of AssetHub’s detection system.

This stage is executed as **two implementation patches** to reduce risk and ensure correctness before UI is layered on top:

- **9.3.1 — Backend authority layer**
- **9.3.2 — UI + workflow integration**

Detection remains heuristic and evolvable.  
Manual assignment is explicit, durable, and never changes without user intent.

---

## Design Doctrine (Locked)

- Detection answers: **“What signals does this file emit?”**
- Manual assignment answers: **“What does the user say this file is?”**
- Manual signals override all automatic signals.
- Detection may change its mind forever.
- Manual assignments must never change unless the user changes them.
- A file manually assigned to an asset **automatically carries forward** into all future non-discarded versions of that asset.

---

## Stage 9.3 Overview

### Stage 9.3.1 — Manual Binding Backend (Authority Layer)
**Focus:** Correctness, invariants, and detection integration  
**User-facing UI:** None (intentionally)

### Stage 9.3.2 — Assignment UI & Workflow
**Focus:** Usability, speed, and daily-driver workflows  
**Depends on:** 9.3.1 complete and stable

---

# Stage 9.3.1 — Manual Asset–File Binding (Backend)

## Goal

Establish **manual file → asset binding** as an authoritative, durable signal that:
- overrides detection
- persists across asset version ups
- integrates seamlessly with snapshot carry-forward

This patch locks the **rules of truth** before any UI is introduced.

---

## Scope (9.3.1)

### In Scope
- Manual binding data model
- Schema migration
- Core binding APIs
- Detection proposal + apply changes
- Version carry-forward integration
- Logging
- Unit and integration tests

### Out of Scope
- Assignment dialogs
- Context menus
- Files view UX changes
- Any new UI

---

## Database Changes

### Schema v7 — Manual Binding Table

Add table:

**`file_binding`**
- `file_id INTEGER PRIMARY KEY REFERENCES file(id) ON DELETE CASCADE`
- `asset_id INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE`
- `created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`

Constraints:
- One file may be bound to **one asset only**
- Binding is **asset-level**, not version-level

Migration:
- Bump schema version to v7
- Create table
- No backfill required

---

## Core Semantics

### Binding Meaning
- A bound file:
  - belongs to an asset by user authority
  - is excluded from detection reassignment
  - is auto-included in all future asset versions

### Detection Integration

#### Proposal Generation
- Files with a `file_binding` entry are treated as **locked**
- Locked files are excluded from:
  - asset grouping
  - version conflict detection
  - reassignment proposals

#### Apply Phase
- Detection must never:
  - detach a bound file
  - reassign a bound file to another asset
- Any proposal touching bound files is skipped with explicit logging

---

## Version Carry-Forward Integration

When creating a new asset version:
1. Clone membership from latest non-discarded version
2. Ensure **all bound files for the asset** are included
3. Apply role-aware overrides from detection
4. Persist snapshot via `version_file`

Bound files are never dropped unless explicitly unbound by the user.

---

## Logging (9.3.1)

Log manual binding operations distinctly from detection:
- operation: `bind_file`, `unbind_file`
- file_id(s)
- asset_id
- timestamp

Detection logs must include:
- `skipped_locked_files=N`

---

## Testing Plan (9.3.1)

### Unit / Integration Tests
- Create and remove bindings
- Bound files excluded from detection proposals
- Bound files survive asset version ups
- Detection attempts to reassign bound files are skipped
- Snapshot correctness with bound files present

---

## Definition of Done (9.3.1)

- Manual binding exists in DB and APIs
- Detection fully respects manual bindings
- Bound files auto-carry-forward across versions
- No UI regressions
- Full pytest suite passes on Windows

---

# Stage 9.3.2 — Assignment UI & Workflow

## Goal

Expose manual asset–file binding to the user through a **fast, clean, frequently-used UI**, enabling AssetHub to function as a true organizational tool.

This patch assumes all backend rules from 9.3.1 are already locked.

---

## Scope (9.3.2)

### In Scope
- Shared “Assign files to asset/version…” dialog
- Files view multi-select assignment
- Assets view single-target assignment
- Files view “unassigned inbox” filtering
- Visual indicators for bound files
- UI wiring to backend binding APIs

### Out of Scope
- Version snapshot editor UI
- Checksum reconcile
- Project logic

---

## UI Entry Points

### Files View (multi-select)
Context menu:
- **Assign selected to asset/version…**

Primary workflow for:
- inbox cleanup
- bulk organization
- unowned files

---

### Assets View (single asset target)
Context menu:
- **Assign files to this asset…**

Used when the asset context is already known.

---

## Assignment Dialog (Shared)

**Title:** Assign files to asset

### Sections
1. **Target Asset**
   - searchable asset list
   - required

2. **Target Version**
   - default: latest non-discarded
   - informational only (binding is asset-level)

3. **Confirmation**
   - warn on rebinding if file is already bound
   - clear statement that assignment carries forward

Footer:
- Apply / Cancel
- Summary text:
  “Assigning N files to Asset ‘X’ (will carry forward to future versions)”

---

## Files View Inbox Behavior

- Add filter: **Unassigned files only**
- Bound files are considered resolved
- Encourages a clean “everything belongs to an asset” workflow

---

## Visual Indicators

- Bound files display a subtle indicator (icon or column)
- Tooltip:
  “Manually assigned to Asset ‘X’”

---

## Testing Plan (9.3.2)

### UI Tests
- Dialog opens from both entry points
- Assignments persist
- Rebind confirmation works
- Unassigned filter behaves correctly

### Manual Tests
- Assign file → rerun detection → no reassignment
- Assign file → version up asset → file carries forward
- Bulk assign from Files view

---

## Definition of Done (9.3.2)

- Users can manually assign files to assets via UI
- Manual bindings persist and carry forward
- Files view supports inbox-style workflows
- Detection never overrides user intent
- No regressions in version behavior
- Full pytest suite passes on Windows

---

## Notes

Stage 9.3 intentionally precedes checksum reconcile and version snapshot editing.  
Manual authority must exist before automated repair systems are introduced.
