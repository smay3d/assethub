# AssetHub Development Log

This document records the concrete implementation progress of AssetHub.  
It complements the main design document by describing *what has actually been built* at each stage.

---

## Stage 5 — Project Skeleton & Initial Wiring  
**Status:** Complete  
**Date:** 2025-11-22  
**Tests:** Passing (4 tests)

### Overview
Stage 5 focused on creating the structural foundation of the AssetHub application without implementing any business logic. The goal was to establish a stable project skeleton, initialize core manager objects, and ensure the UI and startup flow operate without errors. All code compiles, runs successfully, and loads an empty but functional Qt interface.

### Completed Work

#### 5.5 — Project Code Skeleton  
- Created full directory layout under `src/assethub/` according to the design spec.
- Added core package groups:
  - `config/`
  - `core/` (db, storage, scanner, previews, sidecar, health, model, utils)
  - `ui/` (windows, views, widgets, models, style)
- Added `AppContext` class as the central access point for subsystem managers.
- Added `app.py` with the initial Qt application bootstrap.
- Added top-level `main.py` (root entry point).
- Created `MainWindow` with four placeholder tabs (Library, Detail, Scan, Settings).

#### 5.6 — Initial Wiring  
- `app.py` now loads configuration and initializes AppContext.
- AppContext now instantiates:
  - StorageManager  
  - SidecarManager  
  - PreviewManager  
  - HealthChecker  
  - Scanner  
  - QThreadPool (global instance)
- MainWindow receives the context and has access to all managers.
- Added temporary diagnostic printing to verify all systems initialize correctly.

#### Testing Infrastructure  
- Installed pytest for the project.
- Added `conftest.py` to ensure `src/` is added to `sys.path` during testing.
- Tests added:
  - `test_smoke.py`  
    - Verifies version string  
    - Verifies config loading  
    - Verifies AppContext manager initialization
  - `test_ui_imports.py`  
    - Ensures MainWindow imports without error
- All tests pass: 4 passed in 0.13s


### Summary
Stage 5 delivered a fully functional application skeleton with wiring for manager objects, configuration loading, and UI integration. The system launches successfully from `python main.py`, and the test suite verifies that the base infrastructure is solid. No database tables, schema logic, or scanning behavior have been implemented yet — these are the goals of Stage 6.

---

## Stage 6 — Core Systems Implementation

**Status:** In Progress (through Stage 6.3)

**Dates:** 2025-12-18

**Tests:** Passing (9 tests)

### Overview

Stage 6 transitions AssetHub from a structural skeleton into a functioning backend system. The focus is on correctness, invariants, and testability, intentionally deferring UI population, asset semantics, and preview generation.

---

### 6.1 — Database Initialization & Schema

**Status:** Complete

- Implemented SQLite database bootstrap at application startup.
- Added idempotent schema creation for minimal v0 tables:
    - `storage`, `asset`, `version`, `file`, `tag`, `asset_tag`
    - `schema_version` table for future migrations.
- Enabled foreign key enforcement.
- Added tests validating schema creation and table existence.

---

### 6.2 — Storage Roots & Unmanaged Invariant

**Status:** Complete

- Implemented `StorageManager` backed by the `storage` table.
- Added persistent registration of storage roots.
- Guaranteed existence of a single `Unmanaged` storage entry.
- Implemented deterministic path resolution using longest-prefix matching.
- Added tests covering root registration, resolution, and unmanaged fallback.

---

### 6.3 — Scanner v1 (Files-Only Indexing)

**Status:** Complete

- Implemented first functional scanner pass:
    - Walks registered storage roots only.
    - Indexes physical files into the `file` table.
    - Stores `storage_id`, `relative_path`, `size_bytes`, `mtime_unix`.
    - Uses upsert logic to allow safe re-scans.
- Explicitly does **not** create assets, versions, or tags.
- Added `test_scanner_basic.py` validating recursive scanning and relative path handling.

### Supporting Fixes

- Simplified `get_connection()` to be a pure connection factory (no global caching).
- Clarified DB connection lifetime ownership under `AppContext`.

---

### **6.4 — Health Check v1 (Missing Detection)**

**Status:** Complete

**Tests:** Passing (10 total)

**Summary:**

Implemented the first functional health-check system, allowing AssetHub to validate indexed files against disk reality.

**Completed Work:**

- Implemented `HealthChecker` with a files-only integrity pass.
- Added `check_all_files()` to:
    - Iterate indexed files.
    - Reconstruct expected absolute paths from storage roots + relative paths.
    - Update `file.integrity_state` to:
        - `OK` if the file exists.
        - `MISSING` if the file no longer exists.
        - `UNRESOLVED` if the storage root cannot be resolved.
- Integrated `HealthChecker` into `AppContext`.

**Testing:**

- Added `test_health_missing_detection.py`.
- Verified integrity state updates when files are deleted after scanning.
- Confirmed non-deleted files remain `OK`.

---

### **6.5 — AppContext Stabilization & Cleanup**

**Status:** Complete

**Tests:** Passing (10 total)

**Summary:**

Stabilized the application lifecycle and clarified ownership boundaries in preparation for UI integration in Stage 7.

**Completed Work:**

- Formalized `AppContext` as the application composition root.
- Added class-level documentation describing ownership and responsibilities.
- Added an explicit `shutdown()` method to cleanly release owned resources.
- Clarified and documented initialization order inside `initialize_core_services()`.
- Removed stage-specific scaffolding comments from production logic.
- Verified naming consistency and public surface stability for core services.
- Simplified database connection handling to a pure connection factory model, with `AppContext` owning connection lifetime.

**Result:**

- `AppContext` now provides a stable, explicit contract for UI layers.
- Core systems (DB, storage, scanner, health) are cleanly wired and lifecycle-safe.
- Stage 6 backend functionality is complete and ready for UI-driven access.

---

### **Stage 6 — Core Systems Implementation**

**Overall Status:** **Complete**

**Outcome:**

By the end of Stage 6, AssetHub now:

- Maintains a persistent SQLite database with a stable schema.
- Understands and manages storage roots deterministically.
- Indexes files reliably from disk into the database.
- Detects missing or unresolved files via health checks.
- Exposes a clean, stable backend through `AppContext` for future UI integration.