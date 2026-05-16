---
name: raptor-session-start
description: >
  Orient Claude at the start of an AssetRaptor development session. Use this skill
  at the beginning of every working session on the Raptor project — when the user says
  things like "let's work on raptor", "starting a session", "picking up where we left off",
  "what were we doing?", or opens Claude Code on this project. This skill reads the current
  project status, checks git state, and surfaces open work so both Claude and the user can
  pick up immediately without re-explaining context from the previous session.
---

# Session Start

Orient to the current state of the AssetRaptor project at the top of a session.

The goal is to get the user working in under 60 seconds. Read, synthesize, brief — don't ask
clarifying questions before doing these steps.

## Steps

### 1. Read project status

Read `docs/raptor/Raptor_Status.md` in full. This is the session handoff document — it
tells you what was in progress, what was completed last session, and what to do next.
Trust it as your primary source of truth for project state.

### 2. Check git state

Run these two commands and note the results:

```bash
git branch --show-current
git status --short
```

If there are uncommitted changes, flag them — they're almost certainly work in progress
from the last session that didn't get committed. Note the branch name; it tells you whether
you're on `raptor` (general dev) or a feature branch (specific work in progress).

### 3. Check open GitHub Issues (if available)

```bash
gh issue list --state open --limit 10 --assignee @me
```

If `gh` is not installed or not authenticated, skip this step silently — don't mention it
to the user.

### 4. Deliver the session briefing

Output a concise briefing using this structure. Keep each section to 1–3 lines. If
something has nothing to report, omit it entirely rather than writing "none."

---
**Branch:** `<branch-name>`

**Last session:** <one sentence summary of what was accomplished>

**In progress:** <what was being worked on when the session ended, if anything>

**Uncommitted changes:** <files with changes, if any — otherwise omit>

**Open issues:** <top 2–3 issue titles and numbers, if available>

**Suggested start:** <one concrete action to take right now>
---

The "suggested start" is the most important line. Make it specific: not "continue working on
the UI" but "continue the LibraryTab rewrite — `ui/views/library_tab.py` was in progress."
