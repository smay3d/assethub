# src/assethub/ui/views/duplicates_view.py
"""Duplicates view — shows file groups that share a SHA-256 checksum."""

from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from assethub.context import AppContext
from assethub.core.db.duplicates import (
    DuplicateGroup,
    count_checksummed_files,
    query_duplicate_groups,
)
from assethub.core.db.file_records import query_library_files_by_ids
from assethub.ui.models.file_table_model import FileRow, FileTableModel


def _fmt_bytes(size: Optional[int]) -> str:
    """Format a byte count as a human-readable string."""
    if size is None:
        return ""
    s = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if s < 1024.0 or unit == "TB":
            return f"{int(s)} {unit}" if unit == "B" else f"{s:.1f} {unit}"
        s /= 1024.0
    return f"{int(size)} B"


class DuplicateGroupTableModel(QAbstractTableModel):
    """Table model for the duplicate groups list.

    Each row represents one group of files with the same SHA-256 checksum.
    Columns: Copies | Size | Overlap | Locations
    """

    _HEADERS = ["Copies", "Size", "Overlap", "Locations"]

    # Column indices
    _COL_COPIES = 0
    _COL_SIZE = 1
    _COL_OVERLAP = 2
    _COL_LOCATIONS = 3

    def __init__(self) -> None:
        super().__init__()
        self._groups: List[DuplicateGroup] = []

    def set_groups(self, groups: List[DuplicateGroup]) -> None:
        self.beginResetModel()
        self._groups = list(groups)
        self.endResetModel()

    def group_at(self, row: int) -> Optional[DuplicateGroup]:
        if 0 <= row < len(self._groups):
            return self._groups[row]
        return None

    # ----- Qt overrides -----

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._groups)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._HEADERS):
                return self._HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:  # noqa: N802
        if not index.isValid():
            return None
        g = self.group_at(index.row())
        if g is None:
            return None
        col = index.column()
        size = g.files[0].size_bytes if g.files else None
        overlap = (g.file_count - 1) * (size or 0)

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self._COL_COPIES:
                return str(g.file_count)
            if col == self._COL_SIZE:
                return _fmt_bytes(size)
            if col == self._COL_OVERLAP:
                return _fmt_bytes(overlap)
            if col == self._COL_LOCATIONS:
                names = sorted({f.storage_name for f in g.files})
                s = ", ".join(names)
                return s[:60] + "…" if len(s) > 63 else s

        if role == Qt.ItemDataRole.UserRole:
            if col == self._COL_COPIES:
                return g.file_count
            if col == self._COL_OVERLAP:
                return overlap
            if col == self._COL_SIZE:
                return size or 0

        return None


class DuplicatesView(QWidget):
    """Library tab Duplicates view.

    Shows duplicate file groups (files sharing a SHA-256 checksum) with a
    detail panel listing all members of the selected group.
    """

    def __init__(self, context: AppContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._context = context
        self._group_model = DuplicateGroupTableModel()
        self._detail_model = FileTableModel()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        # Status banner — shown when unchecksummed files exist.
        self._banner = QLabel("", self)
        self._banner.setVisible(False)
        layout.addWidget(self._banner)

        # Summary line.
        self._summary = QLabel("", self)
        layout.addWidget(self._summary)

        # Vertical splitter: groups table (top) / detail table + button (bottom).
        splitter = QSplitter(Qt.Orientation.Vertical, self)

        # --- Groups table ---
        self._groups_proxy = QSortFilterProxyModel()
        self._groups_proxy.setSourceModel(self._group_model)
        self._groups_proxy.setSortRole(Qt.ItemDataRole.UserRole)

        self._groups_table = QTableView(self)
        self._groups_table.setModel(self._groups_proxy)
        self._groups_table.setSortingEnabled(True)
        self._groups_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._groups_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._groups_table.setAlternatingRowColors(True)
        self._groups_table.verticalHeader().hide()
        self._groups_table.verticalHeader().setDefaultSectionSize(26)
        self._groups_table.horizontalHeader().setStretchLastSection(True)
        self._groups_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Default sort: Overlap descending (column 2).
        self._groups_table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        splitter.addWidget(self._groups_table)

        # --- Detail table + copy button ---
        detail_container = QWidget()
        det_layout = QVBoxLayout(detail_container)
        det_layout.setContentsMargins(0, 0, 0, 0)

        self._detail_proxy = QSortFilterProxyModel()
        self._detail_proxy.setSourceModel(self._detail_model)
        self._detail_proxy.setSortRole(Qt.ItemDataRole.UserRole)

        self._detail_table = QTableView(self)
        self._detail_table.setModel(self._detail_proxy)
        self._detail_table.setSortingEnabled(True)
        self._detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._detail_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._detail_table.setAlternatingRowColors(True)
        self._detail_table.verticalHeader().hide()
        self._detail_table.verticalHeader().setDefaultSectionSize(26)
        self._detail_table.horizontalHeader().setStretchLastSection(True)
        det_layout.addWidget(self._detail_table)

        self._copy_btn = QPushButton("Copy path(s)", self)
        self._copy_btn.setEnabled(False)
        det_layout.addWidget(self._copy_btn)

        splitter.addWidget(detail_container)
        layout.addWidget(splitter, stretch=1)

        # Wire events.
        groups_sel = self._groups_table.selectionModel()
        if groups_sel is not None:
            groups_sel.selectionChanged.connect(self._on_group_selected)

        detail_sel = self._detail_table.selectionModel()
        if detail_sel is not None:
            detail_sel.selectionChanged.connect(self._on_detail_selection_changed)

        self._copy_btn.clicked.connect(self._copy_selected_paths)

    def refresh(self) -> None:
        """Reload duplicate groups from the database."""
        conn = self._context.db_connection
        if conn is None:
            return

        # Status banner.
        checksummed, total = count_checksummed_files(conn)
        missing = total - checksummed
        if missing > 0:
            self._banner.setText(
                f"{missing} file(s) not yet checksummed — run a scan to compute."
            )
            self._banner.setVisible(True)
        else:
            self._banner.setVisible(False)

        # Groups.
        groups = query_duplicate_groups(conn)
        self._group_model.set_groups(groups)

        # Summary line.
        if not groups:
            self._summary.setText("No duplicate files found.")
        else:
            redundant = sum(g.file_count - 1 for g in groups)
            overlap_bytes = sum(
                (g.file_count - 1) * (g.files[0].size_bytes or 0) for g in groups
            )
            self._summary.setText(
                f"{len(groups)} duplicate group(s)"
                f" · {redundant} redundant copies"
                f" · {_fmt_bytes(overlap_bytes)} overlap"
            )

        # Clear detail panel.
        self._detail_model.set_rows([])
        self._copy_btn.setEnabled(False)

    def _on_group_selected(self, _selected, _deselected) -> None:
        idx = self._groups_table.currentIndex()
        if not idx.isValid():
            self._detail_model.set_rows([])
            return

        src_row = self._groups_proxy.mapToSource(idx).row()
        group = self._group_model.group_at(src_row)
        if group is None:
            self._detail_model.set_rows([])
            return

        conn = self._context.db_connection
        if conn is None:
            return

        file_ids = [f.file_id for f in group.files]
        lib_rows = query_library_files_by_ids(conn, file_ids)

        file_rows: List[FileRow] = []
        for r in lib_rows:
            rel_s = r.relative_path
            filename = rel_s.split("/")[-1] if "/" in rel_s else rel_s
            file_rows.append(
                FileRow(
                    file_id=r.file_id,
                    storage_id=r.storage_id,
                    version_id=r.version_id,
                    storage_name=r.storage_name,
                    relative_path=rel_s,
                    filename=filename,
                    bound_asset_id=r.bound_asset_id,
                    bound_asset_name=r.bound_asset_name,
                    owned_version_count=r.owned_version_count,
                    integrity_state=r.integrity_state,
                    size_bytes=r.size_bytes,
                    mtime_unix=r.mtime_unix,
                    created_at=r.created_at,
                    is_duplicate=False,  # Already in a duplicates context; no chip needed.
                )
            )
        self._detail_model.set_rows(file_rows)

    def _on_detail_selection_changed(self, _selected, _deselected) -> None:
        sel = self._detail_table.selectionModel()
        has_selection = sel is not None and bool(sel.selectedRows())
        self._copy_btn.setEnabled(has_selection)

    def _copy_selected_paths(self) -> None:
        conn = self._context.db_connection
        if conn is None:
            return

        sel = self._detail_table.selectionModel()
        if sel is None:
            return

        paths: List[str] = []
        for pidx in sel.selectedRows(0):
            src = self._detail_proxy.mapToSource(pidx)
            row = self._detail_model.row_data(src.row())
            if row is None:
                continue
            db_row = conn.execute(
                """
                SELECT storage.root_path
                FROM file
                JOIN storage ON storage.id = file.storage_id
                WHERE file.id = ?;
                """,
                (row.file_id,),
            ).fetchone()
            if db_row and db_row[0]:
                abs_path = os.path.join(str(db_row[0]), row.relative_path.replace("/", os.sep))
                paths.append(abs_path)

        if paths:
            QApplication.clipboard().setText("\n".join(paths))
