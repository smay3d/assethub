---
name: raptor-session-end
description: >
  Wrap up an AssetRaptor development session. Use this skill at the end of every working
  session on the Raptor project — when the user says things like "let's wrap up", "end the
  session", "commit everything", "time to stop", or "run session-end". This skill verifies
  tests pass, updates the three core documentation files (Changelog, Architecture, Status),
  commits all changes, and pushes to the current branch. It is the last thing that runs
  before closing Claude Code. Never skip it — the Status doc is what makes the next session
  possible without re-explaining context.
---

# Session End

Wrap up the current AssetRaptor development session. The point of this skill is twofold:
keep the docs current so future-Claude can orient without context from this conversation,
and ensure no in-progress work is left untracked or uncommitted.

Work through these steps in order. Don't skip steps or reorder them.

## Step 1: Verify tests pass

```bash
pytest
```

If any tests fail, **stop here**. Tell the user which tests failed and why before doing
anything else. Do not update docs or commit until the test suite is green. A failing test
suite means the session isn't actually done yet.

## Step 2: Understand what changed this session

```bash
git diff HEAD
git status
```

Read the diff carefully. You're about to write doc entries that explain these changes to a
future reader — understanding *why* the changes happened matters as much as *what* changed.
If the diff is large, note which subsystems were touched (DB, UI, scanner, etc.) and whether
any structural changes were made (new modules, schema bumps, new services in AppContext).

## Step 3: Update `docs/raptor/Raptor_Changelog.md`

Add an entry under `## [Unreleased]`. Only include changes that a future developer (or
future Claude) would care about — features added, bugs fixed, significant refactors.
Skip trivial changes like typo fixes, comment cleanup, or reformatting.

Use this format. Only include subsections that have content:

```markdown
### <Short present-tense description> (YYYY-MM-DD)

#### Added
- <new capability>

#### Changed
- <modified behavior>

#### Fixed
- <bug resolved>

#### Removed
- <thing deleted>
```

## Step 4: Update `docs/raptor/Raptor_Architecture.md` (conditional)

Only update this file if the session produced **structural changes** — new subsystems,
new modules added to `core/` or `ui/`, DB schema version bumps, changes to the AppContext
initialization order or service ownership. 

Skip this step for UI-only changes, bug fixes, or feature additions that work entirely
within existing modules. The architecture doc should reflect *how the system is built*,
not everything that was done.

If you do update it, change only the sections that are now inaccurate. Update the
"Last updated" date at the top.

## Step 5: Update `docs/raptor/Raptor_Status.md`

This is the most important doc update — it's what the next session reads to orient.
Make it accurate and specific, not generic.

Update these sections:

**Milestone Tracker:** Mark any features completed this session as `Complete`. If a
feature moved from "Not started" to "In progress", update that too.

**Current Work:** Replace with what is now in-flight, if anything. If the session
reached a clean stopping point, note that.

**Last Session Summary:** Overwrite this section entirely. Write:
- What was accomplished (specific, not vague — name files and features)
- What is in progress and where it was left off
- What to do at the start of the next session

**Open Items:** Remove items resolved this session. Add any new items discovered
(bugs found, decisions needed, debt incurred). Keep priorities accurate.

## Step 6: Commit and push

Stage all changed files and commit:

```bash
git add docs/raptor/Raptor_Changelog.md
git add docs/raptor/Raptor_Status.md
# add Architecture.md only if it was updated
git add docs/raptor/Raptor_Architecture.md
# add any source files that were modified this session
git add <modified source files>
git commit -m "docs: update session records after <brief description of session work>"
git push
```

If source file changes weren't committed during the session (they should be, but
sometimes the last few changes aren't), commit them as part of this step with a
separate conventional commit before the docs commit.

## Step 7: Suggest next action

Close with a single concrete recommendation for what to do at the start of the next session.
This should match what you wrote in the "Last Session Summary → what to do next" in Status.md.

If the session completed a feature branch, suggest opening a PR:
```bash
gh pr create --base raptor --title "<feature title>" --body "<summary>"
```
