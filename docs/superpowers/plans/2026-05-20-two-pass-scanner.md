# Two-Pass Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `Scanner.scan_all()` into `scan_files_only()` (fast index pass) and `compute_missing_checksums()` (background SHA-256 pass), wired in `ScanTab` as two independent job slots so users can browse files and use all app features immediately after Stage 1 completes.

**Architecture:** Two new methods on `Scanner` (Qt-free core, no threading knowledge); `ScanTab` manages a primary job slot (scan/health — blocks UI as today) and a silent secondary slot (checksum — never blocks any button). A new `ChecksumFinished` event triggers the Library's Duplicates view to refresh when Stage 2 completes.

**Tech Stack:** Python 3.x · PySide6 · SQLite · pytest

---

## File Map

| File | Change |
|---|---|
| `src/assethub/core/scanner/scanner.py` | Add `ChecksumResult`, `_CHECKSUM_BATCH_SIZE`, `scan_files_only()`, `compute_missing_checksums()` |
| `src/assethub/core/events/event_hub.py` | Add `ChecksumFinished` dataclass + `checksum_finished` event on `EventHub` |
| `src/assethub/ui/views/scan_tab.py` | Two job slots, new methods, updated orchestration |
| `tests/test_scanner_two_pass.py` | New file — 8 tests for the two new Scanner methods |

---

### Task 1: `scan_files_only()` — TDD

**Files:**
- Create: `tests/test_scanner_two_pass.py`
- Modify: `src/assethub/core/scanner/scanner.py`

- [ ] **Step 1: Create the test file with three failing tests**

Create `tests/test_scanner_two_pass.py`:

```python
from __future__ import annotations

import os
import time
from pathlib import Path


def _make_env(tmp_path: Path):
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.storage.roots import StorageManager

    conn = get_connection(str(tmp_path / "test.db"))
    initialize_schema(conn)
    sm = StorageManager(conn)
    sm.ensure_unmanaged_storage()
    root = tmp_path / "root"
    root.mkdir()
    sm.register_root(str(root), name="TestRoot")
    return conn, sm, str(root)


def _make_scanner(conn, sm):
    from assethub.core.scanner.scanner import Scanner
    return Scanner(conn, sm)


def test_scan_files_only_leaves_checksums_null(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "a.txt").write_bytes(b"hello")
    scanner = _make_scanner(conn, sm)

    result = scanner.scan_files_only()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='a.txt'").fetchone()
    assert row is not None
    assert row[0] is None
    assert result.files_indexed == 1
    assert result.files_checksummed == 0


def test_scan_files_only_preserves_existing_checksum(tmp_path: Path) -> None:
    """Unchanged file keeps its existing checksum after scan_files_only."""
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "b.txt").write_bytes(b"stable content")
    scanner = _make_scanner(conn, sm)

    scanner.scan_all()  # populate with a real checksum

    # Poison the checksum — scan_files_only must leave it alone for unchanged files.
    conn.execute("UPDATE file SET checksum='poisoned' WHERE relative_path='b.txt'")
    conn.commit()

    scanner.scan_files_only()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='b.txt'").fetchone()
    assert row[0] == "poisoned", "scan_files_only overwrote a valid checksum for an unchanged file"


def test_scan_files_only_nulls_stale_checksum(tmp_path: Path) -> None:
    """Changed file (different mtime) has its checksum NULLed by scan_files_only."""
    conn, sm, root = _make_env(tmp_path)
    f = Path(root) / "c.txt"
    f.write_bytes(b"version 1")
    scanner = _make_scanner(conn, sm)

    scanner.scan_all()  # get a real checksum first

    original = conn.execute("SELECT checksum FROM file WHERE relative_path='c.txt'").fetchone()[0]
    assert original is not None

    # Modify the file so size and mtime change.
    time.sleep(0.05)
    f.write_bytes(b"version 2 — different content")
    os.utime(str(f), None)

    scanner.scan_files_only()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='c.txt'").fetchone()
    assert row[0] is None, "scan_files_only did not NULL the stale checksum after file changed"
```

- [ ] **Step 2: Run to confirm all three tests fail**

```
pytest tests/test_scanner_two_pass.py -v
```

Expected: all three `FAILED` — `AttributeError: 'Scanner' object has no attribute 'scan_files_only'`

- [ ] **Step 3: Add `scan_files_only()` to `scanner.py`**

In `src/assethub/core/scanner/scanner.py`, add this method to the `Scanner` class after
`scan_all()` and before the `# ---------------------------` internals comment:

```python
def scan_files_only(self, *, cancel_check: Optional[Callable[[], bool]] = None) -> ScanResult:
    """Stage 1 of two-pass scanning: index files without computing checksums.

    - New or changed files: upsert with checksum = NULL (marks them pending).
    - Unchanged files: upsert preserving any existing checksum.

    Never calls sha256_file(). Touches disk only via os.stat().
    """
    roots = self._scan_roots()
    discovered: List[str] = []
    indexed = 0

    exclusions: dict[int, frozenset[str]] = {
        root.id: get_exclusions(self._conn, root.id)
        for root in roots
    }

    def _should_cancel() -> bool:
        if cancel_check is None:
            return False
        try:
            return bool(cancel_check())
        except Exception:
            return False

    for root in roots:
        if root.root_path is None:
            continue

        if _should_cancel():
            self._conn.commit()
            return ScanResult(
                discovered_paths=discovered,
                files_indexed=indexed,
                files_checksummed=0,
                files_without_checksum=self._count_without_checksum(),
                canceled=True,
            )

        for dirpath, _dirnames, filenames in os.walk(root.root_path):
            if _should_cancel():
                self._conn.commit()
                return ScanResult(
                    discovered_paths=discovered,
                    files_indexed=indexed,
                    files_checksummed=0,
                    files_without_checksum=self._count_without_checksum(),
                    canceled=True,
                )
            for fname in filenames:
                if _should_cancel():
                    self._conn.commit()
                    return ScanResult(
                        discovered_paths=discovered,
                        files_indexed=indexed,
                        files_checksummed=0,
                        files_without_checksum=self._count_without_checksum(),
                        canceled=True,
                    )

                ext = os.path.splitext(fname)[1].lstrip(".").lower()
                if ext and ext in exclusions.get(root.id, frozenset()):
                    continue

                abs_path = os.path.join(dirpath, fname)
                try:
                    st = os.stat(abs_path)
                except FileNotFoundError:
                    continue

                rel = os.path.relpath(abs_path, root.root_path)
                rel = rel.replace("\\", "/")

                disk_size = int(st.st_size)
                disk_mtime = float(st.st_mtime)

                old_row = self._conn.execute(
                    "SELECT size_bytes, mtime_unix "
                    "FROM file WHERE storage_id=? AND relative_path=?",
                    (root.id, rel),
                ).fetchone()

                file_changed = (
                    old_row is None
                    or old_row[0] != disk_size
                    or old_row[1] != disk_mtime
                )

                self._upsert_file(
                    storage_id=root.id,
                    relative_path=rel,
                    size_bytes=disk_size,
                    mtime_unix=disk_mtime,
                    checksum=None,
                    update_checksum=file_changed,
                )
                discovered.append(abs_path)
                indexed += 1

    self._conn.commit()
    return ScanResult(
        discovered_paths=discovered,
        files_indexed=indexed,
        files_checksummed=0,
        files_without_checksum=self._count_without_checksum(),
        canceled=False,
    )
```

- [ ] **Step 4: Run to confirm all three tests pass**

```
pytest tests/test_scanner_two_pass.py -v
```

Expected: all three `PASSED`.

- [ ] **Step 5: Run the full suite to check for regressions**

```
pytest
```

Expected: all tests pass (97 pre-existing + 3 new = 100).

- [ ] **Step 6: Commit**

```bash
git add tests/test_scanner_two_pass.py src/assethub/core/scanner/scanner.py
git commit -m "feat: add Scanner.scan_files_only() — Stage 1 of two-pass scan"
```

---

### Task 2: `compute_missing_checksums()` — TDD

**Files:**
- Modify: `tests/test_scanner_two_pass.py`
- Modify: `src/assethub/core/scanner/scanner.py`

- [ ] **Step 1: Add five failing tests to `test_scanner_two_pass.py`**

Append to the end of `tests/test_scanner_two_pass.py`:

```python
def test_compute_missing_checksums_hashes_null_files(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "a.txt").write_bytes(b"some content")
    scanner = _make_scanner(conn, sm)

    scanner.scan_files_only()  # leaves checksum NULL

    result = scanner.compute_missing_checksums()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='a.txt'").fetchone()
    assert row[0] is not None
    assert len(row[0]) == 64  # SHA-256 hex digest length
    assert result.files_checksummed == 1
    assert result.files_failed == 0
    assert not result.canceled


def test_compute_missing_checksums_processes_beyond_batch_size(tmp_path: Path) -> None:
    """All files are checksummed even when count exceeds the internal batch size (50)."""
    conn, sm, root = _make_env(tmp_path)
    for i in range(55):
        (Path(root) / f"file{i}.txt").write_bytes(f"content {i}".encode())
    scanner = _make_scanner(conn, sm)

    scanner.scan_files_only()
    result = scanner.compute_missing_checksums()

    null_count = conn.execute("SELECT COUNT(*) FROM file WHERE checksum IS NULL").fetchone()[0]
    assert null_count == 0
    assert result.files_checksummed == 55


def test_compute_missing_checksums_cancel_stops_early(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    for i in range(5):
        (Path(root) / f"file{i}.txt").write_bytes(f"content {i}".encode())
    scanner = _make_scanner(conn, sm)
    scanner.scan_files_only()

    # cancel_check returns True immediately — no files should be processed.
    result = scanner.compute_missing_checksums(cancel_check=lambda: True)

    assert result.canceled
    assert result.files_checksummed == 0
    null_count = conn.execute("SELECT COUNT(*) FROM file WHERE checksum IS NULL").fetchone()[0]
    assert null_count == 5


def test_compute_missing_checksums_skips_unreadable_files(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    f = Path(root) / "gone.txt"
    f.write_bytes(b"temporary")
    scanner = _make_scanner(conn, sm)
    scanner.scan_files_only()

    # Delete after indexing — sha256_file will raise FileNotFoundError (subclass of OSError).
    f.unlink()

    result = scanner.compute_missing_checksums()

    assert result.files_failed == 1
    assert result.files_checksummed == 0
    row = conn.execute("SELECT checksum FROM file WHERE relative_path='gone.txt'").fetchone()
    assert row[0] is None  # checksum stays NULL on failure


def test_two_pass_equivalent_to_scan_all(tmp_path: Path) -> None:
    """scan_files_only() + compute_missing_checksums() produces the same checksums as scan_all()."""
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.storage.roots import StorageManager
    from assethub.core.scanner.scanner import Scanner

    contents = [b"alpha", b"beta", b"gamma"]

    def make_env(base: Path):
        conn = get_connection(str(base / "test.db"))
        initialize_schema(conn)
        sm = StorageManager(conn)
        sm.ensure_unmanaged_storage()
        root = base / "root"
        root.mkdir()
        sm.register_root(str(root), name="TestRoot")
        for i, c in enumerate(contents):
            (root / f"file{i}.txt").write_bytes(c)
        return conn, sm

    # Two-pass
    tp_base = tmp_path / "tp"
    tp_base.mkdir()
    conn1, sm1 = make_env(tp_base)
    s1 = Scanner(conn1, sm1)
    s1.scan_files_only()
    s1.compute_missing_checksums()

    # Single-pass
    sp_base = tmp_path / "sp"
    sp_base.mkdir()
    conn2, sm2 = make_env(sp_base)
    s2 = Scanner(conn2, sm2)
    s2.scan_all()

    rows1 = conn1.execute(
        "SELECT relative_path, checksum FROM file WHERE checksum IS NOT NULL ORDER BY relative_path"
    ).fetchall()
    rows2 = conn2.execute(
        "SELECT relative_path, checksum FROM file WHERE checksum IS NOT NULL ORDER BY relative_path"
    ).fetchall()

    assert rows1 == rows2
```

- [ ] **Step 2: Run to confirm the first 3 tests pass and the 5 new tests fail**

```
pytest tests/test_scanner_two_pass.py -v
```

Expected: first 3 `PASSED`, last 5 `FAILED` — `AttributeError: 'Scanner' object has no attribute 'compute_missing_checksums'`

- [ ] **Step 3: Add `ChecksumResult` and `_CHECKSUM_BATCH_SIZE` to `scanner.py`**

In `src/assethub/core/scanner/scanner.py`, add after the `ScanResult` dataclass:

```python
@dataclass(frozen=True)
class ChecksumResult:
    files_checksummed: int
    files_failed: int
    canceled: bool


_CHECKSUM_BATCH_SIZE = 50
```

- [ ] **Step 4: Add `compute_missing_checksums()` to the `Scanner` class**

Add after `scan_files_only()` and before the `# ---------------------------` internals comment:

```python
def compute_missing_checksums(
    self, *, cancel_check: Optional[Callable[[], bool]] = None
) -> ChecksumResult:
    """Stage 2 of two-pass scanning: hash all files with checksum IS NULL.

    Processes files in batches and re-queries after each batch so that
    files indexed by a concurrent Stage 1 are picked up automatically.

    Files that raise OSError during hashing are skipped (files_failed is
    incremented) and retain checksum=NULL for retry on the next call.
    """
    files_checksummed = 0
    files_failed = 0
    failed_ids: set[int] = set()

    # Build storage_id -> root_path lookup once per call.
    root_map: dict[int, str] = {
        r.id: r.root_path
        for r in self._storage.list_roots()
        if r.root_path is not None
    }

    def _should_cancel() -> bool:
        if cancel_check is None:
            return False
        try:
            return bool(cancel_check())
        except Exception:
            return False

    while True:
        if _should_cancel():
            return ChecksumResult(
                files_checksummed=files_checksummed,
                files_failed=files_failed,
                canceled=True,
            )

        if failed_ids:
            ph = ",".join("?" * len(failed_ids))
            rows = self._conn.execute(
                f"SELECT id, storage_id, relative_path FROM file "
                f"WHERE checksum IS NULL AND id NOT IN ({ph}) LIMIT ?",
                (*sorted(failed_ids), _CHECKSUM_BATCH_SIZE),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, storage_id, relative_path FROM file "
                "WHERE checksum IS NULL LIMIT ?",
                (_CHECKSUM_BATCH_SIZE,),
            ).fetchall()

        if not rows:
            break

        for file_id, storage_id, relative_path in rows:
            if _should_cancel():
                self._conn.commit()
                return ChecksumResult(
                    files_checksummed=files_checksummed,
                    files_failed=files_failed,
                    canceled=True,
                )

            root_path = root_map.get(int(storage_id))
            if root_path is None:
                failed_ids.add(int(file_id))
                files_failed += 1
                continue

            abs_path = os.path.join(root_path, relative_path.replace("/", os.sep))

            try:
                checksum = sha256_file(abs_path)
            except OSError:
                if self._log is not None:
                    self._log.warn(f"Checksum skipped (unreadable): {abs_path}")
                failed_ids.add(int(file_id))
                files_failed += 1
                continue

            self._conn.execute(
                "UPDATE file SET checksum=? WHERE id=?",
                (checksum, int(file_id)),
            )
            files_checksummed += 1

        self._conn.commit()

    return ChecksumResult(
        files_checksummed=files_checksummed,
        files_failed=files_failed,
        canceled=False,
    )
```

- [ ] **Step 5: Run all 8 tests to confirm they all pass**

```
pytest tests/test_scanner_two_pass.py -v
```

Expected: all 8 `PASSED`.

- [ ] **Step 6: Run the full suite**

```
pytest
```

Expected: all tests pass (97 + 8 = 105).

- [ ] **Step 7: Commit**

```bash
git add tests/test_scanner_two_pass.py src/assethub/core/scanner/scanner.py
git commit -m "feat: add Scanner.compute_missing_checksums() and ChecksumResult — Stage 2 of two-pass scan"
```

---

### Task 3: `ChecksumFinished` event

**Files:**
- Modify: `src/assethub/core/events/event_hub.py`

No new tests — `EventHub` is already tested and `ChecksumFinished` follows the identical
pattern as `ScanFinished` and `HealthFinished`.

- [ ] **Step 1: Add `ChecksumFinished` dataclass to `event_hub.py`**

In `src/assethub/core/events/event_hub.py`, add after the `HealthFinished` dataclass:

```python
@dataclass(frozen=True)
class ChecksumFinished:
    summary: Dict[str, Any]
```

- [ ] **Step 2: Register `checksum_finished` on `EventHub`**

In `EventHub.__init__`, add after the `self.health_finished` line:

```python
self.checksum_finished: Event[ChecksumFinished] = Event("checksum_finished")
```

- [ ] **Step 3: Run the full suite**

```
pytest
```

Expected: all 105 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/assethub/core/events/event_hub.py
git commit -m "feat: add ChecksumFinished event to EventHub"
```

---

### Task 4: ScanTab — two-pass orchestration

**Files:**
- Modify: `src/assethub/ui/views/scan_tab.py`

No new unit tests (ScanTab orchestration is deferred to a future integration test pass).
The full suite must stay green.

- [ ] **Step 1: Update imports at the top of `scan_tab.py`**

Change:
```python
from assethub.core.scanner.scanner import Scanner
```
to:
```python
from assethub.core.scanner.scanner import ChecksumResult, Scanner
```

Change:
```python
from assethub.core.events.event_hub import DbChanged, ScanFinished, HealthFinished
```
to:
```python
from assethub.core.events.event_hub import ChecksumFinished, DbChanged, HealthFinished, ScanFinished
```

- [ ] **Step 2: Add checksum job state fields to `ScanTab.__init__`**

In `ScanTab.__init__`, after the existing:
```python
self._cancel_event: Optional[Event] = None
```
add:
```python
self._current_checksum_job: Optional[str] = None
self._checksum_cancel: Optional[Event] = None
```

(`Event` here is `threading.Event`, already imported at the top of the file.)

- [ ] **Step 3: Cancel any running checksum job before starting a new scan**

Replace the `_on_scan` method:

```python
@Slot()
def _on_scan(self) -> None:
    # Cancel any running checksum pass before starting a new index scan.
    if self._current_checksum_job is not None and self._checksum_cancel is not None:
        self._checksum_cancel.set()
    try:
        self.context.log.info("Scan roots: started")
    except Exception:
        pass
    self._start_job("scan", self._scan_job)
```

- [ ] **Step 4: Change `_scan_job` to call `scan_files_only` instead of `scan_all`**

In `_scan_job`, change the one line:
```python
res = scanner.scan_all(cancel_check=cancel.is_set)
```
to:
```python
res = scanner.scan_files_only(cancel_check=cancel.is_set)
```

- [ ] **Step 5: Update the `ScanSummary` block in `_on_job_finished` to start Stage 2**

Find the `if isinstance(result, ScanSummary):` block in `_on_job_finished`. Replace it
with the version below. The changes are: the `self.status_label.setText(...)` line is
removed (Stage 2 sets the label instead), and `self._start_checksum_job()` is added at the
end of the block.

```python
if isinstance(result, ScanSummary):
    tag = "canceled" if result.canceled else "ok"
    try:
        self.context.log.info(
            f"Scan roots: indexed {result.files_indexed} file(s) in {result.elapsed_s:.2f}s ({tag})"
        )
    except Exception:
        pass
    self.scan_completed.emit()
    # Stage 7.5: Central event hub emissions.
    self.context.event_hub.scan_finished.emit(
        ScanFinished(
            summary={
                "files_indexed": int(result.files_indexed),
                "canceled": bool(result.canceled),
                "elapsed_s": float(result.elapsed_s),
            }
        )
    )
    if int(result.files_indexed) > 0:
        self.context.event_hub.db_changed.emit(
            DbChanged(reason="scan_index_updated", payload={"files_indexed": int(result.files_indexed)})
        )
    self._start_checksum_job()
```

The `elif isinstance(result, HealthSummary):` block and the `else:` block are unchanged.

- [ ] **Step 6: Add the four new Stage 2 methods**

Add these methods inside the `# Background task implementations` section of `ScanTab`,
after the existing `_health_job` method:

```python
def _start_checksum_job(self) -> None:
    """Start Stage 2: hash all NULL-checksum files in a silent background worker."""
    if self.context.thread_pool is None:
        self.status_label.setText("Scan complete")
        return
    self._current_checksum_job = "checksum"
    self._checksum_cancel = Event()
    self.status_label.setText("Indexing complete — computing checksums in background")

    signals = _WorkerSignals()
    signals.finished.connect(self._on_checksum_finished)
    signals.error.connect(self._on_checksum_error)

    worker = _CancelableWorker(
        fn=self._checksum_job,
        cancel_event=self._checksum_cancel,
        signals=signals,
    )
    self.context.thread_pool.start(worker)

def _checksum_job(self, cancel: Event) -> ChecksumResult:
    conn = get_connection(self.context.config.db_path)
    try:
        initialize_schema(conn)
        storage = StorageManager(conn)
        storage.ensure_unmanaged_storage()
        scanner = Scanner(conn, storage)
        return scanner.compute_missing_checksums(cancel_check=cancel.is_set)
    finally:
        conn.close()

@Slot(object)
def _on_checksum_finished(self, result: object) -> None:
    self._current_checksum_job = None
    self._checksum_cancel = None

    if not isinstance(result, ChecksumResult):
        return

    if result.canceled:
        self.status_label.setText("Checksum pass canceled")
    else:
        self.status_label.setText("Scan complete — checksums up to date")

    try:
        tag = "canceled" if result.canceled else "ok"
        self.context.log.info(
            f"Checksum pass: {result.files_checksummed} checksummed, "
            f"{result.files_failed} failed ({tag})"
        )
    except Exception:
        pass

    self.context.event_hub.checksum_finished.emit(
        ChecksumFinished(
            summary={
                "files_checksummed": int(result.files_checksummed),
                "files_failed": int(result.files_failed),
                "canceled": bool(result.canceled),
            }
        )
    )
    if result.files_checksummed > 0:
        self.context.event_hub.db_changed.emit(
            DbChanged(
                reason="checksums_updated",
                payload={"files_checksummed": int(result.files_checksummed)},
            )
        )

@Slot(str)
def _on_checksum_error(self, message: str) -> None:
    self._current_checksum_job = None
    self._checksum_cancel = None
    self.status_label.setText("Checksum pass failed")
    try:
        self.context.log.error(f"Checksum pass failed: {message}")
    except Exception:
        pass
```

- [ ] **Step 7: Update `request_cancel_current_job` to handle Stage 2**

Replace the `request_cancel_current_job` method:

```python
def request_cancel_current_job(self) -> None:
    """Request cancellation of the active primary job or checksum pass (ESC)."""
    if self._current_job is not None and self._cancel_event is not None:
        if not self._cancel_event.is_set():
            self._cancel_event.set()
            self.status_label.setText(f"Cancel requested ({self._current_job})…")
            try:
                self.context.log.warn(f"Cancel requested: {self._current_job}")
            except Exception:
                pass
    elif self._current_checksum_job is not None and self._checksum_cancel is not None:
        if not self._checksum_cancel.is_set():
            self._checksum_cancel.set()
            self.status_label.setText("Cancel requested (checksum)…")
            try:
                self.context.log.warn("Cancel requested: checksum")
            except Exception:
                pass
```

- [ ] **Step 8: Run the full test suite**

```
pytest
```

Expected: all 105 tests pass.

- [ ] **Step 9: Commit**

```bash
git add src/assethub/ui/views/scan_tab.py
git commit -m "feat: wire two-pass scan in ScanTab — silent background checksum job"
```
