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

*This document acts as the authoritative design reference for the project’s current state.*

