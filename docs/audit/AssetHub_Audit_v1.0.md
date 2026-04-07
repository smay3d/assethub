# AssetHub Codebase Audit v1.0

**Date:** 2026-04-06  
**Auditor:** Claude Code (Sonnet 4.6)  
**Scope:** Full codebase, all source files, all tests, design documents  
**Branch:** `dev` @ commit `a5f0486` (Stage 9.3.3)  
**Verdict:** Codebase is healthy and well-structured. No showstoppers. Minor issues noted below.

---

## 1. Implementation Status

### What's Built

The implementation faithfully tracks the design documents through **Stage 9.3.3**. Everything described up to that stage is present and functional.

| Feature | Status | Location |
|---|---|---|
| DB schema v7 with migrations | Complete | `core/db/schema.py` |
| Storage roots (longest-prefix) | Complete | `core/storage/roots.py` |
| Unmanaged storage singleton | Complete | `core/storage/roots.py:182-210` |
| File scanner (files-only) | Complete | `core/scanner/scanner.py` |
| Health checker (OK/MISSING/UNRESOLVED) | Complete | `core/health/checker.py` |
| Asset + Version semantics | Complete | `core/db/assets.py`, `versions.py` |
| Multi-version membership (v6 join table) | Complete | `core/db/version_membership.py` |
| Change log (per-action audit trail) | Complete | `core/db/versions.py:~90-130` |
| Discarded versions | Complete | schema v5, respected in health + library queries |
| Tagging (asset-level, with color) | Complete | `core/db/tags.py` |
| Detection engine (preview-only) | Complete | `core/detection/engine.py` |
| Detection rules (user override + defaults) | Complete | `core/detection/rules_loader.py` |
| Detection apply (materialize proposals) | Complete | `core/detection/apply.py` |
| Manual file→asset binding (v7) | Complete | `core/db/file_bindings.py` |
| Binding-triggered version-up | Complete | `core/db/binding_versioning.py` |
| EventHub (non-Qt pub/sub) | Complete | `core/events/event_hub.py` |
| AppLog (ring-buffer, 800 entries) | Complete | `core/utils/app_log.py` |
| AppContext composition root | Complete | `context.py` |
| LibraryTab (files + assets mode) | Complete | `ui/views/library_tab.py` |
| ScanTab (roots, scan, health, detect) | Complete | `ui/views/scan_tab.py` |
| SettingsTab (read-only diagnostics) | Complete | `ui/views/settings_tab.py` |
| Checksum (on-demand SHA-256) | Complete | `core/utils/checksum.py` |
| Tag manager + tag select dialogs | Complete | `ui/dialogs/` |
| File detail pane | Complete | `ui/views/file_detail_pane.py` |
| Asset library widget | Complete | `ui/views/assets_library_widget.py` |
| Version conflict dialog | Complete | `ui/dialogs/version_conflict_dialog.py` |
| File select dialog | Complete | `ui/dialogs/file_select_dialog.py` |
| Library actions (copy path, checksum, etc.) | Complete | `ui/actions/library_actions.py` |

### What's Not Built Yet (Intentional Deferrals)

| Feature | Status | Notes |
|---|---|---|
| Preview image generation | Stub only | `core/previews/manager.py` is an empty class with a TODO comment |
| Sidecar JSON I/O | Stub only | `core/sidecar/manager.py` has `__init__` only; no read/write methods |
| User config file loading | Skeleton only | `config/loader.py` always returns defaults; comment documents this |
| DB-stored checksums | Not started | On-demand `sha256_file()` exists; no storage or reconciliation |
| Project/multi-user workflows | Non-goal | Explicitly out of scope for v0 |

These are all acknowledged in the design documents and don't represent gaps — they're the frontier of unimplemented stages.

---

## 2. Discrepancies Between CLAUDE.md and Actual Code

### 2a. AppLog described as "800-line ring buffer" in CLAUDE.md

CLAUDE.md says: `core/utils/app_log.py` — "Qt-free 800-line ring buffer"

The file is 95 lines long. The 800 is the **ring buffer capacity** (number of log entries retained), not the file size. The description is technically accurate but phrased ambiguously.

**No action needed**, but worth clarifying if CLAUDE.md is ever updated.

### 2b. CLAUDE.md omits `core/utils/logging.py` and `core/utils/paths.py`

CLAUDE.md lists `core/utils/app_log.py` as the only utility in that package. Two additional files exist:
- `core/utils/logging.py` — a stdlib `logging` wrapper (`get_logger`)
- `core/utils/paths.py` — an `ensure_dir` helper

Neither is imported anywhere in the codebase (see §3 below). CLAUDE.md's omission of them is accurate in spirit but leaves them unacknowledged.

### 2c. CLAUDE.md mentions `core/model/` but omits the `File.version_id` type issue

CLAUDE.md says models are "frozen dataclasses." The `File` model is not frozen (`@dataclass`, not `@dataclass(frozen=True)`). The `Asset`, `Version`, and `Tag` models are. Minor inconsistency — see §4 for the more significant type issue.

---

## 3. Dead Code, Unused Imports, Orphaned Files

### 3a. Orphaned file: `src/assethub/core/config/defaults.py`

**File:** `src/assethub/core/config/defaults.py`  
**Issue:** This file is never imported anywhere. It duplicates `src/assethub/config/defaults.py` with two differences:
1. It includes `"rules_root"` in the paths dict returned by `get_default_paths()`.
2. It passes `rules_root=""` explicitly to `AppConfig()`.

The actual config path used by `config/loader.py` is `src/assethub/config/defaults.py` (via `from .defaults import build_default_config`). The `core/config/defaults.py` version appears to be an earlier draft or an abandoned parallel implementation. It is dead code.

**Recommendation:** Delete `src/assethub/core/config/defaults.py`.

### 3b. Orphaned file: `src/assethub/core/utils/logging.py`

**File:** `src/assethub/core/utils/logging.py`  
**Issue:** Defines `get_logger(name: str) -> logging.Logger`. A search of the entire `src/` tree finds no imports of this function. The actual logging system is `AppLog` (`core/utils/app_log.py`), which is Qt-free and owned by `AppContext`. This stdlib wrapper is never used.

**Recommendation:** Delete `src/assethub/core/utils/logging.py`.

### 3c. Orphaned file: `src/assethub/core/utils/paths.py`

**File:** `src/assethub/core/utils/paths.py`  
**Issue:** Defines `ensure_dir(path: str | Path) -> Path`. A search of `src/` finds no imports of this function. Directory creation happens ad-hoc where needed (e.g., `app.py` probably uses `Path.mkdir` directly if at all).

**Recommendation:** Delete `src/assethub/core/utils/paths.py`, or integrate it where directory creation is actually needed.

### 3d. Unused imports in `src/assethub/core/sidecar/manager.py`

**File:** `src/assethub/core/sidecar/manager.py`, lines 5–6  
```python
from pathlib import Path
from typing import Any, Dict
```
`Path` is used on line 15 (`self.root = Path(root)`). `Any` and `Dict` are imported but never referenced.

**Recommendation:** Remove `Any, Dict` from the import on line 6.

### 3e. `src/assethub/config/defaults.py` — unused import `Any`

**File:** `src/assethub/config/defaults.py`, line 6  
```python
from typing import Dict, Any
```
`Dict` is used in the return type annotation on line 11. `Any` is never used.

**Recommendation:** Remove `Any` from the import.

---

## 4. Fragile, Outdated, or Inconsistent Subsystems

### 4a. `File.version_id` type mismatch (Medium risk)

**File:** `src/assethub/core/model/file.py`, line 11  
**File:** `src/assethub/core/db/schema.py`, line 111  

The DB schema declares `version_id INTEGER` as nullable (no `NOT NULL`), with a `FOREIGN KEY ... ON DELETE SET NULL`. This means a `File` row can have `version_id = NULL` when its owning version is deleted.

The `File` dataclass declares:
```python
version_id: int
```
It should be:
```python
version_id: Optional[int]
```

Any code path that constructs a `File` from a row where `version_id IS NULL` will store `None` in a field typed as `int`. This won't raise a Python exception at runtime (Python dataclasses don't enforce types), but type checkers (mypy, Pyright) will flag every callsite that handles `File.version_id`. More importantly, code that assumes `file.version_id` is always a valid integer will silently behave incorrectly for unowned files.

The `version_membership.py` module is aware of this dual-state and handles it correctly at the SQL level. The risk is in code that constructs `File` objects from raw rows without checking for NULL first.

**Recommendation:** Change `version_id: int` to `version_id: Optional[int]` in `src/assethub/core/model/file.py`. Add `from __future__ import annotations` and `from typing import Optional` if not already present.

### 4b. `File` model is not frozen

**File:** `src/assethub/core/model/file.py`, line 8  
```python
@dataclass
class File:
```

The `Asset`, `Version`, and `Tag` models are all `@dataclass(frozen=True)`. `File` is mutable. This is probably an oversight rather than an intentional design choice — models are meant to be value objects.

**Recommendation:** Change to `@dataclass(frozen=True)` if `File` instances are never mutated after construction (verify first; one callsite might assign `file.version_id = ...`).

### 4c. `scan_tab.py` uses `getattr` defensively for a non-optional config field

**File:** `src/assethub/ui/views/scan_tab.py`, line 446  
```python
rules_root=getattr(self.context.config, "rules_root", None),
```
`rules_root` is a defined field on `AppConfig` with a default of `""`. Using `getattr` with a fallback of `None` suggests this was added before `rules_root` was guaranteed to exist, and was never cleaned up. It's now safe to use `self.context.config.rules_root` directly.

Passing `None` vs `""` makes no functional difference here because `resolve_rules_root()` treats both as falsy. But it implies `None` is a valid value for a `str` parameter, which misleads readers.

**Recommendation:** Replace `getattr(self.context.config, "rules_root", None)` with `self.context.config.rules_root`.

### 4d. `core/utils/logging.py` shadows the intent of `AppLog`

**File:** `src/assethub/core/utils/logging.py`  
The stdlib-based `get_logger()` would bypass `AppLog` entirely if ever used. The design intent (confirmed in CLAUDE.md and design docs) is that all logging flows through `AppLog` so the UI can display it via a sink callback. A developer unfamiliar with the codebase might reach for `get_logger()` and silently break the log display in the UI.

**Recommendation:** Delete the file (see §3b). If stdlib logging is ever needed alongside `AppLog`, document the integration point clearly.

### 4e. `AppConfig.rules_root` not populated by the active defaults file

**File:** `src/assethub/config/defaults.py`  

`build_default_config()` creates `AppConfig(...)` without passing `rules_root=`, so it defaults to `""`. The `core/config/defaults.py` (the dead copy) does populate it with `str(base / "rules")`. This means the user-facing rules directory path (`~/AssetHub/rules/`) that the design specifies is never wired into the config object, even though `rules_loader.py` correctly falls back to `data_root / "rules"` when `rules_root` is empty.

The fallback makes this a non-issue functionally — rules resolution works correctly. But `AppConfig.rules_root` is effectively always `""` at startup, meaning the field is decorative. It will matter if rules_root is ever made configurable through the SettingsTab.

**Recommendation:** Either populate `rules_root` in `config/defaults.py` (matching what `core/config/defaults.py` intended), or remove the field from `AppConfig` and have `rules_loader.py` always derive the path from `data_root`.

---

## 5. Items Requiring Attention Before Active Development Resumes

### Priority 1 — Fix before next stage

| # | Issue | File | Line | Action |
|---|---|---|---|---|
| P1-1 | `File.version_id` typed `int` but nullable in DB | `core/model/file.py` | 11 | Change to `Optional[int]` |

### Priority 2 — Clean up to reduce confusion

| # | Issue | File | Action |
|---|---|---|---|
| P2-1 | Orphaned dead-code file | `core/config/defaults.py` | Delete |
| P2-2 | Orphaned dead-code file | `core/utils/logging.py` | Delete |
| P2-3 | Orphaned dead-code file | `core/utils/paths.py` | Delete or integrate |
| P2-4 | Unused imports `Any, Dict` | `core/sidecar/manager.py:6` | Remove `Any, Dict` |
| P2-5 | Unused import `Any` | `config/defaults.py:6` | Remove `Any` |
| P2-6 | Defensive `getattr` for guaranteed field | `ui/views/scan_tab.py:446` | Replace with direct attribute access |

### Priority 3 — Decide before implementing next stage

| # | Issue | Notes |
|---|---|---|
| P3-1 | `File` not frozen | Verify no mutation sites, then add `frozen=True` |
| P3-2 | `AppConfig.rules_root` always `""` | Decide: populate it from defaults, or remove the field |
| P3-3 | Preview/sidecar stubs in `AppContext` | Both are initialized at startup but do nothing; determine which stage implements them |
| P3-4 | Config file loading stub | `config/loader.py` — decide the format and trigger the implementation when needed |

---

## 6. Test Coverage Assessment

**Total tests:** 24 test files, 48+ test functions (all passing as of audit date)

### Well-covered areas
- DB operations: schema migrations, assets, versions, tags, version membership, file bindings, binding-triggered versioning
- Detection engine: locked files, partial texture-set updates, version parsing
- Storage: root registration, path resolution, unmanaged singleton
- Health checker: missing detection, targeted checks, discarded-version exemption
- Events: EventHub pub/sub, AppLog ring buffer
- UI smoke tests: import sanity, SettingsTab render

### Under-covered areas

| Gap | Risk |
|---|---|
| No end-to-end workflow tests (scan → detect → apply → health) | Medium — integration issues could be invisible |
| No test for `File` with `NULL version_id` | Medium — relates to P1-1 above |
| No test for config loading (always returns defaults) | Low — trivial code path |
| No test for `ensure_dir` or `get_logger` | N/A — these are dead code |
| No test for `SidecarManager` or `PreviewManager` | Low — stubs with no logic |
| Detection `apply.py` transaction rollback paths | Low — error paths not exercised |

---

## 7. Architecture Conformance Summary

The codebase conforms well to the architecture described in CLAUDE.md and the design documents.

**Doctrine adherence:**
- **Disk is authoritative** — scanner never writes to disk; detection is preview-only. Confirmed.
- **No-write policy** — no file renames, moves, or modifications anywhere in the codebase. Confirmed.
- **User intent outranks heuristics** — `file_bindings` table is checked before detection proposals; `locked` files are skipped by the engine (`engine.py`). Confirmed.
- **Power-user first** — no hand-holding dialogs; version numbering, tagging, and detection are all exposed directly. Confirmed.

**Composition root pattern** — `AppContext` correctly owns all long-lived services. UI never instantiates services. Initialization order matches the documented `Config → DB → Storage → Scanner → Health → Preview/Sidecar → Thread pool` sequence.

**Qt-free core** — all `core/` subsystems import zero Qt. UI and non-UI code is cleanly separated. Tests run without a display server.

**No major architectural violations found.**

---

*End of audit.*
