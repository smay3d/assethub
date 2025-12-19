# AssetHub — Stage 6 Design & Implementation Plan

**Stage:** 6 — Core Systems Implementation  
**Date:** December 18, 2025  
**Prerequisite:** Stage 5 complete (project skeleton + wiring)

---

## Purpose of Stage 6

Stage 6 transitions AssetHub from a structural skeleton into a functioning system. The goal is to implement the *minimum viable core logic* required for the application to index files on disk, persist metadata, and reason about asset health — without yet implementing UI population, asset/version semantics, or previews.

This stage emphasizes **correctness, invariants, and testability** over polish or UX.

---

## Scope (What Stage 6 Includes)

- SQLite database initialization and schema creation
- Persistent storage root handling
- Guaranteed "Unmanaged" storage behavior
- File system scanning and indexing
- Basic file integrity (health) checks
- AppContext lifecycle stabilization

---

## Non‑Goals (Explicitly Deferred)

- Asset creation or grouping logic
- Version semantics beyond placeholders
- Tagging UI or logic
- Preview generation
- SmartFolders, Collections, or Deploy workflows
- Performance optimization or threading refinements

---

## Stage 6 Sub‑Stages

### **6.0 — Baseline Checkpoint**
**Goal:** Establish a clean starting point.

- Confirm all Stage 5 tests pass
- Create a git tag (e.g. `v0.1.1-stage5-complete`)
- No code changes

---

### **6.1 — Database Initialization & Schema**
**Goal:** Ensure a usable SQLite database with the minimal v0 schema.

**Responsibilities:**
- Open or create database file at startup
- Enable foreign key enforcement
- Create required tables if they do not exist
- (Optional) Record schema version for future migrations

**Tables Created:**
- `storage`
- `asset`
- `version`
- `file`
- `tag`
- `asset_tag`

**Primary Modules:**
- `core/db/schema.py`
- `core/db/connection.py`
- `context.py`

**Tests:**
- Schema creation validation
- Table existence checks

**Exit Criteria:**
- App reliably creates and opens DB
- All required tables exist

---

### **6.2 — Storage Roots & Unmanaged Invariant**
**Goal:** Persist storage roots and resolve file paths deterministically.

**Key Invariants:**
- All files must belong to a storage entry
- A special `Unmanaged` storage always exists

**Responsibilities:**
- Register storage roots in DB
- Resolve file paths to storage IDs
- Fallback to `Unmanaged` storage when no root matches

**Primary Module:**
- `core/storage/roots.py` (`StorageManager`)

**Tests:**
- Root registration
- Path resolution
- Unmanaged fallback behavior

**Exit Criteria:**
- Any absolute path maps to a valid storage ID

---

### **6.3 — Scanner v1 (File Indexing)**
**Goal:** Index files on disk into the database.

**Responsibilities:**
- Walk registered storage roots
- Detect files recursively
- Insert or update rows in the `file` table
- Capture basic file metadata (path, storage, size, timestamps)

**Constraints:**
- No asset or version creation yet
- Scanner operates at the file‑only level

**Primary Module:**
- `core/scanner/scanner.py`

**Tests:**
- Temp directory scanning
- File row insertion verification

**Exit Criteria:**
- Database accurately reflects on‑disk files

---

### **6.4 — Health Check v1 (Missing Detection)**
**Goal:** Detect and mark missing or unresolved files.

**Responsibilities:**
- Iterate indexed files
- Verify expected paths still exist
- Update integrity state accordingly

**Primary Module:**
- `core/health/checker.py`

**Tests:**
- File deletion after scan
- Integrity state update validation

**Exit Criteria:**
- File integrity state reflects disk reality

---

### **6.5 — AppContext Stabilization & Cleanup**
**Goal:** Lock in clean service contracts for Stage 7.

**Responsibilities:**
- Ensure AppContext exposes stable core services
- Remove temporary diagnostics
- Prepare system for UI‑driven queries

**Primary Module:**
- `context.py`

**Exit Criteria:**
- Clean startup
- No debug scaffolding required

---

## Recommended Implementation Order

1. 6.1 — Database schema
2. 6.2 — Storage roots
3. 6.3 — Scanner
4. 6.4 — Health checks
5. 6.5 — Cleanup

Each sub‑stage should be committed independently with tests.

---

## Deliverables

By the end of Stage 6, AssetHub will:
- Maintain a valid persistent database
- Understand where files live
- Index files deterministically
- Detect missing or broken references
- Provide a stable backend for Stage 7 UI integration

---

*This document serves as the authoritative plan for Stage 6 development.*

