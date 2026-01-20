# src/assethub/ui/views/assets_library_widget.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Set

from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from assethub.context import AppContext
from assethub.core.db.asset_library import AssetRow, list_assets, list_files_for_version, list_versions
from assethub.core.model.version import Version


@dataclass
class _Selected:
    asset_id: Optional[int] = None
    version_id: Optional[int] = None


class _AssetFilterProxy(QSortFilterProxyModel):
    """Simple name/type filtering for the Assets table."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._needle: str = ""

    def set_search(self, text: str) -> None:
        self._needle = (text or "").strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:  # noqa: N802
        needle = self._needle
        if not needle:
            return True
        model = self.sourceModel()
        if model is None:
            return True
        # Columns: 0 name, 1 type
        name = str(model.index(source_row, 0).data() or "").lower()
        typ = str(model.index(source_row, 1).data() or "").lower()
        return needle in name or needle in typ


class AssetsLibraryWidget(QWidget):
    """Asset-level Library widget (Stage 8.5).

    This widget is read-only in v0: it displays assets, their versions, and
    version membership (files). Mutation happens elsewhere (Scan/Actions).
    """

    # Optional: emit file ids for a future “jump to files” action.
    request_jump_to_files = Signal(list)  # list[int]

    def __init__(self, context: AppContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.context = context
        self._storage_id: Optional[int] = None
        self._selected = _Selected()

        self._asset_model = QStandardItemModel(self)
        self._asset_model.setHorizontalHeaderLabels(
            ["Name", "Type", "Latest Version", "Versions", "Files", "Health"]
        )
        self._asset_proxy = _AssetFilterProxy(self)
        self._asset_proxy.setSourceModel(self._asset_model)

        self._versions_list = QListWidget(self)
        self._versions_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self._files_model = QStandardItemModel(self)
        self._files_model.setHorizontalHeaderLabels(["Path", "State"])
        self._files_view = QTableView(self)
        self._files_view.setModel(self._files_model)
        self._files_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._files_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._files_view.setSortingEnabled(True)
        self._files_view.horizontalHeader().setStretchLastSection(True)

        self._build_ui()
        self._wire_events()

    # -----------------
    # Public API
    # -----------------

    def set_storage_id(self, storage_id: Optional[int]) -> None:
        self._storage_id = None if storage_id is None else int(storage_id)

    def set_search_text(self, text: str) -> None:
        self._asset_proxy.set_search(text)

    def refresh(self) -> None:
        """Refresh assets list (and detail panes if selection remains valid)."""
        prev_asset = self._selected.asset_id
        prev_version = self._selected.version_id

        rows = list_assets(self.context.db_connection, storage_id=self._storage_id)

        self._asset_model.removeRows(0, self._asset_model.rowCount())
        for r in rows:
            health = "OK" if r.missing_count == 0 else f"{r.missing_count} MISSING"
            items = [
                QStandardItem(r.name),
                QStandardItem(r.type),
                QStandardItem(r.latest_version_label or ""),
                QStandardItem(str(r.version_count)),
                QStandardItem(str(r.file_count)),
                QStandardItem(health),
            ]
            for it in items:
                it.setEditable(False)
            # store ids on first item
            items[0].setData(int(r.asset_id), Qt.ItemDataRole.UserRole)
            items[0].setData(int(r.storage_id), Qt.ItemDataRole.UserRole + 1)
            self._asset_model.appendRow(items)

        # Re-select prior asset if possible.
        self._selected.asset_id = None
        self._selected.version_id = None

        if prev_asset is not None:
            self._select_asset_id(prev_asset)
        else:
            # select first row by default for convenience
            if self._asset_proxy.rowCount() > 0:
                self._select_proxy_row(0)

        # Restore prior version selection if it still exists.
        if prev_version is not None and self._selected.asset_id == prev_asset:
            self._select_version_id(prev_version)

    # -----------------
    # UI
    # -----------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(self._splitter)

        # Left: assets table
        left = QWidget(self._splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._assets_view = QTableView(left)
        self._assets_view.setModel(self._asset_proxy)
        self._assets_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._assets_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._assets_view.setSortingEnabled(True)
        self._assets_view.horizontalHeader().setStretchLastSection(True)
        left_layout.addWidget(self._assets_view)

        # Right: detail pane (versions + files)
        right = QWidget(self._splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._asset_title = QLabel("", right)
        self._asset_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right_layout.addWidget(self._asset_title)

        inner = QSplitter(Qt.Orientation.Horizontal, right)
        right_layout.addWidget(inner, stretch=1)

        # Versions list
        versions_wrap = QWidget(inner)
        v_layout = QVBoxLayout(versions_wrap)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.addWidget(QLabel("Versions", versions_wrap))
        v_layout.addWidget(self._versions_list)

        # Files table
        files_wrap = QWidget(inner)
        f_layout = QVBoxLayout(files_wrap)
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.addWidget(QLabel("Files", files_wrap))
        f_layout.addWidget(self._files_view)

        inner.setStretchFactor(0, 0)
        inner.setStretchFactor(1, 1)

    def _wire_events(self) -> None:
        sel = self._assets_view.selectionModel()
        if sel is not None:
            sel.selectionChanged.connect(lambda *_: self._on_asset_selection_changed())
        self._versions_list.currentItemChanged.connect(lambda *_: self._on_version_selection_changed())

    # -----------------
    # Selection helpers
    # -----------------

    def _select_proxy_row(self, proxy_row: int) -> None:
        idx = self._asset_proxy.index(proxy_row, 0)
        if not idx.isValid():
            return
        self._assets_view.setCurrentIndex(idx)
        self._assets_view.scrollTo(idx)

    def _select_asset_id(self, asset_id: int) -> None:
        target = int(asset_id)
        for pr in range(self._asset_proxy.rowCount()):
            idx = self._asset_proxy.index(pr, 0)
            if int(idx.data(Qt.ItemDataRole.UserRole) or 0) == target:
                self._select_proxy_row(pr)
                return

    def _select_version_id(self, version_id: int) -> None:
        target = int(version_id)
        for i in range(self._versions_list.count()):
            item = self._versions_list.item(i)
            if item is None:
                continue
            if int(item.data(Qt.ItemDataRole.UserRole) or 0) == target:
                self._versions_list.setCurrentRow(i)
                return

    # -----------------
    # Handlers
    # -----------------

    def _on_asset_selection_changed(self) -> None:
        idx = self._assets_view.currentIndex()
        if not idx.isValid():
            self._set_asset_detail(None, None)
            return

        asset_id = int(idx.data(Qt.ItemDataRole.UserRole) or 0)
        if asset_id <= 0:
            self._set_asset_detail(None, None)
            return

        self._selected.asset_id = asset_id
        self._selected.version_id = None

        # Update title
        name = str(self._asset_proxy.index(idx.row(), 0).data() or "")
        typ = str(self._asset_proxy.index(idx.row(), 1).data() or "")
        self._asset_title.setText(f"{name}  —  {typ}")

        # Load versions
        vers = list_versions(self.context.db_connection, asset_id=asset_id)
        self._populate_versions(vers)

        # Select latest by default
        if vers:
            latest = vers[-1]
            self._select_version_id(latest.id)
        else:
            self._files_model.removeRows(0, self._files_model.rowCount())

    def _populate_versions(self, versions: List[Version]) -> None:
        self._versions_list.clear()
        for v in versions:
            it = QListWidgetItem(f"{v.label}")
            it.setData(Qt.ItemDataRole.UserRole, int(v.id))
            it.setToolTip(f"sort_key={v.sort_key}")
            self._versions_list.addItem(it)

    def _on_version_selection_changed(self) -> None:
        item = self._versions_list.currentItem()
        if item is None:
            self._files_model.removeRows(0, self._files_model.rowCount())
            self._selected.version_id = None
            return

        vid = int(item.data(Qt.ItemDataRole.UserRole) or 0)
        if vid <= 0:
            self._files_model.removeRows(0, self._files_model.rowCount())
            self._selected.version_id = None
            return

        self._selected.version_id = vid
        files = list_files_for_version(self.context.db_connection, version_id=vid)
        self._populate_files(files)

    def _populate_files(self, files: List[dict]) -> None:
        self._files_model.removeRows(0, self._files_model.rowCount())
        for f in files:
            path_item = QStandardItem(str(f.get("relative_path", "")))
            state_item = QStandardItem(str(f.get("integrity_state", "")))
            path_item.setEditable(False)
            state_item.setEditable(False)
            path_item.setData(int(f.get("file_id", 0)), Qt.ItemDataRole.UserRole)
            self._files_model.appendRow([path_item, state_item])

        self._files_view.resizeColumnsToContents()

    def _set_asset_detail(self, asset: Optional[AssetRow], versions: Optional[List[Version]]) -> None:
        self._asset_title.setText("")
        self._versions_list.clear()
        self._files_model.removeRows(0, self._files_model.rowCount())
