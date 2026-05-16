# Raptor Architecture

**Last updated:** 2026-05-13
**Status:** Initial stub — update after any structural change to the codebase.

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.x |
| UI | PySide6 (Qt6) |
| Database | SQLite (Python stdlib `sqlite3`) |
| Testing | pytest |
| Distribution | PyInstaller → standalone `.exe` |

---

## Repository Layout

```
AssetHub/
├── src/
│   └── assethub/
│       ├── context.py          # AppContext — composition root
│       ├── app.py              # Qt application bootstrap
│       ├── config/             # Config loading and defaults
│       └── core/               # Qt-free backend
│           ├── db/             # Schema, migrations, typed query functions
│           ├── storage/        # Storage roots, longest-prefix path resolution
│           ├── scanner/        # File indexing (no disk writes)
│           ├── health/         # integrity_state maintenance
│           ├── detection/      # Heuristic asset grouping (proposal-only)
│           ├── events/         # Non-Qt pub/sub (EventHub)
│           ├── model/          # Frozen dataclasses: Asset, Version, File, Tag
│           └── utils/          # AppLog (ring buffer), checksum
│       └── ui/                 # All PySide6 code
│           ├── windows/        # MainWindow
│           ├── views/          # Tab views: Library, Scan, Settings
│           ├── models/         # Qt table models (QAbstractTableModel)
│           ├── dialogs/        # Modal dialogs
│           ├── actions/        # Action logic, decoupled from views
│           └── style/          # QSS theme engine (qss.py)
├── tests/                      # pytest suite (runs headless)
├── docs/
│   └── raptor/                 # Core Raptor documentation
│       ├── Raptor_Architecture.md   (this file)
│       ├── Raptor_Changelog.md
│       ├── Raptor_Status.md
│       └── Raptor_ProjectSpec.md
└── main.py                     # Entry point
```

---

## Composition Root

`AppContext` (`src/assethub/context.py`) owns all long-lived services and is the single
dependency container passed to UI components.

**Initialization order:**
```
Config → DB → StorageManager → Scanner → HealthChecker → EventHub → UI
```

UI components receive `AppContext` and access services through it. Services are never
instantiated directly by UI code.

---

## Core Subsystems

| Subsystem | Module | Responsibility |
|---|---|---|
| DB | `core/db/` | Schema v7, migrations, typed query helpers |
| Storage | `core/storage/roots.py` | Root registration, longest-prefix path resolution, Unmanaged singleton |
| Scanner | `core/scanner/scanner.py` | Walks registered roots, upserts file records (path, size, mtime) |
| Health | `core/health/checker.py` | Validates indexed files against disk; sets `integrity_state` |
| Detection | `core/detection/` | Regex rule engine → reviewable asset proposals, no auto-writes |
| Events | `core/events/event_hub.py` | Non-Qt pub/sub signaling (thread-safe RLock) |
| Log | `core/utils/app_log.py` | 800-entry ring buffer; UI sink callback for live display |
| Models | `core/model/` | Value objects: `Asset`, `Version`, `File`, `Tag` |

**Invariant:** `core/` imports zero Qt. Any import of PySide6 in `core/` is a violation.

---

## DB Schema

**Current version:** v7

**Tables:** `storage`, `asset`, `version`, `file`, `tag`, `asset_tag`,
`file_binding`, `version_file`, `version_change_log`

**Key invariants:**
- Every file belongs to exactly one storage root
- Files outside all registered roots → Unmanaged (always exists, cannot be deleted)
- `integrity_state` per file: `OK` / `MISSING` / `UNRESOLVED`
- "Latest version" is computed, not stored
- Manual `file_binding` records survive re-scans and outrank detection

*Update this section when the schema version changes.*

---

## UI Layer

**MainWindow** holds a vertical splitter: tab area (top) + global log view (bottom).

**Tabs:**
- **LibraryTab** — browse/filter files and assets; `FileTableModel` + `QSortFilterProxyModel`
- **ScanTab** — register roots, trigger scans, run health checks, preview detection proposals
- **SettingsTab** — config display, diagnostics, theme toggle

Background operations (scan, health check) use `QThreadPool` workers with a
`threading.Event` passed as `cancel_check`. ESC triggers a global cancel.

---

## Planned Structural Changes (Raptor Reboot)

- `ui/` to be rewritten from scratch (PySide6 retained; visual design to be defined)
- `core/sidecar/` to be deleted (feature removed from scope)
- `core/utils/logging.py`, `core/utils/paths.py`, `core/config/defaults.py` to be deleted
  (confirmed dead code per audit v1.0)

*Remove this section once the reboot structural work is complete.*
