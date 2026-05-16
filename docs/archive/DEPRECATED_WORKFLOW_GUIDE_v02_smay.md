**WARNING: This document is deprecated as of the AssetHub project reboot (now Raptor) on 5/12/2026. Use this document only for reference on the way the original prototype was designed and iterated on, not a guide on iteration for the project reboot.**

# AssetHub Workflow Guide — Stage Execution (Chat → Plan → Code → Verify)

This guide captures the workflow we’ve been using successfully in this project. Use it as the default process for future stages/sub-stages to keep scope tight, avoid drift, and maintain steady progress.

---

## Core Loop (per sub-stage)

1) **Outline the next sub-stage in chat**
   - Define the goal in “ship terms” (what becomes possible for the user).
   - Declare in-scope vs out-of-scope items.
   - Identify dependencies on prior stages.

2) **Discuss and refine the outline**
   - Resolve open questions early.
   - Set sensible defaults when decisions aren’t critical.
   - Identify UX risks, performance concerns, or schema constraints.

3) **Finalize and export the plan as an in-chat Markdown text message**
   - Assistant may reference previous sub-stage documents in the repo docs/ARCHIVE.
   - Print the markdown text in a chat message code blurb.
   - Include: deliverables, wiring/data flow, files to add/modify, tests, and Definition of Done.

4) **Upload the latest repo zip (including the stage plan doc)**
   - This repo is the single source of truth for implementation.
   - The uploaded plan doc anchors expectations and reduces ambiguity.

5) **Receive code as “changed/new files only”**
   - Assistant returns a zip containing only modified and new files.
   - User copies files into their local repo (preserving folder structure).

6) **Verify locally**
   - **Human test:** validate the feature in the UI and attempt to break it.
   - **Pytest:** run the full test suite and confirm results are clean.

7) **Micro-edit loop (when needed)**
   - If tweaks are required:
     - User uploads the **exact current file(s)** from their repo.
     - Assistant returns **drop-in replacements** for those specific files.
   - Repeat until the sub-stage meets the Definition of Done.

8) **Conclude the sub-stage**
   - Confirm Definition of Done is achieved (or the feature is stable enough to proceed).
   - User commits and pushes to `dev` (and tags milestone versions when appropriate).

9) **Repeat steps 1–8**
   - Continue until the parent stage is complete.
   - Optionally merge `dev → main` at a stable milestone (stage end).

---

## What each Stage Plan should include

- **Goal**
- **Deliverables**
- **In-scope / Out-of-scope**
- **UI elements**
- **Data flow / wiring**
- **Threading and performance notes**
- **Files to add/modify**
- **Testing plan**
- **Definition of Done**

---

## Practical defaults we’ve used

- Prefer shipping a working v0.1 quickly and iterating.
- Use read-only UIs first, then add editing features later.
- Use Model/View (`QAbstractTableModel` + proxy) for tables.
- Keep large operations off the UI thread.
- Treat warnings as “fix soon” when the fix is small and low-risk.

---

## Artifact naming conventions

- Stage plans: `AssetHub_StageX_Y_<Topic>_Plan_v0.1.md`
- Patch zips: `AssetHub_stageX_Y_files.zip` or `..._patch.zip`
- When applicable, keep a short entry in `AssetHub_DevLog.md` at stage completion.
