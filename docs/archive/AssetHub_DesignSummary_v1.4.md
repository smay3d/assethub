# AssetHub Project Design Summary (v1)

This document captures the current design state of the AssetHub project for reference, consistency, and future development. It summarizes each stage completed so far and the decisions made.

---

## **Stage 1 — Goals & Scope**
- AssetHub is a single-pane desktop application for browsing, organizing, and previewing assets located anywhere on disk.
- Audience: primarily single-user, power-user workflows.
- MVP features:
  - Asset ingest/scanning
  - Versioning (immutable)
  - Tagging
  - Library view with preview pane
  - Sidecar JSON metadata storage
  - Storage roots for linking arbitrary filesystem locations
- Non-goals for v0:
  - Cloud sync
  - Multi-user permissions
  - AI tagging

---

## **Stage 2 — Data Model Overview**
### Core Entities
- **Asset** — conceptual object (e.g., Raven A, Oak Bark 001).
- **Version** — immutable snapshot of Asset.
- **File** — physical file on disk, linked to Version.
- **Tag** — labels for organizing assets.
- **Storage** — logical roots for resolving file paths.
- **Preview** (*future*) — thumbnails/turntables.
- **Collections** (*future*) — manual groupings.
- **SmartFolders** (*future*) — query-based dynamic lists.

### Metadata Strategy
- Hybrid model: **SQLite database (source of truth for index)** + **centralized sidecar JSONs** under `SIDECARS/<asset-id>/` for portability/extensibility.
- Versions are **immutable**.
- Assets/files can live **anywhere on disk**.

---

## **Stage 2b — Storage Choice & Hybrid Architecture**
### Chosen Approach
- **Hybrid system:** SQLite (index) + centralized sidecar JSONs.
- Sidecars store:
  - `asset.json` per asset
  - `vX.Y.Z.json` per version
- Sidecars do **not** live beside the asset files.
- Previews stored in `CACHE/previews/`.

### Storage Roots
- User registers multiple storage roots.
- Scanner only scans inside registered roots.
- Manual file attachments may fall under no root ➝ assigned to special **"Unmanaged"** storage.

### Selected Initial Storage Roots
- `A:\Art\Assets`
- `A:\Art\Projects\2025`
- `A:\Education\Academy of Art\Fall 2025`
- `G:\Minecraft\Minecraft Skins`

---

## **Stage 3 — Folder & Naming Rules**
### Central AssetHub Folder Structure
```
E:\AssetHub\
  DB\
  SIDECARS\
  CACHE\previews\
  LOGS\
```
- Database file lives in `DB/`.
- Sidecar JSONs in `SIDECARS/<asset-id>/`.
- Previews in hashed subfolders under `CACHE/previews/`.

### Asset File Locations
- Asset files remain *wherever the user keeps them* (project folders, libraries, external drives).
- No enforced restructuring of user files.
- Naming rules are guidelines only, not required.

---

## **Stage 4 — UX Outline**
### Tabs
1. **Library** — main browsing UI
2. **Detail** — edit and view full asset data
3. **Scan** — register roots, ingest assets, fix issues
4. **Deploy** (*future*) — package assets for DCCs
5. **Settings** — preferences, performance, storage roots

### Library View Design (Option A chosen)
- Notion-style table with customizable columns (future feature).
- Right preview pane updates when selecting an asset.
- Sidebar: SmartFolders + Collections.
- Read-only editing.
- Row background colors display asset health:
  - RED → BROKEN
  - YELLOW → UNRESOLVED
  - BLUE → DUPLICATE

### Detail View
- Editable tabs: Overview, Versions, Files, Attributes, Dependencies, Audit, Notes.
- Sidecar controls.

### Scan View
- Register storage roots.
- Start scans, lint, ingest assets.
- Fix missing/unresolved/duplicate files.

---

## **Stage 5 — Tech Stack & Setup Decisions**
### Chosen Technologies
- **Language:** Python
- **GUI Framework:** PySide6 / Qt6
- **Database:** SQLite via built-in `sqlite3`
- **Sidecars:** JSON files stored under `SIDECARS/`
- **Preview generation:** Python image/video libs (future)
- **Threading:** Qt `QThreadPool` for background work

### Repo Layout (Finalized)
```
assethub/
  src/
    app.py
    context.py
    config/
    core/
      db/
      storage/
      scanner/
      previews/
      sidecar/
      health/
      model/
      utils/
    ui/
      windows/
      views/
      widgets/
      models/
      style/
  data/
  tests/
  README.md
```

---

## **Minimal v0 Database Schema (6 Core Tables)**
1. **storage**
2. **asset**
3. **version**
4. **file**
5. **tag**
6. **asset_tag** (join table)

### Key Concepts
- Files always have a `storage_id`.
- If a file isn’t inside any registered root: assign to **Unmanaged** storage.
- Integrity states stored on each `file` row.
- Latest version computed dynamically via semver comparison.

---

## **Current Development State**
- Planning phases complete for stages 1–5 (conceptual design).
- Ready to begin coding Stage 5 (project skeleton).
- Added decisions:
  - Minimal v0 DB schema with 6 core tables.
  - "Unmanaged" storage root for manual/legacy file paths.
  - AppContext will manage DB, storage, sidecars, previews, scanner, health, and threadpool.
  - Config system finalized: default + user config with paths, UI settings, performance settings.
  - Startup sequence established (load config → init context → open DB → load storage → launch UI).
- Next step: Begin coding in a separate implementation thread.

### Update — Stage 5 Complete (Skeleton + Wiring)

- Stage 5.5 (Project Code Skeleton) implemented:
  - Full repo directory structure created
  - AppContext, config loader, and core subsystem packages added
  - MainWindow created with Library / Detail / Scan / Settings tabs
  - Entry point finalized (`main.py` at repo root)

- Stage 5.6 (Initial Wiring) implemented:
  - Config loads at startup
  - AppContext initializes all manager objects (empty skeletons)
  - ThreadPool created and accessible
  - MainWindow receives AppContext and can access all managers
  - Temporary diagnostic added to confirm successful wiring

- Tests configured and passing:
  - pytest integrated via `python -m pytest`
  - `conftest.py` ensures src/ is on Python path
  - `test_smoke.py` validates config + AppContext initialization
  - `test_ui_imports.py` validates UI package integrity


---

## Stage 6 — Core Systems (Implemented)

Stage 6 completes the foundational backend systems of AssetHub. At this point, the application has transitioned from a structural prototype into a functioning core platform capable of persisting data, indexing files, and validating file integrity. All systems described below are implemented, tested, and in active use by the application.

### Database & Persistence

AssetHub now maintains a persistent SQLite database that serves as the authoritative source of truth for indexed assets and files.

- The database schema is created automatically at startup if it does not exist.
- Foreign key enforcement is enabled to preserve relational integrity.
- Core tables include:
    - `storage` — registered storage roots
    - `asset` — conceptual asset containers (reserved for future stages)
    - `version` — asset version placeholders (reserved)
    - `file` — indexed physical files
    - `tag` and `asset_tag` — tagging infrastructure (reserved)
- Schema creation is idempotent and safe to call on every launch.

### Storage Roots & Path Resolution

AssetHub understands file locations through a system of registered storage roots.

- Storage roots are persisted in the database.
- Every file indexed by AssetHub belongs to exactly one storage entry.
- A special `Unmanaged` storage entry is always guaranteed to exist.
- Absolute file paths are resolved deterministically using longest-prefix matching against registered roots.
- This system ensures all files can be reasoned about, even if they fall outside known or user-managed directories.

### File Scanning & Indexing

AssetHub can index files on disk into the database.

- Registered storage roots are scanned recursively.
- Physical files are detected and recorded in the `file` table.
- For each file, AssetHub records:
    - storage association
    - relative path within the storage root
    - file size
    - modification timestamp
- Repeated scans update existing records rather than creating duplicates.
- No asset grouping, versioning, or tagging semantics are applied at this stage.

### File Health & Integrity

AssetHub can validate indexed files against disk reality.

- Indexed files are checked to ensure they still exist at their expected locations.
- Each file maintains an `integrity_state` reflecting its current health:
    - `OK` — file exists as expected
    - `MISSING` — file no longer exists on disk
    - `UNRESOLVED` — file path cannot be resolved to a valid storage root
- Health checks are diagnostic only and do not modify or recover files.

### Application Context & Lifecycle

AssetHub exposes all core systems through a centralized application context.

- `AppContext` acts as the composition root of the application.
- It owns and initializes all long-lived resources, including:
    - database connection
    - storage manager
    - scanner
    - health checker
    - auxiliary managers (sidecar, previews)
- A formal shutdown mechanism exists to release owned resources cleanly.
- UI layers and future systems are expected to access shared state exclusively through `AppContext`.

### Resulting State

With Stage 6 complete, AssetHub now has a stable and testable backend capable of:

- Persisting structured metadata
- Understanding where files live on disk
- Indexing files deterministically
- Detecting missing or broken references
- Providing a clean, authoritative interface for higher-level systems

This completes the core backend foundation and prepares the project for UI integration and asset semantics in the next stage.

---

## Stage 7 — UI Integration & Asset Semantics (Planned)

---

*This document acts as the authoritative design reference for the project’s current state.*

