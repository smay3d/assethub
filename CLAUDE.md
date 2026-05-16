# CLAUDE_raptor.md

Guidance for Claude Code when working on the **AssetRaptor** project (formerly AssetHub).
This file is the primary orientation document for every session. Each section links to deeper
documentation where applicable.

> **Note:** This file becomes `CLAUDE.md` when the Raptor reboot is the active codebase.
> Until then it lives alongside the legacy `CLAUDE.md` for reference during the transition.

---

## 1. Project Goals

AssetRaptor ("Raptor") is a single-user Windows desktop application for 3D artists and Pipeline
TDs to catalog, organize, and track pipeline assets and their associated files — without modifying
anything on disk.

**The problem it solves:** Tools like Eagle Asset Manager track individual files but have no
concept of a multi-file asset. A PBR texture set is 6+ image files. A 3D model is regularly
versioned. An image sequence is hundreds of files in order. Raptor tracks the relationships between
files, assets, and versions so an artist always knows what belongs to what, and at which version.

**Target user:** Solo 3D artist or small team lead — power users, not mass-market.
**Platform:** Windows desktop.
**Distribution:** Standalone `.exe` (PyInstaller).
**Current milestone:** MVP — see `docs/raptor/Raptor_ProjectSpec.md` for full milestone scope.

---

## 2. Architecture Overview

**Stack:** Python 3.x · PySide6 · SQLite
**Pattern:** Single-user desktop, composition root architecture.

### Composition Root: `AppContext` (`src/assethub/context.py`)

All long-lived services are owned by `AppContext`. The UI never instantiates services directly.

**Initialization order:**
```
Config → DB → StorageManager → Scanner → HealthChecker → EventHub → UI
```

**Critical doctrine: `core/` imports zero Qt.** All PySide6 code lives in `ui/`. Tests run
without a display server. Any edit that imports Qt into `core/` is an architectural violation.

**Core subsystems** (`src/assethub/core/`): `db/` · `storage/` · `scanner/` · `health/` ·
`detection/` · `events/` · `model/` · `utils/`

→ Full layout, subsystem details, DB schema: `docs/raptor/Raptor_Architecture.md`

### Documentation System

**At the start of every session, read `Raptor_Status.md`** (handled by `raptor-session-start`).

**Auto-update loop** — maintained by `raptor-session-end` at the end of every session:

| Document | Purpose |
|---|---|
| `docs/raptor/Raptor_Status.md` | Current progress, in-progress work, last session summary |
| `docs/raptor/Raptor_Changelog.md` | Notable changes over time |
| `docs/raptor/Raptor_Architecture.md` | System design, layout, DB schema *(updated only if structural changes occurred)* |

**Contract documents** — updated only when deliberate decisions are made, not by session-end:

| Document | Purpose | Update when |
|---|---|---|
| `docs/raptor/Raptor_ProjectSpec.md` | Product + engineering requirements | Requirements or scope change |
| `CLAUDE_raptor.md` | Claude Code orientation and workflow rules | Workflow or project-wide decisions change |

---

## 3. Design Style Guide

**Tech stack (locked):** Python 3.x · PySide6 · SQLite · pytest

**UI framework patterns:**
- All table interfaces use Qt Model/View: `QAbstractTableModel` + `QSortFilterProxyModel`.
  Never use `QTableWidget` for data-driven tables.
- Theme and styling live in `ui/style/qss.py`. Do not apply colors, fonts, or spacing inline
  in widget code — use the QSS system.
- Background operations run on a `QThreadPool` worker, never the UI thread. Pass a
  `threading.Event` as `cancel_check` to all long-running operations.

**Visual style:** Not yet defined. Until the style guide is written, follow the existing theme
engine patterns and avoid hardcoded colors or fonts outside of `ui/style/qss.py`.

→ Visual style guide (placeholder): `docs/raptor/Raptor_StyleGuide.md`

---

## 4. Product & UX Guidelines

These are invariants, not preferences. Code that violates them is architecturally wrong.

| Doctrine | Rule |
|---|---|
| **Disk is authoritative** | The filesystem is always ground truth. The DB is a derived index. Never treat DB state as more correct than what is on disk. |
| **No-write policy** | Raptor never renames, moves, or modifies user files. No exceptions in v0–v1. |
| **User intent outranks heuristics** | Manual user actions are durable and authoritative. Automated detection never overwrites them. |
| **Explainability over magic** | The system must always be able to answer *why* something happened. No silent side effects. |
| **Power-user first** | Expert workflows are prioritized. Do not add confirmations, tooltips, or beginner UX unless explicitly requested. |

---

## 5. Constraints & Policies

### Explicit Non-Goals — Do Not Implement

- **Sidecar JSON system** — removed from scope entirely. `core/sidecar/` is to be deleted.
- Multi-user permissions or collaboration workflows
- Cloud sync of any kind
- AI-driven tagging or file inference (future consideration only — do not design for it now)

### Code Quality Rules

- **TDD is required.** Invoke `superpowers:test-driven-development` before writing implementation
  code for any feature or fix. Tests are written first.
- No dead code. No orphaned files. No unused imports. Remove them when found.
- No speculative abstractions. Build only what the current task requires.
- No new external dependencies without explicit discussion and agreement.
- `pytest` must be green before any commit. Never commit with failing tests.

### Validation Boundaries

Validate at system boundaries only (user input, file I/O). Trust internal code and framework
guarantees. Do not add defensive checks for conditions that cannot occur.

---

## 6. Development Workflow & Skills

### Skill Usage Reference

| Situation | Invoke |
|---|---|
| Starting a session | `raptor-session-start` |
| New feature or significant behavior change | `superpowers:brainstorming` → `superpowers:writing-plans` |
| Any implementation work (feature or fix) | `superpowers:test-driven-development` |
| Any bug or unexpected behavior | `superpowers:systematic-debugging` |
| Before claiming work is complete | `superpowers:verification-before-completion` |
| Before merging a feature branch | `superpowers:requesting-code-review` |
| Guided feature implementation | `feature-dev:feature-dev` |
| Ending a session | `raptor-session-end` |

### Feature Development Loop

1. Open a GitHub Issue describing the task
2. Create a feature branch: `git checkout -b feature/<short-name>`
3. Brainstorm → plan → implement (TDD) → verify
4. Open a PR: `feature/<name>` → `raptor`
5. Review and merge; delete the feature branch
6. Run `raptor-session-end` to update docs and commit

### When to Skip the Full Loop

Small, self-contained fixes (single-file corrections, removing dead code, fixing a typo) may be
committed directly to `raptor` without a feature branch. If in doubt, use a branch.

---

## 7. Repository Etiquette

**Active development branch:** `raptor`
**Stable/release branch:** `main` (Raptor merges to `main` at milestone completions via PR)

### Branch Naming

| Type | Format | Example |
|---|---|---|
| New feature | `feature/<short-name>` | `feature/library-tab-rewrite` |
| Bug fix | `fix/<short-name>` | `fix/null-version-id-crash` |
| Maintenance / chore | `chore/<short-name>` | `chore/delete-sidecar-stubs` |

### Commit Message Format

Use conventional commits. Prefix with type, followed by a concise imperative description.

```
feat: add duplicate file detection to scanner
fix: correct null version_id type in File model
chore: remove core/sidecar dead code
docs: update architecture doc after scanner refactor
```

### Rules

- Never commit feature work directly to `raptor` — always use a feature branch and PR.
- All tests must pass before opening a PR.
- Always run `raptor-session-end` before closing Claude Code for the day.
- Do not force-push to `raptor` or `main`.

---

## 8. Commands

```bash
# Run the app
python main.py

# Run all tests
pytest

# Run a single test file
pytest tests/test_db_assets.py

# Run a specific test function
pytest tests/test_db_assets.py::test_function_name

# Build standalone .exe  (requires /raptor-build skill — not yet configured)
# See docs/raptor/Raptor_BuildGuide.md when available
```

No build step. No `requirements.txt` at root. `src/` is on the path via `conftest.py` and
`main.py`.
