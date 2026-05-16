# Raptor Status

**Last updated:** 2026-05-13
**Active branch:** `raptor`
**Current milestone:** Pre-MVP — project reboot and workflow setup

---

## Milestone Tracker

### MVP
File ingest + disk tracking · Manual file → asset assignment · Search, filter, sort · Duplicate detection

| Feature | Status | Notes |
|---|---|---|
| File ingest + disk tracking | Carried over (complete) | Core backend retained from prototype |
| Manual file → asset assignment | Carried over (complete) | Backend retained; UI to be rewritten |
| Search, filter, sort | Carried over (complete) | Backend retained; UI to be rewritten |
| Duplicate file detection | Not started | New feature for Raptor |
| UI rewrite (PySide6) | Not started | Replacing prototype UI from scratch |
| `.exe` distribution (PyInstaller) | Not started | Required before any beta testing |

### Beta
Auto asset detection · Asset version tracking

| Feature | Status | Notes |
|---|---|---|
| Auto asset detection | Carried over (complete) | Backend retained; UI to be rewritten |
| Asset version tracking | Carried over (complete) | Backend retained; UI to be rewritten |

### v1.0
Auto project detection · Smart folders

| Feature | Status | Notes |
|---|---|---|
| Auto project detection | Not started | |
| Smart folders | Not started | |

---

## Current Work

**Phase:** Ready for implementation — workflow and tooling setup complete.

**Next action:** Install `raptor-session-start` and `raptor-session-end` as a local plugin,
then begin the first implementation work: P1/P2 audit debt cleanup (see Open Items).

---

## Last Session Summary

**Date:** 2026-05-13
**Session type:** Planning / design — Raptor reboot session 1

Completed:
- Decided core approach: keep `core/` backend, rewrite `ui/` from scratch, stay on PySide6
- Decided workflow: skill-driven iterative + GitHub Issues + feature branches on `raptor` branch
- Wrote `CLAUDE_raptor.md` — Claude Code orientation and workflow rules
- Created `docs/raptor/` with five core documents: Architecture, Changelog, Status,
  ProjectSpec (v1.0, full product + engineering requirements), and brainstorm notes archived
- Wrote `raptor-session-start` and `raptor-session-end` skills in `.claude/skills/`
- Removed sidecar system from scope; confirmed tags as MVP; set scale target at 10k files
- Moved legacy root-level design docs to `docs/ARCHIVE/`

Next session should start with:
- Install skills as a local plugin so they're invocable via the Skill tool
- Open GitHub Issues for the P1/P2 audit debt items (see Open Items #1–3)
- Begin chore branch: delete dead code and fix `File.version_id` type

---

## Open Items

| # | Item | Priority | Notes |
|---|---|---|---|
| 1 | Fix `File.version_id: int` → `Optional[int]` | P1 | Audit finding; fix before next feature |
| 2 | Delete dead code: `core/config/defaults.py`, `core/utils/logging.py`, `core/utils/paths.py`, `core/sidecar/` | P2 | Audit findings; sidecar removed from scope |
| 3 | Decide `AppConfig.rules_root` handling | P3 | Populate from defaults or remove the field |
| 4 | Install skills as local plugin | High | Makes `raptor-session-start/end` invocable via Skill tool |
| 5 | Design UI visual style | Medium | Deferred to UI design stage; stub at `docs/raptor/Raptor_StyleGuide.md` |
| 6 | Write `raptor-build` skill | Low | Needed before first beta distribution |
