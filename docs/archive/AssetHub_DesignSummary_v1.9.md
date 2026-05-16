# AssetHub — Project Design Summary v1.9

This document captures the **authoritative design state** of the AssetHub project.  
It records **intentional design decisions, system doctrines, invariants, and models** that guide implementation.  

It intentionally avoids historical narration, test status, and step-by-step implementation detail.  
For execution history, see the **Development Log**.

---

## Design Doctrine (Applies to All Stages)

- **Disk is authoritative**  
  AssetHub never assumes ownership over user files. The filesystem is always the ground truth.

- **No-write policy (v0–v1)**  
  AssetHub does not rename, move, or modify user files on disk.

- **User intent outranks heuristics**  
  Automated detection is fallible. Manual user actions are authoritative and durable.

- **Explainability over magic**  
  The system must always be able to answer *why* something happened.

- **Power-user first**  
  Single-user, expert workflows are prioritized over mass-market simplicity.

---

## Stage 1 — Goals & Scope

### Purpose
AssetHub is a desktop application for browsing, organizing, and maintaining digital assets located anywhere on disk, without imposing filesystem structure.

### Audience
- Single user
- Power users (CG artists, technical artists, archivists)

### Core Capabilities (v0 Direction)
- Asset scanning and indexing
- Asset versioning
- Tagging and organization
- Library browsing with previews
- Sidecar-based metadata storage
- Multiple storage roots

### Explicit Non-Goals (v0)
- Cloud sync
- Multi-user permissions
- AI-driven tagging or inference

---

## Stage 2 — Data Model Overview

### Core Entities

- **Asset**  
  A conceptual container (e.g. *Oak Bark 001*, *Raven A*).

- **Version**  
  A labeled snapshot of an Asset’s file membership.

- **File**  
  A physical file on disk, tracked and indexed by AssetHub.

- **Tag**  
  A semantic label applied at the asset level.

- **Storage**  
  A logical root used to resolve file paths deterministically.

### Future Entities (Planned)
- Preview
- Collections
- SmartFolders

---

## Metadata & Persistence Strategy

### Hybrid Architecture (Locked)

- **SQLite database**  
  - Source of truth for indexing, relationships, and state
- **Centralized sidecar JSONs**  
  - Stored under `SIDECARS/<asset-id>/`
  - Used for portability, extensibility, and future export

### Key Principles
- Sidecars do **not** live beside user files
- Assets and files may live **anywhere on disk**
- Metadata must be reconstructible from disk via rescans

---

## Stage 2b — Storage Roots & Resolution

### Storage Roots

- Users explicitly register one or more storage roots
- Scans only occur within registered roots
- Path resolution uses deterministic longest-prefix matching

### Unmanaged Storage (Invariant)

- Files outside all registered roots are assigned to a special **Unmanaged** storage
- Unmanaged always exists
- Unmanaged cannot be deleted or renamed

---

## Stage 3 — Folder & Naming Rules

### Internal AssetHub Folder Layout

AssetHub/
DB/
SIDECARS/
CACHE/previews/
LOGS/


### User File Policy

- User files remain exactly where the user keeps them
- AssetHub does not enforce folder structure
- Naming conventions are guidelines only

---

## Stage 4 — UX Structure (Conceptual)

### Primary Tabs

1. **Library** — Browse files and assets
2. **Detail** — Inspect and edit asset data
3. **Scan** — Register roots, ingest, diagnose
4. **Deploy** (future)
5. **Settings** — Transparency and configuration

### Library Model

- Master–detail layout
- Read-only browsing by default
- Visual health indicators (color coded)
- Selection-driven actions

---

## Stage 5 — Technology Decisions

### Stack (Locked)

- **Language:** Python
- **UI:** PySide6 / Qt
- **Database:** SQLite
- **Sidecars:** JSON
- **Threading:** Qt thread pool

### Architectural Pattern

- Central **AppContext** as composition root
- UI layers access state exclusively through context
- Long-lived services owned and lifecycle-managed centrally

---

## Database Model (v0 Baseline)

### Core Tables

1. storage  
2. asset  
3. version  
4. file  
5. tag  
6. asset_tag  

### Core Invariants

- Every file belongs to exactly one storage
- Files outside roots belong to Unmanaged
- Integrity state is tracked per file
- “Latest version” is computed, not stored

---

## Stage 6 — Backend Foundation (Design Intent)

Stage 6 establishes a **stable backend substrate** that higher-level systems rely on.

### Design Guarantees

- Deterministic file indexing
- Repeatable rescans
- Explicit integrity states
- Clean separation between disk reality and indexed state

### Non-Responsibilities (by design)

- No asset grouping
- No version semantics
- No tagging logic

---

## Stage 7 — File-Level UI Doctrine

Stage 7 exposes backend state **without altering it**.

### Principles

- File-level UI is diagnostic and maintenance-oriented
- All actions are DB-only unless explicitly stated
- UI must remain stable as asset-level systems are layered above it

### Foundation Decisions

- Centralized event signaling
- Stable ID-based selection
- Separation of views from action logic
- Global action logging surface

These foundations are intentionally reused in later stages.

---

## Stage 8 — Asset Semantics (Design)

Stage 8 introduces **explicit asset meaning** while preserving disk authority.

### Asset Model v0

- Assets are scoped to a storage root
- Assets have:
  - type
  - stable key
  - display name

### Version Model v0

- Versions are **mutable but accountable**
- Display labels (`v01`, `v02`, …) are user-facing
- Internal ordering uses a monotonic sort key
- Membership edits are logged

### Detection System Role

- Detection answers: *“What signals does this file emit?”*
- Detection:
  - is heuristic
  - is reversible
  - never overwrites manual intent

### Detection Constraints

- Runs on demand
- Produces reviewable proposals
- Never auto-reassigns owned files
- Rules are explicit and user-configurable

---

## Stage 9 — Power-User Organization Doctrine

Stage 9 formalizes AssetHub’s **trust model**.

### Signals vs Authority (Locked)

- **Signals**
  - Emitted by filenames, structure, heuristics
  - Fallible and revisable

- **Manual Authority**
  - Explicit user actions
  - Durable
  - Never auto-overridden

### Asset-Centric Versioning

- Versions represent **set snapshots**
- Filename version tokens are metadata, not truth
- Composite assets carry forward unchanged membership
- Older versions remain historically accurate

### Multi-Version Membership

- A file may belong to multiple versions
- Snapshot history is preserved, not rewritten

---

## Files View as Assignment Inbox (Planned Direction)

- Unassigned files are treated as “unowned”
- Files view evolves toward an inbox model
- Primary user action:
  - *Assign selected files to asset/version*

This supports eventual completeness: every file belongs to an asset.

---

## Explicitly Deferred (Intentional)

- Checksum reconciliation
- Project-level workflows
- File-level tagging
- Version snapshot editor UI

Deferrals exist to protect correctness and avoid premature complexity.

---

## Current Design State (Summary)

AssetHub now has:

- A locked architectural foundation
- Trustworthy, pipeline-realistic version semantics
- Clear separation between heuristics and authority
- A scalable path toward manual, user-driven organization

This document serves as the **canonical design reference** for the project.
