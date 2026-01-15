# src/assethub/ui/views/library_tab.py

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal, QUrl, QSettings
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from assethub.context import AppContext
from assethub.core.db.schema import initialize_schema
from assethub.ui.models.file_table_model import FileRow, FileTableModel
from assethub.ui.ui_constants import LIBRARY_CAP_ROWS
from assethub.ui.views.file_detail_pane import FileDetailPane, compute_absolute_path


class FileFilterProxyModel(QSortFilterProxyModel):
    """Proxy model that implements search + simple dropdown filters."""

    def __init__(self) -> None:
        super().__init__()
        self._search_text: str = ""
        self._storage_id: Optional[int] = None
        self._integrity: Optional[str] = None

        self.setDynamicSortFilter(True)
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def _invalidate(self) -> None:
        """Request the proxy to re-evaluate its row filter.

        Qt 6.13+ deprecates invalidateFilter()/invalidateRowsFilter(). The
        recommended API is beginFilterChange()/endFilterChange(Direction.Rows).
        """
        if hasattr(self, "beginFilterChange") and hasattr(self, "endFilterChange"):
            # Preferred in newer Qt/PySide6
            self.beginFilterChange()  # type: ignore[attr-defined]
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)  # type: ignore[attr-defined]
            return

        # Fallback for older Qt/PySide6
        if hasattr(self, "invalidateRowsFilter"):
            self.invalidateRowsFilter()  # type: ignore[attr-defined]
        else:
            self.invalidateFilter()

    def set_search_text(self, text: str) -> None:
        self._search_text = (text or "").strip().lower()
        self._invalidate()

    def set_storage_id(self, storage_id: Optional[int]) -> None:
        self._storage_id = storage_id
        self._invalidate()

    def set_integrity(self, integrity: Optional[str]) -> None:
        self._integrity = integrity
        self._invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:  # noqa: N802
        model = self.sourceModel()
        if not isinstance(model, FileTableModel):
            return True
        row = model.row_data(source_row)
        if row is None:
            return False

        if self._storage_id is not None and int(row.storage_id) != int(self._storage_id):
            return False

        if self._integrity is not None and str(row.integrity_state).upper() != str(self._integrity).upper():
            return False

        if self._search_text:
            hay_a = (row.filename or "").lower()
            hay_b = (row.relative_path or "").lower()
            if self._search_text not in hay_a and self._search_text not in hay_b:
                return False

        return True


@dataclass(frozen=True)
class _Counts:
    shown: int
    loaded: int
    total_in_db: Optional[int]
    truncated: bool


class LibraryTab(QWidget):
    """Stage 7.2: Library tab UI (v0.1).

    Displays indexed `file` records, supports sorting, search, and basic filters.
    """

    file_selected = Signal(int)  # file_id

    CAP_ROWS = LIBRARY_CAP_ROWS

    _SETTINGS_KEY_HSPLIT = "ui/library/hsplitter_state"

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context

        self.model = FileTableModel()
        self.proxy = FileFilterProxyModel()
        self.proxy.setSourceModel(self.model)

        self._selected_file_id: Optional[int] = None

        self._build_ui()
        self._wire_events()
        self.refresh()

    # -----------------
    # UI
    # -----------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Top controls
        top = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Search filename or path…")

        self.storage_combo = QComboBox(self)
        self.integrity_combo = QComboBox(self)
        self.chk_show_hidden = QCheckBox("Show hidden columns", self)
        self.btn_refresh = QPushButton("Refresh", self)

        top.addWidget(QLabel("Search:"))
        top.addWidget(self.search_edit, stretch=2)
        top.addWidget(QLabel("Storage:"))
        top.addWidget(self.storage_combo)
        top.addWidget(QLabel("Integrity:"))
        top.addWidget(self.integrity_combo)
        top.addWidget(self.chk_show_hidden)
        top.addWidget(self.btn_refresh)
        root.addLayout(top)

        # Master–detail split view
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        left = QWidget(self.splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Table
        self.table = QTableView(left)
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        left_layout.addWidget(self.table, stretch=1)

        # Footer (belongs with the table)
        self.status_label = QLabel("", left)
        left_layout.addWidget(self.status_label)

        conn = self.context.db_connection
        if conn is None:
            raise RuntimeError("AppContext db_connection is not initialized")
        self.detail_pane = FileDetailPane(conn, parent=self.splitter)

        self.splitter.addWidget(left)
        self.splitter.addWidget(self.detail_pane)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        root.addWidget(self.splitter, stretch=1)

        # Restore splitter state (if available), otherwise use default ratios.
        self._restore_splitter_state()
        self.splitter.splitterMoved.connect(lambda *_: self._save_splitter_state())

        self._apply_column_visibility()
        self._rebuild_filter_options(preserve_selection=False)
        self._update_status_label()

    def _wire_events(self) -> None:
        self.btn_refresh.clicked.connect(self.refresh)
        self.search_edit.textChanged.connect(self._on_search_changed)
        self.chk_show_hidden.toggled.connect(lambda _v: self._apply_column_visibility())

        self.storage_combo.currentIndexChanged.connect(self._on_storage_filter_changed)
        self.integrity_combo.currentIndexChanged.connect(self._on_integrity_filter_changed)

        # Update footer when filters change.
        self.proxy.modelReset.connect(self._update_status_label)
        self.proxy.rowsInserted.connect(lambda *_: self._update_status_label())
        self.proxy.rowsRemoved.connect(lambda *_: self._update_status_label())
        self.proxy.layoutChanged.connect(self._update_status_label)

        # Selection -> emit file_id
        sel = self.table.selectionModel()
        if sel is not None:
            sel.selectionChanged.connect(self._on_selection_changed)

        # Context menu on rows
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu_requested)

    def _on_search_changed(self, text: str) -> None:
        self.proxy.set_search_text(text)
        self._update_status_label()

    # -----------------
    # Public API
    # -----------------

    def refresh(self) -> None:
        """Reload the table from the database."""
        prev_selected = self._selected_file_id
        conn = self.context.db_connection
        if conn is None:
            raise RuntimeError("AppContext db_connection is not initialized")

        initialize_schema(conn)

        # Count total rows first (for footer).
        total_row = conn.execute("SELECT COUNT(*) FROM file;").fetchone()
        total_in_db = int(total_row[0]) if total_row else 0

        # Load a capped number of rows; fetch one extra to detect truncation.
        limit = self.CAP_ROWS + 1
        rows = conn.execute(
            """
            SELECT
                file.id,
                file.version_id,
                file.storage_id,
                storage.name,
                file.relative_path,
                file.integrity_state,
                file.size_bytes,
                file.mtime_unix,
                file.created_at
            FROM file
            JOIN storage ON storage.id = file.storage_id
            ORDER BY file.id
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()

        truncated = len(rows) > self.CAP_ROWS
        if truncated:
            rows = rows[: self.CAP_ROWS]

        file_rows = []
        for (file_id, version_id, storage_id, storage_name, rel, integrity, size_b, mtime_u, created_at) in rows:
            rel_s = str(rel)
            filename = rel_s.split("/")[-1] if "/" in rel_s else rel_s
            file_rows.append(
                FileRow(
                    file_id=int(file_id),
                    storage_id=int(storage_id),
                    version_id=None if version_id is None else int(version_id),
                    storage_name=str(storage_name),
                    relative_path=rel_s,
                    filename=filename,
                    integrity_state=str(integrity),
                    size_bytes=None if size_b is None else int(size_b),
                    mtime_unix=None if mtime_u is None else float(mtime_u),
                    created_at=str(created_at),
                )
            )

        self.model.set_rows(file_rows, total_in_db=total_in_db, truncated=truncated)
        self._rebuild_filter_options(preserve_selection=True)
        self._apply_column_visibility()
        self._update_status_label()

        # Preserve selection by file_id if possible; otherwise clear detail pane.
        if prev_selected is not None:
            if not self._select_file_id(prev_selected):
                self._selected_file_id = None
                self.detail_pane.clear()
        else:
            self.detail_pane.clear()

    def _on_search_changed(self, text: str) -> None:
        self.proxy.set_search_text(text)
        self._update_status_label()

    # -----------------
    # Filters
    # -----------------

    def _rebuild_filter_options(self, *, preserve_selection: bool) -> None:
        current_storage = self._current_storage_filter() if preserve_selection else None
        current_integrity = self._current_integrity_filter() if preserve_selection else None

        # Storage options
        self.storage_combo.blockSignals(True)
        self.storage_combo.clear()
        self.storage_combo.addItem("All", None)
        sm = self.context.storage_manager
        if sm is not None:
            for r in sm.list_roots():
                # Show name; if duplicates ever exist, id distinguishes.
                self.storage_combo.addItem(r.name, int(r.id))
        self.storage_combo.blockSignals(False)

        # Integrity options
        self.integrity_combo.blockSignals(True)
        self.integrity_combo.clear()
        self.integrity_combo.addItem("All", None)
        for st in ["OK", "MISSING", "UNRESOLVED"]:
            self.integrity_combo.addItem(st, st)
        self.integrity_combo.blockSignals(False)

        if preserve_selection:
            if current_storage is not None:
                self._set_combo_by_data(self.storage_combo, current_storage)
            if current_integrity is not None:
                self._set_combo_by_data(self.integrity_combo, current_integrity)

        # Apply current selections to proxy
        self._on_storage_filter_changed()
        self._on_integrity_filter_changed()

    def _on_storage_filter_changed(self) -> None:
        self.proxy.set_storage_id(self._current_storage_filter())
        self._update_status_label()

    def _on_integrity_filter_changed(self) -> None:
        self.proxy.set_integrity(self._current_integrity_filter())
        self._update_status_label()

    def _current_storage_filter(self) -> Optional[int]:
        data = self.storage_combo.currentData()
        return None if data is None else int(data)

    def _current_integrity_filter(self) -> Optional[str]:
        data = self.integrity_combo.currentData()
        return None if data is None else str(data)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: object) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    # -----------------
    # Column visibility
    # -----------------

    def _apply_column_visibility(self) -> None:
        show_hidden = bool(self.chk_show_hidden.isChecked())
        for idx, col in enumerate(self.model.columns):
            hide = (not col.default_visible) and (not show_hidden)
            self.table.setColumnHidden(idx, hide)

    # -----------------
    # Selection
    # -----------------

    def _on_selection_changed(self, selected, _deselected) -> None:
        if selected is None or not selected.indexes():
            self._selected_file_id = None
            self.detail_pane.clear()
            return

        proxy_index = selected.indexes()[0]
        src_index = self.proxy.mapToSource(proxy_index)
        file_id = self.model.file_id_for_row(src_index.row())
        if file_id is None:
            self._selected_file_id = None
            self.detail_pane.clear()
            return

        fid = int(file_id)
        self._selected_file_id = fid
        self.detail_pane.set_file_id(fid)
        self.file_selected.emit(fid)

    def _select_file_id(self, file_id: int) -> bool:
        """Select a row in the proxy model by file_id, respecting current filters."""
        target = int(file_id)
        for src_row in range(self.model.rowCount()):
            if self.model.file_id_for_row(src_row) == target:
                src_index = self.model.index(src_row, 0)
                proxy_index = self.proxy.mapFromSource(src_index)
                if not proxy_index.isValid():
                    return False
                self.table.setCurrentIndex(proxy_index)
                self.table.selectRow(proxy_index.row())
                return True
        return False

    def _resolve_absolute_path(self, file_id: int) -> Optional[str]:
        conn = self.context.db_connection
        if conn is None:
            return None
        row = conn.execute(
            """
            SELECT storage.root_path, file.relative_path
            FROM file
            JOIN storage ON storage.id = file.storage_id
            WHERE file.id = ?;
            """,
            (int(file_id),),
        ).fetchone()
        if not row:
            return None
        root_path, rel = row
        return compute_absolute_path(None if root_path is None else str(root_path), str(rel))

    def _on_context_menu_requested(self, pos) -> None:
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return

        # Select the row under the cursor.
        self.table.selectRow(idx.row())

        src_index = self.proxy.mapToSource(idx)
        file_id = self.model.file_id_for_row(src_index.row())
        if file_id is None:
            return

        abs_path = self._resolve_absolute_path(int(file_id))
        if not abs_path:
            return

        menu = QMenu(self)

        act_copy_abs = menu.addAction("Copy absolute path")
        act_copy_abs.triggered.connect(lambda: FileDetailPane.copy_to_clipboard(abs_path))

        folder = os.path.dirname(abs_path)
        act_open = menu.addAction("Open in Explorer")
        act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder)))

        menu.exec(self.table.viewport().mapToGlobal(pos))


    # -----------------
    # Splitter persistence
    # -----------------

    def _settings(self) -> QSettings:
        return QSettings()

    def _save_splitter_state(self) -> None:
        try:
            s = self._settings()
            s.setValue(self._SETTINGS_KEY_HSPLIT, self.splitter.saveState())
        except Exception:
            return

    def _restore_splitter_state(self) -> None:
        try:
            s = self._settings()
            state = s.value(self._SETTINGS_KEY_HSPLIT)
            if state:
                ok = self.splitter.restoreState(state)
                if ok:
                    return
        except Exception:
            pass

        # Fallback: default sizing based on current width.
        w = max(1, int(self.width()))
        self.splitter.setSizes([int(w * 0.6), int(w * 0.4)])

    # -----------------
    # Status
    # -----------------

    def _counts(self) -> _Counts:
        shown = int(self.proxy.rowCount())
        loaded = int(self.model.rowCount())
        total = self.model.total_in_db
        truncated = bool(self.model.truncated)
        return _Counts(shown=shown, loaded=loaded, total_in_db=total, truncated=truncated)

    def _update_status_label(self) -> None:
        c = self._counts()
        msg = f"Showing {c.shown} files (of {c.loaded} loaded)"
        if c.total_in_db is not None and c.total_in_db != c.loaded:
            msg += f" — DB has {c.total_in_db}"
        if c.truncated:
            msg += f" (capped at {self.CAP_ROWS})"
        self.status_label.setText(msg)
