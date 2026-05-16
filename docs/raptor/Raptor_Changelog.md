# Raptor Changelog

All notable changes to AssetRaptor are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

Versions:
- **Unreleased** — active development, not yet at a named milestone
- **MVP** — file ingest, manual assignment, search/filter/sort, duplicate detection
- **Beta** — auto asset detection, asset version tracking
- **v1.0** — auto project detection, smart folders

---

## [Unreleased]

### Workflow and tooling setup (2026-05-13)

#### Added
- `CLAUDE_raptor.md` — Claude Code orientation doc covering project goals, architecture,
  UX doctrines, constraints, skill usage, repo etiquette, and commands
- `docs/raptor/` directory with five core project documents:
  `Raptor_Architecture.md`, `Raptor_Changelog.md`, `Raptor_Status.md`,
  `Raptor_ProjectSpec.md` (v1.0 with full product and engineering requirements)
- `.claude/skills/raptor-session-start/` — skill to orient Claude at session start
- `.claude/skills/raptor-session-end/` — skill to update docs, commit, and push at session end

#### Changed
- Legacy root-level design docs moved to `docs/ARCHIVE/`

---

### Project Reboot (2026-05-13)

AssetHub prototype (Stages 5–9.4, ChatGPT workflow) rebooted as **AssetRaptor** under a
new Claude Code workflow. Decision summary:

- **Kept:** Full `core/` backend (DB, scanner, health, detection, events, models, storage)
- **Rewriting:** `ui/` from scratch in PySide6 with intentional visual design
- **Removed from scope:** Sidecar JSON system
- **New workflow:** Skill-driven iterative development with GitHub Issues + feature branches
- **New docs:** `CLAUDE_raptor.md`, `Raptor_Architecture.md`, `Raptor_Changelog.md`,
  `Raptor_Status.md` (this file)

### Known debt carried forward from prototype (from Audit v1.0)

- `File.version_id` typed `int` but nullable in DB — fix before next feature (P1)
- Dead code to delete: `core/config/defaults.py`, `core/utils/logging.py`,
  `core/utils/paths.py`, `core/sidecar/` (P2)
- `File` model not frozen — verify no mutation sites, then add `frozen=True` (P3)
- `AppConfig.rules_root` always `""` at startup — decide: populate or remove (P3)

---

*Entries above this line are added automatically by `raptor-session-end`.*
*Format per entry: `### Description (YYYY-MM-DD)` with Added / Changed / Fixed / Removed subsections.*
