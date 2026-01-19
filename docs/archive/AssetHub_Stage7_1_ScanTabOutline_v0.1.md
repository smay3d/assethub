# AssetHub — Stage 7.1 Scan Tab v0.1 Implementation Plan

## Goal
Implement a functional **Scan** tab that can:

- Register and persist storage roots
- Scan registered roots into the `file` table
- Run a health check across all indexed files
- Provide basic status + summary output
- Support **press ESC to cancel** without freezing the UI

---

## UI Elements (Scan Tab)

### Storage Roots Panel
- Table/list of registered roots (columns):
  - Name/label (if available)
  - Root path
  - Type/flag (e.g., normal vs Unmanaged)
- Buttons:
  - **Add Root…** (directory picker)
  - **Remove Root** (removes selected root, with safety checks)

### Actions Panel
- Buttons:
  - **Scan Roots**
  - **Run Health Check**
  - (Optional) **Cancel Current Job** (ESC also cancels)

### Status Panel
- Status label (idle/running/canceling/done)
- Summary text box (append logs):
  - Scan: files discovered, inserted, updated, skipped, elapsed time
  - Health: counts by integrity_state (OK/MISSING/UNRESOLVED), elapsed time

---

## Data Flow and Backend Calls

### Add Root…
1. UI opens directory picker
2. User selects directory
3. Call `StorageManager.register_root(path)` (or equivalent)
4. Refresh roots list from DB

### Remove Root
1. Determine selected storage row
2. Guardrails:
   - **Block removal** if it’s the **Unmanaged** storage
   - **Block removal** if the root is referenced by any tracked files in the DB (recommended v0.1)
     - i.e., do not allow deletion while there are rows in `file` with this `storage_id`
3. If allowed: call `StorageManager.unregister_root(storage_id)` (or implement)
4. Refresh roots list

> Decision: removal is prevented unless the user first removes all associated tracked files (i.e., deletes the relevant records from the DB).

### Scan Roots
- In worker:
  1. Call scanner method (e.g., `Scanner.scan_all_roots()`)
  2. Return a summary object (counts + timing)
- On completion:
  - Update status + append summary
  - Emit `scan_completed` signal for future Library tab refresh

### Run Health Check
- In worker:
  1. Call `HealthChecker.check_all_files()`
  2. Return counts by integrity state + timing
- On completion:
  - Update status + append summary
  - Emit `health_completed` signal

> Decision: **Health check validates all files already tracked in the DB**, independent of the most recent scan run.

---

## Threading Model
- Use Qt `QThreadPool` + `QRunnable`
- Implement a generic **CancelableWorker** pattern:
  - Worker holds a `cancel_requested` flag (thread-safe boolean)
  - Long loops periodically check the flag and exit early with a “Canceled” result

### UI Safety
- Disable action buttons while a job is running
- Re-enable on finished/canceled/errored
- Ensure DB connections used inside workers are created inside the worker thread (avoid sharing a single connection across threads)

---

## ESC Cancel Protocol (v0.1)
- Implement a global shortcut / event filter on the main window:
  - **Press ESC** triggers `request_cancel_current_job()`
- Behavior:
  - If scan/health is running: set the cancel flag and update status (“Canceling…”)
  - Worker checks flag frequently and exits cleanly
  - If nothing is running: ESC does nothing

> Decision: use **press ESC to cancel** (not hold).

---

## Persistence and Schema Notes
- Storage roots persist in the **existing AssetHub SQLite DB** via the `storage` table (not a separate DB).
- `Unmanaged` storage must always exist and must not be removable.
- Removing a storage root must not violate invariants (avoid orphaned `file.storage_id` references).

---

## Testing Plan (Stage 7.1)

### Automated (pytest)
- Storage UI actions call `StorageManager` correctly (mock or temp DB)
- Attempting to remove Unmanaged is blocked
- Attempting to remove an in-use root is blocked
- Worker cancellation:
  - a long-running simulated scan/health loop exits when cancel flag is set

### Manual smoke test
1. Create a temp folder with a few nested files
2. Add root via Scan tab
3. Scan roots → confirm summary counts
4. Delete one file on disk
5. Run health check → confirm MISSING count increments
6. Press ESC during a deliberately slow scan → confirm cancel completes and UI remains responsive

---

## Definition of Done
- Roots can be added/removed (with guardrails) and persist across restarts
- Scan runs in background and produces a visible summary
- Health check runs in background and produces counts by integrity state
- ESC cancels a running job without freezing the UI
- Existing tests still pass; new Stage 7.1 tests added where practical