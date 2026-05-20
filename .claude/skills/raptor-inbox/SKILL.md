---
name: raptor-inbox
description: >
  Log a discovered issue or observation to the Raptor issue inbox. Use this skill whenever
  the user reports a bug, unexpected behavior, UI oddity, or any informal observation while
  using or testing AssetRaptor — including phrases like "I noticed...", "this seems off",
  "issue:", "bug:", "something's wrong with...", or any problem report. Also triggers on
  explicit /raptor-inbox invocations. The inbox is intentionally lightweight — no triage,
  no priority, just a timestamped log entry. Get it captured and out of the way so the user
  can keep working.
---

# Raptor Inbox

The inbox captures raw observations from app use — things the user notices while testing or
working in AssetRaptor that shouldn't interrupt their flow but shouldn't be forgotten either.

**Inbox file:** `docs/raptor/Raptor_Inbox.md`
**Triage happens at:** session-end, when inbox items are promoted to Open Items or GitHub Issues

---

## How to log an entry

The goal is fast and frictionless. The user is in the middle of testing something; a quick
capture and confirmation is all they need.

### 1. Extract area and description

From the user's message, identify:

- **Area** — the subsystem or UI region involved. Common values: `scanner`, `ui`, `db`,
  `duplicates-view`, `library-tab`, `ingest`, `search`, `general`. If the area isn't obvious,
  pick the closest match and move on — don't ask.
- **Description** — one sentence describing the observed behavior, not the cause. Write what
  was seen, not why it might be happening.

### 2. Ensure the inbox file exists

Check for `docs/raptor/Raptor_Inbox.md`. If it doesn't exist, create it with this header:

```markdown
# Raptor Inbox

Observations logged during app use. Not verified, not prioritized.
Reviewed at session-end — items are promoted to Open Items or GitHub Issues as warranted.

| Timestamp | Area | Observation |
|---|---|---|
```

### 3. Append the entry

Add a row to the table:

```
| YYYY-MM-DD HH:MM | <area> | <one-sentence description> |
```

Use the current date and time (24-hour). Granularity matters — a fix could land within the same day.
Keep the description factual and concise — what was observed, not a diagnosis.

**Examples:**
```
| 2026-05-20 14:32 | duplicates-view | Copy path(s) button copies only the first selected row when multiple are selected |
| 2026-05-20 09:15 | scanner | Progress bar does not update during checksum phase on large directories |
| 2026-05-20 17:44 | library-tab | Column sort order resets after switching between view modes |
```

### 4. Confirm

Reply with one line, then an optional second line:

**Line 1 (always):** `Logged: <area> — <description>`

**Line 2 (only if you already have relevant context):** `(Have context on this — ask me to investigate when ready.)`

The second line is appropriate when you recognized the symptom as something familiar, saw the likely cause while reading the user's description, or have already analyzed the relevant code this session. Omit it if you're working from the user's description alone with no prior knowledge of the affected area. The user is testing and doesn't need a diagnosis — but a brief signal that you have context is useful so they know to ask later.
