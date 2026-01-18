# AssetHub Development Log (v1.5)

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

**Status:** Complete (Stages 6.1–6.5)

**Dates:** 2025-12-18

**Tests:** Passing (10 tests)

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

---

## Stage 7 — UI Integration (File-Level)

**Status:** Complete

**Dates:** 2026-01-14 to 2026-01-18

**Tests:** Passing (pytest green)

### Overview
Stage 7 exposes the Stage 6 backend through a usable, file-level UI. The focus is read-only inspection and safe DB maintenance (no modification of user assets on disk). This stage also lays the UI foundation needed for Stage 8 (asset-level semantics) without UI drift.

---

### 7.1 — Scan Tab (Roots + Scan + Health + Cancel)

**Status:** Complete

- Implemented a functional **Scan** tab with a storage roots panel, actions panel, and status reporting.
- Added UI flows to **Add Root…** and **Remove Root** with guardrails:
  - Unmanaged storage is protected and cannot be removed.
  - Safe root removal is blocked if tracked files still reference the root.
- Implemented **Scan Roots** to index files into the `file` table using the Stage 6 scanner.
- Implemented **Run Health Check** to update `integrity_state` using the Stage 6 health checker.
- Added a cancelable worker pattern and **ESC cancels current job** without freezing the UI.

---

### 7.2 — Library Tab (Table + Search/Filter/Sort)

**Status:** Complete

- Implemented a **Library** tab that displays DB-tracked file rows (`file` joined with `storage`).
- Added a model/proxy approach to support:
  - Column sorting
  - Search by filename (primary) and relative path (secondary)
  - Dropdown filters (storage root, integrity state)
- Added a developer toggle: **Show hidden columns** (IDs and raw/internal fields).
- Added selection signaling using stable `file_id` for downstream detail view integration.

---

### 7.3 — Library Detail Pane (Preview + Read-Only File Details)

**Status:** Complete

- Upgraded Library to a **master–detail split view** (table left, detail pane right).
- Implemented a **File Detail Pane** with:
  - Best-effort image previews for supported formats
  - A clean fallback message when preview is unavailable
  - Read-only metadata fields including resolved absolute path (when possible)
  - Collapsible “Advanced” section for raw/internal fields
- Added a table context menu for quick copy/open operations.
- Implemented selection preservation on refresh by `file_id` when possible.

---

### 7.4 — Settings Tab (Read-Only Transparency)

**Status:** Complete

- Added a **Settings** tab that surfaces “under the hood” information as read-only diagnostics, including:
  - App version + DB schema version
  - Key configured paths (data root, db path, sidecar root, preview cache, log root) with copy/open helpers
  - DB/index stats (tracked files, missing files, storage root count, unmanaged presence, db size)
  - UI behavior transparency (row caps, supported preview formats, etc.)
- Included refresh behavior so values stay accurate during development and testing.

---

### 7.5 — UI Foundation (EventHub + Multi-Select + Library Actions + Missing Cleanup)

**Status:** Complete

- Introduced **EventHub**, a lightweight non-Qt signaling hub owned by `AppContext`:
  - `db_changed(reason, payload)`
  - `scan_finished(summary)`
  - `health_finished(summary)`
- Subscribed Library and Settings to EventHub updates to keep views in sync.
- Upgraded Library selection to standard desktop **multi-select** (ExtendedSelection) and clarified:
  - “Current” row drives preview
  - “Selected set” drives multi-select summaries and action targets
- Added a dedicated **LibraryActions** layer to keep DB/action plumbing out of the view.
- Implemented a robust Library context menu action set:
  - Open / reveal / copy utilities
  - Targeted health check for selected file IDs
  - Remove-from-database for MISSING-only selections (with confirmation)
- Added a Scan tab bulk maintenance tool: **Remove all MISSING records from database…**

---

### 7.6 — UI Foundation Extensions (Global Log + Storage Display Names + Remove Roots)

**Status:** Complete

- Added a **Global MainWindow Log** as a bottom split-pane across the entire app:
  - Central logging API: `ctx.log.info/warn/error(...)`
  - Action summaries written consistently for major operations
  - Removed the Scan tab summary log box (promoted to global)
- Implemented **Storage root display names**:
  - Added `storage.display_name` and bumped DB schema to **v2**
  - UI shows `display_name` with fallback to the base storage name
  - Rename action in Scan tab context menu (DB-only; Unmanaged not renameable)
- Implemented **Remove root from tracking** (explicit destructive action):
  - Scan tab context menu action with clear confirmation
  - Transactional DB cascade delete (files first, then storage)
  - No disk deletes; immediate UI refresh via EventHub; summary written to global log

---

### Stage 7 Outcome
By the end of Stage 7, AssetHub provides a stable, developer-friendly file-level UI that exposes the Stage 6 backend end-to-end, and establishes the selection + action + signaling foundations needed to implement Stage 8 (asset semantics) without reworking the UI architecture.
