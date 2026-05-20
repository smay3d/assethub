# Two-Pass Scanner Design

**Date:** 2026-05-20
**Branch:** `raptor`
**Status:** Approved — ready for implementation

---

## Problem

File indexing and checksum computation currently happen in a single blocking pass inside
`Scanner.scan_all()`. For large directories or large files, SHA-256 hashing dominates scan
time — potentially minutes to hours. The Library tab does not refresh until the entire pass
completes, so the user cannot browse files or create assets while the dedupe process runs.

---

## Goal

Split the scanner into two stages so the user can browse indexed files and use all app
features immediately after Stage 1, with checksumming continuing silently in the background.

**Stage 1 — Index:** Walk storage roots, upsert file records (path, size, mtime). Fast.
**Stage 2 — Checksum:** Hash all files with `checksum IS NULL`. Silent, non-blocking.

---

## Approach

Approach A: two explicit methods on `Scanner`, orchestrated by `ScanTab`.

- `Scanner` stays Qt-free. No threading knowledge lives in core.
- `ScanTab` manages two independent job slots — one for scan/health (blocks UI as today),
  one for checksumming (fully silent, never disables any button).
- `scan_all()` is kept unchanged for single-pass callers (tests, future CLI).

---

## Design

### 1. Scanner — `core/scanner/scanner.py`

#### `scan_files_only(cancel_check=None) -> ScanResult`

Same `os.walk` loop as `scan_all()`. Checksum logic differs:

- **New or changed file** (no existing row, or `size_bytes`/`mtime_unix` differ from DB):
  upsert with `update_checksum=True, checksum=None`. Explicitly sets `checksum = NULL`,
  marking the file as pending checksumming.
- **Unchanged file**: upsert with `update_checksum=False`. Existing checksum is preserved.

Never calls `sha256_file()`. Touches disk only via `os.stat()`.

#### `compute_missing_checksums(cancel_check=None) -> ChecksumResult`

Batch re-query loop:

1. `SELECT id, storage_id, relative_path FROM file WHERE checksum IS NULL LIMIT 50`
2. If empty → done, return result.
3. For each row: resolve `storage_id → root_path` via `StorageManager`, build absolute path,
   call `sha256_file()`, `UPDATE file SET checksum=? WHERE id=?`.
4. Commit the batch.
5. Check cancel; if set, stop.
6. Go to step 1.

Re-querying each iteration (not fetching all IDs up front) gives natural "append" behavior:
files indexed by a concurrent Stage 1 appear in subsequent batches without any coordination.

OSError during hashing: log warning, increment `files_failed`, continue.

#### New dataclass

```python
@dataclass(frozen=True)
class ChecksumResult:
    files_checksummed: int
    files_failed: int      # files skipped due to OSError
    canceled: bool
```

#### `scan_all()` — unchanged

Kept as the single-pass method. Existing tests and any future CLI callers are unaffected.

---

### 2. ScanTab — `ui/views/scan_tab.py`

#### Two job slots

| Slot | Variable | Blocks UI? |
|---|---|---|
| Scan / Health | `_current_job` (existing) | Yes — buttons disabled as today |
| Checksum | `_current_checksum_job` (new) | No — all buttons remain enabled |

Each slot has its own cancel event: `_cancel_event` (existing) and `_checksum_cancel` (new).

#### Flow when "Scan Roots" is clicked

1. If `_current_job` is set → block (existing behavior, unchanged).
2. If `_current_checksum_job` is set → set `_checksum_cancel`. Do **not** wait. Proceed to
   step 3 immediately. SQLite `busy_timeout` handles any brief write overlap.
3. Run `_scan_job` in thread pool (calls `scanner.scan_files_only()` instead of `scan_all()`).
4. On finish → emit `DbChanged(reason="scan_index_updated")` → call `_start_checksum_job()`.

#### `_start_checksum_job()`

New private method. Sets `_current_checksum_job = "checksum"`, creates a fresh
`_checksum_cancel` event, dispatches `_checksum_job` as a `_CancelableWorker`.

#### `_checksum_job(cancel: Event) -> ChecksumResult`

Opens its own DB connection (same pattern as `_scan_job`). Sets `PRAGMA busy_timeout = 5000`.
Calls `scanner.compute_missing_checksums(cancel_check=cancel.is_set)`. Closes connection.

#### `_on_checksum_finished(result: ChecksumResult)`

Separate slot (not mixed with `_on_job_finished`). Clears `_current_checksum_job` and
`_checksum_cancel`. Emits `ChecksumFinished` and `DbChanged(reason="checksums_updated")`.

#### ESC / cancel behavior

`request_cancel_current_job()` is extended:
- If `_current_job` is set → cancel it (existing behavior).
- Else if `_current_checksum_job` is set → set `_checksum_cancel`.

ESC during Stage 2 stops checksumming without locking any UI.

#### Status label

| State | Text |
|---|---|
| Stage 1 running | `"Scanning: indexing files… (ESC to cancel)"` |
| Stage 1 done, Stage 2 starting | `"Indexing complete — computing checksums in background"` |
| Stage 2 done | `"Scan complete — checksums up to date"` |
| Stage 2 canceled by new scan | Stage 1 overwrites the label immediately |
| Stage 2 canceled by ESC | `"Checksum pass canceled"` |

No new UI widgets.

#### Write conflict mitigation

Both `_scan_job` and `_checksum_job` open their own DB connections. Both set
`PRAGMA busy_timeout = 5000` so SQLite serializes writes without raising errors. Stage 2
stops after its current file once canceled, keeping the overlap window short.

---

### 3. Events — `core/events/event_hub.py`

New event:

```python
@dataclass
class ChecksumFinished:
    summary: dict  # keys: files_checksummed, files_failed, canceled
```

`ScanTab` emits it when Stage 2 completes or is canceled.
`DuplicatesView` connects to it to trigger a refresh (same pattern as `ScanFinished` today).

---

### 4. Testing — `tests/test_scanner_two_pass.py`

New file, core-layer only (no Qt):

- `scan_files_only` indexes files and leaves all `checksum IS NULL`
- `scan_files_only` preserves existing checksums for unchanged files
- `scan_files_only` NULLs out checksum when size or mtime changes
- `compute_missing_checksums` hashes all NULL-checksum files and updates DB
- `compute_missing_checksums` picks up files added between batches (batch re-query behavior)
- `compute_missing_checksums` stops cleanly when cancel is set mid-batch
- `compute_missing_checksums` skips unreadable files and increments `files_failed`
- `scan_files_only` + `compute_missing_checksums` produces the same DB state as `scan_all()`
  (regression guard)

Existing `test_scanner_checksum.py` stays green — `scan_all()` is untouched.

ScanTab orchestration (two-slot coordination, cancel handoff between stages) is deferred to
a future integration test pass.

---

## Out of Scope

- Progress reporting within Stage 2 (file count / percentage) — deferred
- Persisting checksum queue across app restarts — the DB is the queue; any NULL checksums
  present at next launch are processed on next scan
- Parallel checksumming (multiple worker threads) — deferred
