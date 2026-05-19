# Scan Exclusions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-storage-root extension exclusion list so users can prevent specific file types from being indexed during scanning.

**Architecture:** New `storage_scan_exclusion` DB table (schema v8) with a Qt-free helper module in `core/db/`. The scanner loads exclusion sets before walking each root. UI lives in a new `EditRootDialog` accessible via a toolbar button and right-click menu in the Scan tab.

**Tech Stack:** Python 3.x · PySide6 · SQLite · pytest

---

## File Map

| File | Action |
|---|---|
| `src/assethub/core/db/schema.py` | Modify — add DDL, `_migrate_to_v8`, bump `LATEST_SCHEMA_VERSION` to 8 |
| `src/assethub/core/db/scan_exclusions.py` | Create — Qt-free DB helper |
| `src/assethub/core/scanner/scanner.py` | Modify — load exclusions, skip excluded extensions |
| `src/assethub/ui/dialogs/edit_root_dialog.py` | Create — Edit Root dialog |
| `src/assethub/ui/views/scan_tab.py` | Modify — "Edit…" toolbar button + context menu entry |
| `tests/test_scan_exclusions.py` | Create — DB helper tests |
| `tests/test_scanner_exclusions.py` | Create — scanner exclusion tests |

---

## Task 1: Schema v8 — `storage_scan_exclusion` table

**Files:**
- Modify: `src/assethub/core/db/schema.py`

- [ ] **Step 1: Add DDL to `initialize_schema`**

In `schema.py`, add the new table definition inside the `ddl` string (after `file_binding` and before the `tag` table):

```python
    -- Schema v8: per-root scan exclusions
    CREATE TABLE IF NOT EXISTS storage_scan_exclusion (
        id          INTEGER PRIMARY KEY,
        storage_id  INTEGER NOT NULL REFERENCES storage(id) ON DELETE CASCADE,
        extension   TEXT NOT NULL,
        UNIQUE(storage_id, extension)
    );
    CREATE INDEX IF NOT EXISTS idx_scan_exclusion_storage ON storage_scan_exclusion(storage_id);
```

- [ ] **Step 2: Add `_migrate_to_v8`**

Add this function at the bottom of the migration functions (before `_MIGRATIONS`):

```python
def _migrate_to_v8(conn: sqlite3.Connection) -> None:
    """Migrate to schema v8.

    v8 adds per-root scan exclusions:
      - storage_scan_exclusion(storage_id, extension)

    Migration is forward-only and idempotent.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS storage_scan_exclusion (
            id          INTEGER PRIMARY KEY,
            storage_id  INTEGER NOT NULL REFERENCES storage(id) ON DELETE CASCADE,
            extension   TEXT NOT NULL,
            UNIQUE(storage_id, extension)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scan_exclusion_storage ON storage_scan_exclusion(storage_id);"
    )
    _record_schema_version(conn, 8)
```

- [ ] **Step 3: Bump version and register migration**

Change `LATEST_SCHEMA_VERSION = 7` → `LATEST_SCHEMA_VERSION = 8`.

Add to `_MIGRATIONS`:
```python
    8: _migrate_to_v8,
```

- [ ] **Step 4: Run existing tests to confirm nothing broke**

```
pytest tests/test_db_schema.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/assethub/core/db/schema.py
git commit -m "feat: schema v8 — add storage_scan_exclusion table"
```

---

## Task 2: DB helper module — `core/db/scan_exclusions.py`

**Files:**
- Create: `src/assethub/core/db/scan_exclusions.py`
- Create: `tests/test_scan_exclusions.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scan_exclusions.py`:

```python
# tests/test_scan_exclusions.py
from __future__ import annotations

import sqlite3
from pathlib import Path

from assethub.core.db.schema import initialize_schema
from assethub.core.db.scan_exclusions import (
    get_exclusions,
    set_exclusions,
    add_exclusion,
    remove_exclusion,
)


def _mk_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.sqlite3")
    initialize_schema(conn)
    return conn


def _insert_root(conn: sqlite3.Connection, name: str = "Root") -> int:
    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, 'OK');",
        (name, f"/tmp/{name}"),
    )
    conn.commit()
    return int(conn.execute("SELECT id FROM storage WHERE name=?;", (name,)).fetchone()[0])


def test_get_exclusions_empty_for_new_root(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    assert get_exclusions(conn, sid) == frozenset()


def test_add_exclusion_and_retrieve(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    assert get_exclusions(conn, sid) == frozenset({"log"})


def test_add_exclusion_normalizes_dot_and_case(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, ".LOG")
    assert get_exclusions(conn, sid) == frozenset({"log"})


def test_add_exclusion_duplicate_is_ignored(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    add_exclusion(conn, sid, "log")  # should not raise
    assert get_exclusions(conn, sid) == frozenset({"log"})


def test_remove_exclusion(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    remove_exclusion(conn, sid, "log")
    assert get_exclusions(conn, sid) == frozenset()


def test_remove_nonexistent_exclusion_is_noop(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    remove_exclusion(conn, sid, "log")  # should not raise


def test_set_exclusions_replaces_full_set(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    add_exclusion(conn, sid, "tmp")
    set_exclusions(conn, sid, ["png", "jpg"])
    assert get_exclusions(conn, sid) == frozenset({"png", "jpg"})


def test_set_exclusions_to_empty_clears_all(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    set_exclusions(conn, sid, [])
    assert get_exclusions(conn, sid) == frozenset()


def test_set_exclusions_normalizes_extensions(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    set_exclusions(conn, sid, [".PNG", "JPG", ".Fbx"])
    assert get_exclusions(conn, sid) == frozenset({"png", "jpg", "fbx"})


def test_exclusions_are_per_root(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid_a = _insert_root(conn, "RootA")
    sid_b = _insert_root(conn, "RootB")
    add_exclusion(conn, sid_a, "log")
    assert get_exclusions(conn, sid_b) == frozenset()


def test_removing_storage_root_cascades_exclusions(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    conn.execute("DELETE FROM storage WHERE id=?;", (sid,))
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM storage_scan_exclusion WHERE storage_id=?;", (sid,)
    ).fetchone()[0]
    assert count == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_scan_exclusions.py -v
```

Expected: `ImportError: cannot import name 'get_exclusions' from 'assethub.core.db.scan_exclusions'`

- [ ] **Step 3: Create `src/assethub/core/db/scan_exclusions.py`**

```python
# src/assethub/core/db/scan_exclusions.py
"""Per-root scan extension exclusion helpers.

Extensions are stored and returned normalized: lowercase, no leading dot.
All write functions apply normalization before touching the DB.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable


def _normalize(extension: str) -> str:
    return extension.lstrip(".").lower().strip()


def get_exclusions(conn: sqlite3.Connection, storage_id: int) -> frozenset[str]:
    """Return the set of excluded extensions for a storage root.

    Returns an empty frozenset if no exclusions are configured.
    Extensions are returned normalized (lowercase, no dot).
    """
    rows = conn.execute(
        "SELECT extension FROM storage_scan_exclusion WHERE storage_id=?;",
        (int(storage_id),),
    ).fetchall()
    return frozenset(str(r[0]) for r in rows)


def add_exclusion(conn: sqlite3.Connection, storage_id: int, extension: str) -> None:
    """Add a single extension to the exclusion list for a root.

    Normalizes the extension before inserting. Duplicate insertions are ignored.
    """
    ext = _normalize(extension)
    if not ext:
        return
    conn.execute(
        "INSERT OR IGNORE INTO storage_scan_exclusion(storage_id, extension) VALUES (?, ?);",
        (int(storage_id), ext),
    )
    conn.commit()


def remove_exclusion(conn: sqlite3.Connection, storage_id: int, extension: str) -> None:
    """Remove a single extension from the exclusion list for a root.

    No-op if the extension is not present.
    """
    ext = _normalize(extension)
    conn.execute(
        "DELETE FROM storage_scan_exclusion WHERE storage_id=? AND extension=?;",
        (int(storage_id), ext),
    )
    conn.commit()


def set_exclusions(
    conn: sqlite3.Connection,
    storage_id: int,
    extensions: Iterable[str],
) -> None:
    """Replace the full exclusion set for a root.

    Deletes all existing exclusions for the root, then inserts the new set.
    Normalizes all extensions before inserting. Duplicates in input are ignored.
    """
    sid = int(storage_id)
    normalized = {_normalize(e) for e in extensions if _normalize(e)}
    conn.execute(
        "DELETE FROM storage_scan_exclusion WHERE storage_id=?;",
        (sid,),
    )
    for ext in sorted(normalized):
        conn.execute(
            "INSERT OR IGNORE INTO storage_scan_exclusion(storage_id, extension) VALUES (?, ?);",
            (sid, ext),
        )
    conn.commit()
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_scan_exclusions.py -v
```

Expected: all 12 tests pass.

- [ ] **Step 5: Run full suite to confirm no regressions**

```
pytest -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/assethub/core/db/scan_exclusions.py tests/test_scan_exclusions.py
git commit -m "feat: add scan_exclusions DB helper module with tests"
```

---

## Task 3: Scanner — skip excluded extensions

**Files:**
- Modify: `src/assethub/core/scanner/scanner.py`
- Create: `tests/test_scanner_exclusions.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scanner_exclusions.py`:

```python
# tests/test_scanner_exclusions.py
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from assethub.core.db.schema import initialize_schema
from assethub.core.db.scan_exclusions import add_exclusion
from assethub.core.scanner.scanner import Scanner
from assethub.core.storage.roots import StorageManager


def _mk_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.sqlite3")
    initialize_schema(conn)
    return conn


def _mk_root(conn: sqlite3.Connection, path: Path) -> int:
    sm = StorageManager(conn)
    root = sm.register_root(str(path))
    return int(root.id)


def _indexed_paths(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT relative_path FROM file;").fetchall()
    return {str(r[0]) for r in rows}


def test_excluded_extension_not_indexed(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    (root_dir / "texture.png").write_text("data")
    (root_dir / "cache.log").write_text("data")

    sid = _mk_root(conn, root_dir)
    add_exclusion(conn, sid, "log")

    scanner = Scanner(conn, StorageManager(conn))
    scanner.scan_all()

    paths = _indexed_paths(conn)
    assert "texture.png" in paths
    assert "cache.log" not in paths


def test_non_excluded_extension_is_indexed(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    (root_dir / "model.fbx").write_text("data")

    sid = _mk_root(conn, root_dir)
    add_exclusion(conn, sid, "log")  # only log excluded

    scanner = Scanner(conn, StorageManager(conn))
    scanner.scan_all()

    assert "model.fbx" in _indexed_paths(conn)


def test_exclusions_are_per_root(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)

    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "file.log").write_text("data")
    (root_b / "file.log").write_text("data")

    sid_a = _mk_root(conn, root_a)
    _mk_root(conn, root_b)
    add_exclusion(conn, sid_a, "log")  # only root_a excludes log

    scanner = Scanner(conn, StorageManager(conn))
    scanner.scan_all()

    paths = _indexed_paths(conn)
    assert "file.log" not in paths  # root_a — excluded
    # root_b's file.log should be indexed (same relative_path, different storage_id)
    row = conn.execute(
        "SELECT COUNT(*) FROM file WHERE relative_path='file.log';"
    ).fetchone()
    assert int(row[0]) == 1  # only root_b's copy


def test_already_indexed_files_remain_after_exclusion_added(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    (root_dir / "junk.log").write_text("data")

    sid = _mk_root(conn, root_dir)
    scanner = Scanner(conn, StorageManager(conn))

    # First scan: no exclusions — file gets indexed
    scanner.scan_all()
    assert "junk.log" in _indexed_paths(conn)

    # Add exclusion, re-scan — file must remain in DB (Option A)
    add_exclusion(conn, sid, "log")
    scanner.scan_all()
    assert "junk.log" in _indexed_paths(conn)


def test_no_exclusions_indexes_all_files(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    (root_dir / "a.png").write_text("data")
    (root_dir / "b.fbx").write_text("data")
    (root_dir / "c.log").write_text("data")

    _mk_root(conn, root_dir)
    scanner = Scanner(conn, StorageManager(conn))
    scanner.scan_all()

    paths = _indexed_paths(conn)
    assert paths == {"a.png", "b.fbx", "c.log"}
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_scanner_exclusions.py -v
```

Expected: `test_excluded_extension_not_indexed` FAILS — `cache.log` is currently indexed despite the exclusion because the scanner doesn't check exclusions yet.

- [ ] **Step 3: Update `scanner.py` to load and apply exclusions**

Add the import at the top of `scanner.py` (after existing imports):

```python
from assethub.core.db.scan_exclusions import get_exclusions
```

In `scan_all`, replace the existing `for root in roots:` loop preamble. Before the loop, load all exclusion sets:

```python
    def scan_all(self, *, cancel_check: Optional[Callable[[], bool]] = None) -> ScanResult:
        roots = self._scan_roots()
        discovered: List[str] = []
        indexed = 0

        # Load exclusion sets for all roots before walking.
        exclusions: dict[int, frozenset[str]] = {
            root.id: get_exclusions(self._conn, root.id)
            for root in roots
        }

        def _should_cancel() -> bool:
            ...  # unchanged
```

Inside the inner `for fname in filenames:` loop, add the exclusion check immediately after the cancel check and before `abs_path` is computed:

```python
                for fname in filenames:
                    if _should_cancel():
                        self._conn.commit()
                        return ScanResult(discovered_paths=discovered, files_indexed=indexed, canceled=True)

                    # Skip files whose extension is excluded for this root.
                    ext = os.path.splitext(fname)[1].lstrip(".").lower()
                    if ext in exclusions.get(root.id, frozenset()):
                        continue

                    abs_path = os.path.join(dirpath, fname)
                    # ... rest of loop unchanged
```

- [ ] **Step 4: Run scanner exclusion tests**

```
pytest tests/test_scanner_exclusions.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Run full suite**

```
pytest -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/assethub/core/scanner/scanner.py tests/test_scanner_exclusions.py
git commit -m "feat: scanner skips files matching per-root extension exclusions"
```

---

## Task 4: `EditRootDialog` — `ui/dialogs/edit_root_dialog.py`

**Files:**
- Create: `src/assethub/ui/dialogs/edit_root_dialog.py`

No Qt-free unit tests for this dialog — it requires a `QApplication`. Manual testing covers it in Task 5.

- [ ] **Step 1: Create the dialog**

Create `src/assethub/ui/dialogs/edit_root_dialog.py`:

```python
# src/assethub/ui/dialogs/edit_root_dialog.py
"""EditRootDialog — view and edit per-root scan exclusions."""

from __future__ import annotations

import sqlite3
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assethub.core.db.scan_exclusions import get_exclusions, set_exclusions
from assethub.core.storage.roots import StorageRoot


class EditRootDialog(QDialog):
    """Dialog to view and edit scan exclusions for a storage root.

    Changes are written to the DB only when the user clicks Save.
    Cancel discards all in-memory changes.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        root: StorageRoot,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._root = root
        self.setWindowTitle("Edit Storage Root")
        self.setMinimumWidth(420)
        self._build_ui()
        self._load_exclusions()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Root info (read-only)
        info_label = QLabel(
            f"<b>{self._root.display_label}</b><br>"
            f"<small>{self._root.root_path or '(Unmanaged)'}</small>"
        )
        info_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info_label)

        layout.addSpacing(8)
        layout.addWidget(QLabel("Scan exclusions (extensions to skip):"))

        # List of current exclusions
        self._list = QListWidget(self)
        layout.addWidget(self._list)

        # Add row
        add_row = QHBoxLayout()
        self._input = QLineEdit(self)
        self._input.setPlaceholderText("e.g. log, .tmp, FBX")
        self._input.returnPressed.connect(self._on_add)
        self._btn_add = QPushButton("Add")
        self._btn_add.clicked.connect(self._on_add)
        add_row.addWidget(self._input, stretch=1)
        add_row.addWidget(self._btn_add)
        layout.addLayout(add_row)

        # Remove selected button
        self._btn_remove = QPushButton("Remove selected")
        self._btn_remove.clicked.connect(self._on_remove_selected)
        layout.addWidget(self._btn_remove)

        layout.addSpacing(8)

        # Save / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load_exclusions(self) -> None:
        self._list.clear()
        exts = sorted(get_exclusions(self._conn, int(self._root.id)))
        for ext in exts:
            self._list.addItem(QListWidgetItem(ext))

    def _current_extensions(self) -> list[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_add(self) -> None:
        raw = self._input.text().strip()
        if not raw:
            return
        # Support comma-separated input
        parts = [p.strip().lstrip(".").lower() for p in raw.split(",") if p.strip()]
        existing = set(self._current_extensions())
        for ext in parts:
            if not ext:
                continue
            if ext not in existing:
                self._list.addItem(QListWidgetItem(ext))
                existing.add(ext)
        self._input.clear()

    def _on_remove_selected(self) -> None:
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))

    def _on_save(self) -> None:
        try:
            set_exclusions(self._conn, int(self._root.id), self._current_extensions())
        except Exception as exc:
            QMessageBox.warning(self, "AssetHub", f"Failed to save exclusions: {exc}")
            return
        self.accept()
```

- [ ] **Step 2: Verify the import works**

```
python -c "from assethub.ui.dialogs.edit_root_dialog import EditRootDialog; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/assethub/ui/dialogs/edit_root_dialog.py
git commit -m "feat: add EditRootDialog for per-root scan exclusion management"
```

---

## Task 5: Scan tab — "Edit…" button and context menu entry

**Files:**
- Modify: `src/assethub/ui/views/scan_tab.py`

- [ ] **Step 1: Add the import**

At the top of `scan_tab.py`, add to the existing dialog imports:

```python
from assethub.ui.dialogs.edit_root_dialog import EditRootDialog
```

- [ ] **Step 2: Add the "Edit…" toolbar button**

In `_build_ui`, in the `roots_btn_row` section, add `btn_edit_root` between the Add and Remove buttons:

```python
        self.btn_edit_root = QPushButton("Edit…")
        self.btn_edit_root.clicked.connect(self._on_edit_root)
        roots_btn_row.addWidget(self.btn_add_root)
        roots_btn_row.addWidget(self.btn_edit_root)
        roots_btn_row.addWidget(self.btn_remove_root)
```

- [ ] **Step 3: Update `_update_action_button_states` to enable/disable "Edit…"**

In `_update_action_button_states`, add the edit button state alongside the detect button:

```python
    def _update_action_button_states(self) -> None:
        if self._current_job is not None:
            self.btn_detect_assets.setEnabled(False)
            self.btn_edit_root.setEnabled(False)
            return
        root = self._get_selected_storage_root()
        is_managed = bool(
            root is not None
            and root.root_path is not None
            and str(root.status).upper() != StorageManager.UNMANAGED_STATUS
        )
        self.btn_detect_assets.setEnabled(is_managed)
        self.btn_edit_root.setEnabled(is_managed)
```

- [ ] **Step 4: Add `_on_edit_root` slot**

Add this method after `_on_remove_root`:

```python
    @Slot()
    def _on_edit_root(self) -> None:
        root = self._get_selected_storage_root()
        if root is None:
            QMessageBox.information(self, "AssetHub", "Select a storage root to edit.")
            return
        if root.root_path is None or str(root.status).upper() == StorageManager.UNMANAGED_STATUS:
            QMessageBox.information(self, "AssetHub", "Cannot edit the Unmanaged storage root.")
            return
        conn = self.context.db_connection
        if conn is None:
            return
        dlg = EditRootDialog(conn, root, parent=self)
        if dlg.exec() == EditRootDialog.DialogCode.Accepted:
            self.context.event_hub.db_changed.emit(
                DbChanged(
                    reason="scan_exclusions_updated",
                    payload={"storage_id": int(root.id)},
                )
            )
```

- [ ] **Step 5: Add "Edit root…" to the right-click context menu**

In `_on_roots_context_menu`, add the new action before `act_rename`:

```python
            menu = QMenu(self)

            act_edit = menu.addAction("Edit root…")
            act_rename = menu.addAction("Rename (display name)…")
            act_remove = menu.addAction("Remove root from tracking…")

            if root.root_path is None or str(root.status).upper() == StorageManager.UNMANAGED_STATUS:
                act_edit.setEnabled(False)
                act_rename.setEnabled(False)
                act_remove.setEnabled(False)

            chosen = menu.exec(self.roots_table.viewport().mapToGlobal(pos))
            if chosen is None:
                return

            if chosen == act_edit:
                self._on_edit_root()
            elif chosen == act_rename:
                self._rename_storage_root(root)
            elif chosen == act_remove:
                self._remove_root_from_tracking(root)
```

- [ ] **Step 6: Run full test suite**

```
pytest -q
```

Expected: all pass.

- [ ] **Step 7: Manual smoke test**

Launch the app with `python main.py`. Verify:
1. Add a storage root → "Edit…" button becomes enabled
2. Click "Edit…" → `EditRootDialog` opens showing root name and empty exclusion list
3. Type `log` in the input and click "Add" → appears in list
4. Type `.TMP, .cache` → both appear normalized (`tmp`, `cache`)
5. Select an entry and click "Remove selected" → removed from list
6. Click Save → dialog closes, no error
7. Re-open Edit dialog for same root → previously saved exclusions appear
8. Right-click a root row → "Edit root…" appears in menu and opens same dialog
9. Click Cancel → no changes persisted

- [ ] **Step 8: Commit**

```bash
git add src/assethub/ui/views/scan_tab.py
git commit -m "feat: add Edit Root dialog access to Scan tab toolbar and context menu"
```

---

## Task 6: End-to-end smoke test and branch wrap-up

- [ ] **Step 1: Run full test suite one final time**

```
pytest -v
```

Expected: all tests pass, no warnings about missing fixtures or imports.

- [ ] **Step 2: Manual end-to-end test**

Launch `python main.py`. Verify the full flow:
1. Register a storage root containing a mix of file types (e.g. `.png`, `.log`, `.fbx`)
2. Open Edit dialog → add `log` to exclusions → Save
3. Click "Scan Roots" → scan completes
4. Open Library tab → confirm `.log` files do not appear
5. Confirm `.png` and `.fbx` files do appear

- [ ] **Step 3: Push branch and open PR**

```bash
git push -u origin feature/scan-exclusions
"/c/Program Files/GitHub CLI/gh.exe" pr create \
  --title "feat: per-root scan exclusion list (closes #2)" \
  --base raptor \
  --body "Implements smay3d/assethub#2.

## Changes
- Schema v8: new \`storage_scan_exclusion\` table
- \`core/db/scan_exclusions.py\`: Qt-free helper (get/set/add/remove)
- \`core/scanner/scanner.py\`: skips excluded extensions per root
- \`ui/dialogs/edit_root_dialog.py\`: new Edit Root dialog
- \`ui/views/scan_tab.py\`: Edit button + right-click menu entry
- 2 new test files (12 + 5 tests)

## Test plan
- [ ] All pytest tests pass
- [ ] Manual: add exclusions, scan, confirm excluded types absent from Library
- [ ] Manual: Edit dialog accessible via toolbar button and right-click menu
- [ ] Manual: Cancel does not persist changes"
```
