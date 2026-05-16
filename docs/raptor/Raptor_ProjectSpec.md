# Raptor Project Spec

**Version:** 1.0
**Date:** 2026-05-13
**Status:** Active — authoritative source of truth for product and engineering requirements.

This document supersedes the AssetHub prototype's Design Summary (`AssetHub_DesignSummary_v1.9.md`).
Update this document when requirements change; link to it from `CLAUDE_raptor.md`.

---

## Part 1: Product Requirements

### 1.1 Product Identity

**Name:** AssetRaptor ("Raptor")
**Type:** Single-user desktop application
**Platform:** Windows
**Distribution:** Standalone `.exe` (PyInstaller) — no installer required for beta

### 1.2 Target Users

**Primary:** Solo 3D artist (hobbyist or professional VFX/game artist)
**Secondary:** Small team lead managing a personal pipeline asset library

**User profile:** Power user. Comfortable with pipeline concepts — assets, versions, texture
maps, render sequences, storage roots. Not mass-market. Raptor does not hand-hold.

### 1.3 Problem Statement

Tools like Eagle Asset Manager track individual files but have no concept of a multi-file
asset. This breaks down for:

- **Texture sets** — a PBR material is 6+ image files (albedo, roughness, normal, metallic,
  height, AO). Eagle shows each file in isolation with no way to see the set.
- **Versioned 3D models** — a model is regularly versioned up; previous versions must be
  retained. No tracking = no reliable rollback.
- **Image sequences** — a render is hundreds of sequentially-named files. No grouping = no
  coherent view of the sequence as a single asset.

Raptor tracks file → asset → version relationships so an artist always knows what files
belong to what asset, at which version, and what state each file is in on disk.

### 1.4 Usage Goals

These are the specific outcomes Raptor exists to enable. Features must serve at least one
of these goals.

1. **"Why is my material missing a texture map?"** — An artist should be able to see at a
   glance which files belong to a texture asset and which are missing from disk.

2. **"What version of my model is in production?"** — Asset versioning with snapshot history
   lets an artist pin a version and track its file membership over time.

3. **"Where did I put that render sequence?"** — A single library view across all storage
   roots eliminates manual folder hunting for multi-location assets.

4. **"Are these two files the same?"** — A core goal is that Raptor identifies files by
   content (checksum), not solely by filename or path. This enables duplicate detection,
   move/rename detection, and content-addressable file identity independent of filesystem
   organization. An artist should be able to find and eliminate duplicate files to reclaim
   disk space without relying on filenames alone.

5. **"What is this file, even without its name?"** — Long term, checksums enable Raptor to
   re-identify a file even if it has been renamed or its extension has changed.

### 1.5 Feature Scope

#### MVP

The following features constitute the MVP. Items marked (carried) use backend code from the
AssetHub prototype; their UI is being rewritten from scratch.

| Feature | Status | Notes |
|---|---|---|
| File ingest + disk tracking | Carried — UI rewrite | Scan, upsert, health check (OK/MISSING/UNRESOLVED) |
| Storage root management | Carried — UI rewrite | Register, rename, remove roots; Unmanaged singleton |
| Manual file → asset assignment | Carried — UI rewrite | Bindings survive re-scan; outrank detection |
| Asset + version management | Carried — UI rewrite | Create, label, discard, restore versions; snapshot carry-forward |
| Asset-level tagging | Carried — UI rewrite | Colored tags, bulk add/remove, tag manager |
| File + asset library browser | Carried — UI rewrite | Files mode + Assets mode; search, sort, column filters |
| Notion-like filter rules | Not started | Rule blocks: field / operator / value (see §1.6) |
| File type attribute + filter | Not started | File type column; filterable in library |
| Duplicate file detection | Not started | See §1.6 |
| UI rewrite (PySide6) | Not started | Full visual redesign; style TBD |

#### Beta

| Feature | Status | Notes |
|---|---|---|
| Automatic asset detection | Carried — UI rewrite | Rules-based, proposal-only, user applies |
| Asset version tracking UI | Carried — UI rewrite | Version list, file membership per version |
| Preview thumbnails | Not started | Image formats at minimum; scope TBD in style guide |
| Force-unbind detection-bound files | Not started | User can unbind any file, not just manually-bound ones |
| Re-detect on file binding | Not started | Run detection when user manually attaches a file |
| Detect assets dialog: version-up indicator | Not started | Clear UI signal when merging to existing asset vs. creating new |
| Detect assets dialog: supporting files | Not started | Add non-detected files to proposal within same directory |
| Detection filetype exclusion filter | Not started | User-editable list of excluded extensions (default: .tx, .rat) |

#### v1.0

| Feature | Status | Notes |
|---|---|---|
| Project detection (scanner) | Not started | Ingest project files (.mel, .hip, .ma, etc.); mark dirs as projects |
| Project detection (assets) | Not started | Asset proposals use project context for naming/grouping |
| Smart folders | Not started | Dynamic collections based on saved filter rules |

#### Future / Under Consideration

| Feature | Notes |
|---|---|
| Expand asset detection variety | Additional grouping heuristics beyond texture sets and sequences |
| Expanded preview format support | Non-image formats (video, 3D, etc.) |
| Filesystem watchdog | Replace manual scan trigger with automatic change detection |
| Mark version as latest | UI indicator for pinned/latest version when labels are renamed |
| Multi-dissolve assets | Dissolve multiple assets in one operation |

#### Out of Scope (do not implement)

- Sidecar JSON system — removed from scope
- Multi-user permissions or collaboration
- Cloud sync of any kind
- AI-driven tagging or file inference
- Modifying, renaming, or moving user files on disk (no-write policy)

### 1.6 Feature Detail: Key MVP Features

#### Duplicate File Detection

Raptor identifies duplicates by content, not filename.

- **Checksum-based:** SHA-256 hash match across any two indexed files = same content,
  regardless of filename, extension, or location. Flagged as a content duplicate.
- **Name-based:** Same filename found in two or more locations across registered roots.
  Flagged as a name collision (may or may not be the same content).
- **Scope:** Scans across all registered storage roots.
- **UI:** Both duplicate types are flagged and visually distinguished. User decides which
  copy to keep; Raptor does not delete files.
- **Secondary benefit:** Checksums enable Raptor to detect when a file has been moved or
  renamed (same hash, different path) rather than treating it as deleted + new.

#### Notion-like Filter Rules

The library browser supports structured filter rules in addition to basic text search.

Each rule block specifies:
1. **Field:** `file name` / `file type` / `integrity state` / `tag` / (expandable)
2. **Operator:** `contains` / `is` / `is not`
3. **Value:** string, file type token, integrity state enum, or tag name

Multiple rule blocks combine as AND conditions. Rules persist within the session.

---

## Part 2: Engineering Requirements

### 2.1 Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.x | No version below 3.10 |
| UI | PySide6 (Qt6) | Retained from prototype; visual redesign only |
| Database | SQLite (stdlib `sqlite3`) | Schema v7 baseline; migrations required for changes |
| Testing | pytest | All tests must pass before any commit |
| Distribution | PyInstaller | Standalone `.exe`; no installer for beta |

No new external dependencies without explicit approval.

### 2.2 Architecture

Raptor uses a composition root architecture. All long-lived services are owned by
`AppContext` and accessed by UI through it. The UI never instantiates services directly.

**`core/` is strictly Qt-free.** Tests run headless. Any Qt import in `core/` is a
violation.

Initialization order: `Config → DB → StorageManager → Scanner → HealthChecker → EventHub → UI`

→ Full architecture, subsystem map, DB schema: `docs/raptor/Raptor_Architecture.md`

### 2.3 Core Design Invariants

These are non-negotiable. Code that violates them is wrong.

| Invariant | Rule |
|---|---|
| **Disk is authoritative** | The filesystem is always ground truth. The DB is a derived index. |
| **No-write policy** | Raptor never renames, moves, or modifies user files. |
| **User intent outranks heuristics** | Manual bindings are durable. Detection never overwrites them. |
| **Explainability over magic** | The system must always be able to say why something happened. |
| **Power-user first** | Expert workflows are prioritized. No hand-holding UX. |

### 2.4 Quality Requirements

- **TDD required** — tests are written before implementation code for all features and fixes
- `pytest` must be green before any commit
- No dead code, orphaned files, or unused imports
- No speculative abstractions — build only what the current task requires
- No defensive checks for conditions that cannot occur; validate at system boundaries only

### 2.5 Performance Requirements

| Scenario | Target |
|---|---|
| Normal library (up to 10,000 files) | UI responsive at all times; no perceived lag in browse/filter |
| Large library (up to 50,000 files, e.g. render sequences) | Scan completes in under 60 seconds on typical workstation hardware |
| Background operations | Always cancellable via `threading.Event`; never block the UI thread |
| Startup | App ready for interaction in under 5 seconds on target hardware |

### 2.6 Known Debt Carried from Prototype

These issues were identified in Audit v1.0 and must be resolved during the Raptor reboot.

| Priority | Issue | Location |
|---|---|---|
| P1 | `File.version_id` typed `int` but nullable in DB | `core/model/file.py:11` |
| P2 | Dead code: `core/config/defaults.py` | Delete |
| P2 | Dead code: `core/utils/logging.py` | Delete |
| P2 | Dead code: `core/utils/paths.py` | Delete |
| P2 | Dead code: `core/sidecar/` | Delete (feature removed from scope) |
| P3 | `File` model not frozen | Verify no mutation sites, add `frozen=True` |
| P3 | `AppConfig.rules_root` always `""` at startup | Populate from defaults or remove field |

**Known open bugs from prototype testing:**

| Bug | Notes |
|---|---|
| Foreign key error on unregister root | Cascade delete failing with `sqlite3.IntegrityError` |
| File duplication in detect assets UI after file move | Checksum-based move detection will resolve this |
| Re-added file missing from detect assets dialog | File removed, scanned, re-added, re-scanned — does not appear in detection proposals |
