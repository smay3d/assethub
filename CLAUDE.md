# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app
python main.py

# Run all tests
pytest

# Run a single test file
pytest tests/test_db_assets.py

# Run a specific test
pytest tests/test_db_assets.py::test_function_name
```

There is no build step, no requirements.txt at the root, and no linter configured. `src/` is added to `sys.path` by `conftest.py` and `main.py`.

## Architecture

AssetHub is a single-user desktop asset management app (PySide6 + SQLite). It indexes files from user-registered filesystem roots without modifying them ("no-write policy"). The filesystem is authoritative; the DB is a derived index.

### Core Doctrine (from design docs)
- **Disk is authoritative** — the DB is a cache of reality, not the source of truth
- **No-write policy** (v0–v1) — AssetHub never renames or moves user files
- **User intent outranks heuristics** — manual overrides always win over auto-detection
- **Power-user first** — expert workflows, not beginner-friendly UX

### Composition Root: `AppContext` (`src/assethub/context.py`)

All long-lived services are owned by `AppContext`, which is the single dependency container passed to UI components. Initialization order matters:

```
Config → DB → StorageManager → Scanner → HealthChecker → EventHub → UI
```

The UI never instantiates services directly; it receives them via `AppContext`.

### Layered Subsystems (`src/assethub/core/`)

| Subsystem | Location | Purpose |
|---|---|---|
| DB | `core/db/` | SQLite schema (v7), migrations, typed query functions |
| Storage | `core/storage/roots.py` | Manages registered filesystem roots; longest-prefix path resolution |
| Scanner | `core/scanner/scanner.py` | Walks roots, indexes files (path, size_bytes, mtime_unix) |
| Health | `core/health/checker.py` | Validates indexed files against disk; sets `integrity_state` |
| Detection | `core/detection/` | Regex-based pattern engine that proposes asset groupings (preview-only, no DB writes) |
| Events | `core/events/event_hub.py` | Non-Qt pub/sub (thread-safe RLock); events: `DbChanged`, `ScanFinished`, `HealthFinished` |
| Log | `core/utils/app_log.py` | Qt-free 800-line ring buffer; bridges to Qt signals for UI display |
| Models | `core/model/` | Frozen dataclasses: `Asset`, `Version`, `File`, `Tag` — no business logic |

### DB Schema (v7)

Tables: `storage`, `asset`, `version`, `file`, `tag`, `asset_tag`, `file_binding`, `version_file`, `version_change_log`

Files have an `integrity_state` column (`OK` / `MISSING` / `UNRESOLVED`) maintained by `HealthChecker`. The "Unmanaged" storage root is a singleton for files outside any registered root.

### UI Layer (`src/assethub/ui/`)

**MainWindow** holds a vertical splitter: tab area on top, global log view on bottom. ESC triggers a global cancel event.

Three tabs:
- **LibraryTab** — browse/filter files by storage, integrity state, tags, text search; uses `FileTableModel` + `QSortFilterProxyModel`
- **ScanTab** — register roots, trigger scans, run health checks, preview detection proposals
- **SettingsTab** — config and diagnostics display

Background operations (scan, health check) are cancellable via `threading.Event` passed as a `cancel_check` callback.

### Key Design Docs

Authoritative design decisions and implementation stage tracking live in:
- `AssetHub_DesignSummary_v1.9.md` — architecture decisions and rationale
- `AssetHub_DevLog_v1.7.md` — stage-by-stage implementation log (Stages 5–9+)

Consult these before making structural changes.
