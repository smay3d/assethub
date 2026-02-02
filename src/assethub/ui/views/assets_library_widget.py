# src/assethub/ui/views/assets_library_widget.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Set, Tuple, Dict

from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal, QItemSelectionModel, QEvent
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from assethub.context import AppContext
from assethub.core.events.event_hub import DbChanged
from assethub.core.db.asset_library import AssetRow, list_assets, list_files_for_version, list_versions
from assethub.core.db.tags import list_tags, list_tags_for_asset_ids, add_tags_to_assets, remove_tags_from_assets
from assethub.core.db.versions import (
    get_version,
    set_version_discarded,
    set_version_sort_key,
    set_version_user_label,
)
from assethub.core.model.tag import Tag
from assethub.core.model.version import Version
from assethub.ui.actions.library_actions import LibraryActions
from assethub.ui.delegates.tag_chips_delegate import TagChipsDelegate, TAG_PAYLOAD_ROLE
from assethub.ui.dialogs.tag_manager_dialog import TagManagerDialog
from assethub.ui.dialogs.tag_select_dialog import TagSelectDialog
from assethub.ui.utils.clipboard import set_clipboard_text

class _NoCollapseOnRightClickTableView(QTableView):
    """A QTableView that preserves multi-selection on right-click.

    Qt can collapse multi-selection on right-click (often on mouse release or
    context-menu dispatch). The Library file view solved this by short-circuiting
    right-click presses on already-selected rows. In Assets view, platform/Qt
    combos can still collapse selection later in the event chain.

    This implementation uses a viewport event filter to reliably:
      - Preserve selection when right-clicking an already-selected row
      - Keep default behavior when right-clicking an unselected row
      - Emit the custom context menu request for preserved-selection cases
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._preserve_selection: bool = False
        self._saved_selected_rows: list = []
        # Mouse events for item views arrive on the viewport.
        self.viewport().installEventFilter(self)

    def _is_row_selected(self, idx) -> bool:
        if not idx.isValid():
            return False
        sel = self.selectionModel()
        if sel is None:
            return False
        idx0 = idx.siblingAtColumn(0)
        try:
            return bool(sel.isRowSelected(idx.row(), idx.parent()) or sel.isSelected(idx0))
        except Exception:
            return bool(sel.isSelected(idx0))

    def _snapshot_selection(self) -> None:
        sel = self.selectionModel()
        if sel is None:
            self._saved_selected_rows = []
            return
        # Save proxy-model indices (as seen by the view), column 0 per row.
        rows = sel.selectedRows(0)
        self._saved_selected_rows = list(rows)

    def _restore_selection(self) -> None:
        sel = self.selectionModel()
        if sel is None:
            return
        if not self._saved_selected_rows:
            return
        sel.clearSelection()
        for idx in self._saved_selected_rows:
            if idx.isValid():
                sel.select(
                    idx,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        # We only care about viewport events.
        if watched is not self.viewport():
            return super().eventFilter(watched, event)

        et = event.type()

        # Right mouse press: decide whether we preserve selection for this click.
        if et == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                idx = self.indexAt(event.pos())
                if self._is_row_selected(idx):
                    self._preserve_selection = True
                    self._snapshot_selection()
                    # Update current index without changing selection so the
                    # detail pane stays aligned with the clicked row.
                    sel = self.selectionModel()
                    if sel is not None:
                        sel.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.NoUpdate)
                    event.accept()
                    # Swallow to prevent Qt from clearing selection.
                    return True
                self._preserve_selection = False
            return super().eventFilter(watched, event)

        # Right mouse release: if we preserved selection, swallow to avoid Qt
        # performing any late selection changes on release.
        if et == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.RightButton and self._preserve_selection:
                event.accept()
                return True
            return super().eventFilter(watched, event)

        # Context menu event: if this right-click was on a selected row, restore
        # selection and emit the custom context menu request ourselves (single menu).
        if et == QEvent.Type.ContextMenu:
            if self._preserve_selection:
                idx = self.indexAt(event.pos())
                if idx.isValid():
                    self._restore_selection()
                    sel = self.selectionModel()
                    if sel is not None:
                        sel.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.NoUpdate)
                # Emit in viewport coordinates.
                self.customContextMenuRequested.emit(event.pos())
                self._preserve_selection = False
                event.accept()
                return True
            return super().eventFilter(watched, event)

        return super().eventFilter(watched, event)



@dataclass
class _Selected:
    asset_id: Optional[int] = None
    version_id: Optional[int] = None


class _AssetFilterProxy(QSortFilterProxyModel):
    """Simple name/type filtering for the Assets table."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._needle: str = ""
        self._integrity: Optional[str] = None

    def set_search(self, text: str) -> None:
        self._needle = (text or "").strip().lower()
        self.invalidateFilter()

    def set_integrity_filter(self, integrity: Optional[str]) -> None:
        # In Assets mode we interpret integrity as a missing-files filter.
        # - OK: only assets with missing_count==0
        # - MISSING: only assets with missing_count>0
        # - other/None: no filter
        self._integrity = None if integrity is None else str(integrity).strip().upper() or None
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:  # noqa: N802
        model = self.sourceModel()
        if model is None:
            return True

        # Integrity filter (missing_count semantics).
        integ = self._integrity
        if integ in {"OK", "MISSING"}:
            # missing_count stored on column 0
            mc = int(model.index(source_row, 0).data(Qt.ItemDataRole.UserRole + 2) or 0)
            if integ == "OK" and mc != 0:
                return False
            if integ == "MISSING" and mc <= 0:
                return False

        needle = self._needle
        if not needle:
            return True

        # Columns: 0 name, 1 type, 2 tags, 3 latest, 4 versions, 5 files, 6 health, 7 key (hidden)
        name = str(model.index(source_row, 0).data() or "").lower()
        typ = str(model.index(source_row, 1).data() or "").lower()
        tags = str(model.index(source_row, 2).data() or "").lower() if model.columnCount() > 2 else ""
        key = str(model.index(source_row, 7).data() or "").lower() if model.columnCount() > 7 else ""
        return needle in name or needle in typ or (tags and needle in tags) or (key and needle in key)


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
        self._actions = LibraryActions(context, parent=self)
        self._storage_id: Optional[int] = None
        self._selected = _Selected()
        self._pending_restore = _Selected()
        self._show_hidden_columns: bool = False

        self._asset_model = QStandardItemModel(self)
        self._asset_model.setHorizontalHeaderLabels(
            [
                "Name",
                "Type",
                "Tags",
                "Latest Version",
                "Versions",
                "Files",
                "Health",
                "Key",
                "Asset ID",
                "Storage ID",
            ]
        )
        self._asset_proxy = _AssetFilterProxy(self)
        self._asset_proxy.setSourceModel(self._asset_model)

        self._chk_show_discarded = QCheckBox("Show discarded", self)
        self._chk_show_discarded.setChecked(False)

        self._versions_list = QListWidget(self)
        self._versions_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._versions_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._versions_list.customContextMenuRequested.connect(self._on_versions_context_menu)
        self._versions_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._versions_list.customContextMenuRequested.connect(self._on_versions_context_menu)

        self._files_model = QStandardItemModel(self)
        self._files_model.setHorizontalHeaderLabels(["Path", "State"])
        self._files_view = QTableView(self)
        self._files_view.setModel(self._files_model)
        self._files_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._files_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._files_view.setSortingEnabled(True)
        self._files_view.horizontalHeader().setStretchLastSection(True)
        self._files_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._files_view.customContextMenuRequested.connect(self._on_files_context_menu)

        self._build_ui()
        self._wire_events()

    # -----------------
    # Public API
    # -----------------

    def set_storage_id(self, storage_id: Optional[int]) -> None:
        self._storage_id = None if storage_id is None else int(storage_id)

    def set_search_text(self, text: str) -> None:
        self._asset_proxy.set_search(text)

    def set_integrity_filter(self, integrity: Optional[str]) -> None:
        self._asset_proxy.set_integrity_filter(integrity)

    def set_show_hidden_columns(self, show: bool) -> None:
        self._show_hidden_columns = bool(show)
        # Hidden columns start at "Key".
        for col in range(7, self._asset_model.columnCount()):
            self._assets_view.setColumnHidden(col, not self._show_hidden_columns)

    def set_pending_restore(self, *, asset_id: Optional[int], version_id: Optional[int]) -> None:
        self._pending_restore.asset_id = None if asset_id is None else int(asset_id)
        self._pending_restore.version_id = None if version_id is None else int(version_id)

    def get_selection(self) -> _Selected:
        return _Selected(asset_id=self._selected.asset_id, version_id=self._selected.version_id)

    def refresh(self) -> None:
        """Refresh assets list (and detail panes if selection remains valid)."""
        # Prefer any pending restore request; fall back to current selection.
        prev_asset = self._pending_restore.asset_id or self._selected.asset_id
        prev_version = self._pending_restore.version_id or self._selected.version_id
        self._pending_restore = _Selected()

        rows = list_assets(self.context.db_connection, storage_id=self._storage_id)
        asset_ids = [int(r.asset_id) for r in rows]
        tag_map: Dict[int, List[Tag]] = {}
        try:
            tag_map = list_tags_for_asset_ids(self.context.db_connection, asset_ids)
        except Exception:
            tag_map = {}

        self._asset_model.removeRows(0, self._asset_model.rowCount())
        for r in rows:
            health = "OK" if int(r.missing_count) == 0 else f"{int(r.missing_count)} MISSING"
            tags = tag_map.get(int(r.asset_id), [])
            tag_pairs = [(str(t.name), str(t.color)) for t in tags]
            tag_text = ", ".join([p[0] for p in tag_pairs])
            items = [
                QStandardItem(r.name),
                QStandardItem(r.type),
                QStandardItem(tag_text),
                QStandardItem(r.latest_version_label or ""),
                QStandardItem(str(r.version_count)),
                QStandardItem(str(r.file_count)),
                QStandardItem(health),
                QStandardItem(str(r.key)),
                QStandardItem(str(r.asset_id)),
                QStandardItem(str(r.storage_id)),
            ]
            for it in items:
                it.setEditable(False)
            # store ids on first item
            items[0].setData(int(r.asset_id), Qt.ItemDataRole.UserRole)
            items[0].setData(int(r.storage_id), Qt.ItemDataRole.UserRole + 1)
            items[0].setData(int(r.missing_count), Qt.ItemDataRole.UserRole + 2)
            # store tag payload on the tags cell for the delegate
            items[2].setData(tag_pairs, TAG_PAYLOAD_ROLE)
            self._asset_model.appendRow(items)

        # Re-apply hidden column state (model refresh can reset header/view state on some Qt builds).
        self.set_show_hidden_columns(self._show_hidden_columns)

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

        self._assets_view = _NoCollapseOnRightClickTableView(left)
        self._assets_view.setModel(self._asset_proxy)
        self._assets_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._assets_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._assets_view.setSortingEnabled(True)
        self._assets_view.horizontalHeader().setStretchLastSection(True)
        self._assets_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._assets_view.customContextMenuRequested.connect(self._on_assets_context_menu)
        # Tag chips delegate on the Tags column.
        self._assets_view.setItemDelegateForColumn(2, TagChipsDelegate(self._assets_view))
        left_layout.addWidget(self._assets_view)

        # Default: hide internal columns in v0.
        self.set_show_hidden_columns(False)

        # Default hidden columns.
        self.set_show_hidden_columns(False)

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
        v_layout.addWidget(self._chk_show_discarded)
        v_layout.addWidget(self._versions_list)

        # Files table
        files_wrap = QWidget(inner)
        f_layout = QVBoxLayout(files_wrap)
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.addWidget(QLabel("Files", files_wrap))
        f_layout.addWidget(self._files_view)
        self._files_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._files_view.customContextMenuRequested.connect(self._on_files_context_menu)

        inner.setStretchFactor(0, 0)
        inner.setStretchFactor(1, 1)

    def _wire_events(self) -> None:
        sel = self._assets_view.selectionModel()
        if sel is not None:
            sel.selectionChanged.connect(lambda *_: self._on_asset_selection_changed())
        self._versions_list.currentItemChanged.connect(lambda *_: self._on_version_selection_changed())
        self._chk_show_discarded.stateChanged.connect(lambda *_: self._refresh_detail_preserve_selection())

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
        # Important: user can click any column; ids are stored on column 0.
        sel = self._assets_view.selectionModel()
        idx0 = None

        # Prefer the current index row for detail (multi-select friendly).
        cur = self._assets_view.currentIndex()
        if cur.isValid():
            idx0 = self._asset_proxy.index(cur.row(), 0)

        # Fallback: first selected row.
        if (idx0 is None or not idx0.isValid()) and sel is not None:
            rows = sel.selectedRows(0)
            if rows:
                idx0 = rows[0]

        if idx0 is None or not idx0.isValid():
            self._set_asset_detail(None, None)
            return

        asset_id = int(idx0.data(Qt.ItemDataRole.UserRole) or 0)
        if asset_id <= 0:
            self._set_asset_detail(None, None)
            return

        self._selected.asset_id = asset_id
        self._selected.version_id = None

        # Update title
        name = str(self._asset_proxy.index(idx0.row(), 0).data() or "")
        typ = str(self._asset_proxy.index(idx0.row(), 1).data() or "")
        self._asset_title.setText(f"{name}  —  {typ}")

        # Load versions
        vers = list_versions(self.context.db_connection, asset_id=asset_id)
        visible = self._visible_versions(vers)
        self._populate_versions(visible)

        # Select latest visible by default
        if visible:
            latest = visible[-1]
            self._select_version_id(latest.id)
        else:
            self._files_model.removeRows(0, self._files_model.rowCount())

    def _visible_versions(self, versions: List[Version]) -> List[Version]:
        """Filter versions based on the "show discarded" toggle."""

        if self._chk_show_discarded.isChecked():
            return list(versions)
        return [v for v in versions if int(getattr(v, "is_discarded", 0) or 0) == 0]

    def _refresh_detail_preserve_selection(self) -> None:
        """Refresh version list without clobbering the current selection."""

        if self._selected.asset_id is None:
            return

        prev_vid = self._selected.version_id
        vers = list_versions(self.context.db_connection, asset_id=int(self._selected.asset_id))
        visible = self._visible_versions(vers)
        self._populate_versions(visible)
        if prev_vid is not None:
            self._select_version_id(int(prev_vid))
        # Trigger file refresh (or clear) after potential selection change.
        self._on_version_selection_changed()

    def _populate_versions(self, versions: List[Version]) -> None:
        self._versions_list.clear()
        for v in versions:
            text = str(v.label)
            ul = str(getattr(v, "user_label", "") or "").strip()
            if ul:
                text = f"{text}  —  {ul}"
            if int(getattr(v, "is_discarded", 0) or 0):
                text = f"{text}  [discarded]"
            it = QListWidgetItem(text)
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

    # -----------------
    # Context menus
    # -----------------

    def _current_asset_row_data(self) -> Tuple[int, str, str]:
        """Return (asset_id, name, key) for the current selection."""
        idx = self._assets_view.currentIndex()
        if not idx.isValid():
            return 0, "", ""
        idx0 = self._asset_proxy.index(idx.row(), 0)
        asset_id = int(idx0.data(Qt.ItemDataRole.UserRole) or 0)
        name = str(self._asset_proxy.index(idx.row(), 0).data() or "")
        key = str(self._asset_proxy.index(idx.row(), 7).data() or "")
        return asset_id, name, key

    def _selected_asset_ids(self) -> List[int]:
        sel = self._assets_view.selectionModel()
        if sel is None:
            return []
        ids: List[int] = []
        for idx in sel.selectedRows(0):
            try:
                aid = int(idx.data(Qt.ItemDataRole.UserRole) or 0)
            except Exception:
                aid = 0
            if aid > 0:
                ids.append(aid)
        # stable order for logs
        return sorted(set(ids))

    def _representative_file_id_for_current_asset(self) -> Optional[int]:
        """Best-effort file_id for asset location actions."""
        # Prefer a currently selected file in the files table.
        fidx = self._files_view.currentIndex()
        if fidx.isValid():
            it = self._files_model.item(int(fidx.row()), 0)
            if it is not None:
                fid = int(it.data(Qt.ItemDataRole.UserRole) or 0)
                if fid > 0:
                    return fid

        # Fall back to the first visible file row.
        if self._files_model.rowCount() > 0:
            it = self._files_model.item(0, 0)
            if it is not None:
                fid = int(it.data(Qt.ItemDataRole.UserRole) or 0)
                if fid > 0:
                    return fid
        return None

    def _current_version_id(self) -> Optional[int]:
        item = self._versions_list.currentItem()
        if item is None:
            return None
        try:
            vid = int(item.data(Qt.ItemDataRole.UserRole) or 0)
        except Exception:
            vid = 0
        return vid if vid > 0 else None

    def _on_versions_context_menu(self, pos) -> None:
        # No version selected → nothing to edit.
        item = self._versions_list.itemAt(pos)
        if item is None:
            return

        try:
            vid = int(item.data(Qt.ItemDataRole.UserRole) or 0)
        except Exception:
            vid = 0
        if vid <= 0:
            return

        conn = self.context.db_connection
        if conn is None:
            return

        v = get_version(conn, version_id=int(vid))

        menu = QMenu(self)

        act_set_label = menu.addAction("Set label…")
        act_set_number = menu.addAction("Edit version number…")
        menu.addSeparator()

        if int(getattr(v, "is_discarded", 0) or 0):
            act_discard = menu.addAction("Restore version")
        else:
            act_discard = menu.addAction("Mark version as discarded")

        def _apply_and_refresh(new_vid: Optional[int] = None) -> None:
            # Preserve selection through refresh.
            self._pending_restore.asset_id = self._selected.asset_id
            self._pending_restore.version_id = new_vid if new_vid is not None else vid
            self.refresh()

        def _on_set_label() -> None:
            current = str(getattr(v, "user_label", "") or "")
            text, ok = QInputDialog.getText(self, "Version label", "Label (optional):", text=current)
            if not ok:
                return
            try:
                set_version_user_label(conn, version_id=int(vid), user_label=str(text))
            except Exception as e:
                QMessageBox.warning(self, "AssetHub", f"Failed to set label: {e}")
                return
            _apply_and_refresh()

        def _on_set_number() -> None:
            val, ok = QInputDialog.getInt(
                self,
                "Version number",
                "Version number (used for vNN sorting):",
                value=int(getattr(v, "sort_key", 1) or 1),
                minValue=1,
                maxValue=999999,
            )
            if not ok:
                return
            try:
                set_version_sort_key(conn, version_id=int(vid), sort_key=int(val))
            except Exception as e:
                QMessageBox.warning(self, "AssetHub", f"Failed to update version number: {e}")
                return
            _apply_and_refresh()

        def _on_toggle_discard() -> None:
            target = 0 if int(getattr(v, "is_discarded", 0) or 0) else 1
            try:
                set_version_discarded(conn, version_id=int(vid), is_discarded=target)
            except Exception as e:
                QMessageBox.warning(self, "AssetHub", f"Failed to update discard state: {e}")
                return
            # If we just discarded the selected version and "show discarded" is off,
            # selection might disappear; keep asset selection, fall back to latest.
            self._pending_restore.asset_id = self._selected.asset_id
            self._pending_restore.version_id = vid
            self.refresh()

        act_set_label.triggered.connect(_on_set_label)
        act_set_number.triggered.connect(_on_set_number)
        act_discard.triggered.connect(_on_toggle_discard)

        menu.exec(self._versions_list.viewport().mapToGlobal(pos))

    def _on_assets_context_menu(self, pos) -> None:
        idx = self._assets_view.indexAt(pos)
        if not idx.isValid():
            return

        # Preserve multi-selection on right-click.
        sel = self._assets_view.selectionModel()
        if sel is not None:
            # Same issue as above: when selecting rows, a right-click on a
            # different column can look "unselected" if we check the exact
            # index. Determine selection by row (or by column 0).
            idx0 = idx.siblingAtColumn(0)
            row_selected = sel.isRowSelected(idx.row(), idx.parent())
            if not (row_selected or sel.isSelected(idx0)):
                # Replace selection with the clicked row.
                sel.select(
                    idx0,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
            # IMPORTANT: do not call view.setCurrentIndex() here; on some Qt builds
            # that can collapse multi-selection. Update current index through the
            # selection model without changing selection.
            sel.setCurrentIndex(idx0, QItemSelectionModel.SelectionFlag.NoUpdate)

        asset_id, name, key = self._current_asset_row_data()
        if asset_id <= 0:
            return

        menu = QMenu(self)

        act_reveal = menu.addAction("Open asset location (reveal in Explorer)")
        act_reveal.triggered.connect(lambda: self._actions.reveal_in_explorer(self._representative_file_id_for_current_asset()))

        menu.addSeparator()

        tags_menu = menu.addMenu("Tags")
        act_edit_tags = tags_menu.addAction("Edit tags…")
        act_edit_tags.triggered.connect(self._on_edit_tags)
        tags_menu.addSeparator()
        act_manage_tags = tags_menu.addAction("Manage tags…")
        act_manage_tags.triggered.connect(self._on_manage_tags)

        menu.addSeparator()

        copy_menu = menu.addMenu("Copy")
        act_c_name = copy_menu.addAction("Copy asset name")
        act_c_name.triggered.connect(lambda: set_clipboard_text(name))

        act_c_key = copy_menu.addAction("Copy asset key")
        act_c_key.triggered.connect(lambda: set_clipboard_text(key))

        act_c_id = copy_menu.addAction("Copy asset id")
        act_c_id.triggered.connect(lambda: set_clipboard_text(str(asset_id)))

        menu.addSeparator()

        act_dissolve = menu.addAction("Dissolve asset (remove from database)")
        act_dissolve.triggered.connect(lambda: self._dissolve_asset(asset_id))

        menu.exec(self._assets_view.viewport().mapToGlobal(pos))

    # -----------------
    # Tag actions
    # -----------------

    def _on_manage_tags(self) -> None:
        dlg = TagManagerDialog(parent=self, context=self.context)
        dlg.exec()
        self.refresh()

    def _on_edit_tags(self) -> None:
        """Edit tags for the current multi-selection (tri-state dialog)."""
        conn = self.context.db_connection
        if conn is None:
            return

        asset_ids = self._selected_asset_ids()
        if not asset_ids:
            return

        tags = list_tags(conn)
        if not tags:
            # No tags exist yet; open manager.
            self._on_manage_tags()
            return

        current = list_tags_for_asset_ids(conn, asset_ids)

        # Compute per-tag membership across the selection.
        sets = [set(int(t.id) for t in current.get(aid, [])) for aid in asset_ids]
        all_ids: Set[int] = set.intersection(*sets) if sets else set()
        any_ids: Set[int] = set.union(*sets) if sets else set()

        initial_states: Dict[int, Qt.CheckState] = {}
        for t in tags:
            tid = int(t.id)
            if tid in all_ids:
                initial_states[tid] = Qt.CheckState.Checked
            elif tid in any_ids:
                initial_states[tid] = Qt.CheckState.PartiallyChecked
            else:
                initial_states[tid] = Qt.CheckState.Unchecked

        dlg = TagSelectDialog(
            parent=self,
            title="Edit Tags",
            tags=tags,
            initial_states=initial_states,
            allow_tristate=True,
        )
        if dlg.exec() != TagSelectDialog.DialogCode.Accepted:
            return

        add_ids, remove_ids = dlg.changes()
        if not add_ids and not remove_ids:
            return

        inserted = 0
        deleted = 0
        try:
            if add_ids:
                inserted = add_tags_to_assets(conn, asset_ids=asset_ids, tag_ids=add_ids, commit=True)
            if remove_ids:
                deleted = remove_tags_from_assets(conn, asset_ids=asset_ids, tag_ids=remove_ids, commit=True)
        except Exception:
            return

        # Human-friendly tag names for logging.
        tag_by_id = {int(t.id): t for t in tags}
        add_names = [tag_by_id[tid].name for tid in add_ids if tid in tag_by_id]
        remove_names = [tag_by_id[tid].name for tid in remove_ids if tid in tag_by_id]

        try:
            parts = []
            if add_names:
                parts.append(f"+{add_names}")
            if remove_names:
                parts.append(f"-{remove_names}")
            self.context.log.info(f"Updated tags for {len(asset_ids)} asset(s): " + " ".join(parts))
        except Exception:
            pass

        try:
            self.context.event_hub.db_changed.emit(
                DbChanged(
                    reason="asset_tags_edited",
                    payload={
                        "asset_ids": asset_ids,
                        "add_tag_ids": add_ids,
                        "remove_tag_ids": remove_ids,
                        "new_links": inserted,
                        "removed_links": deleted,
                    },
                )
            )
        except Exception:
            pass

        self.refresh()



    def _dissolve_asset(self, asset_id: int) -> None:
        aid = int(asset_id)
        if aid <= 0:
            return
        conn = self.context.db_connection
        if conn is None:
            return

        # Gather counts for UI + logging.
        row = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM version WHERE asset_id=?),
              (SELECT COUNT(*) FROM file WHERE version_id IN (SELECT id FROM version WHERE asset_id=?))
            """,
            (aid, aid),
        ).fetchone()
        vcount = int(row[0]) if row else 0
        fcount = int(row[1]) if row else 0

        resp = QMessageBox.question(
            self,
            "Dissolve asset",
            "Dissolve this asset group?\n\n"
            f"- Versions: {vcount}\n"
            f"- Attached files: {fcount}\n\n"
            "This removes the asset + its versions from the database and releases all files (they remain as unowned file records).",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        try:
            with conn:
                conn.execute("DELETE FROM asset WHERE id=?;", (aid,))
        except Exception:
            return

        try:
            self.context.log.info(f"Dissolved asset id={aid} (versions={vcount}, files_released={fcount}).")
        except Exception:
            pass

        try:
            self.context.event_hub.db_changed.emit(
                DbChanged(
                    reason="asset_dissolved",
                    payload={"asset_id": aid, "version_count": vcount, "released_files": fcount},
                )
            )
        except Exception:
            pass

        # Local refresh in case no listeners exist yet.
        self.refresh()

    def _on_files_context_menu(self, pos) -> None:
        idx = self._files_view.indexAt(pos)
        if not idx.isValid():
            return

        # Preserve multi-selection on right-click.
        sel = self._files_view.selectionModel()
        if sel is not None:
            if not sel.isSelected(idx):
                sel.select(
                    idx,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
                )
            sel.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.NoUpdate)

        # Gather selection.
        selected_rows = []
        selected_ids: List[int] = []
        if sel is not None:
            for r in sel.selectedRows(0):
                it = self._files_model.item(int(r.row()), 0)
                st = self._files_model.item(int(r.row()), 1)
                fid = int(it.data(Qt.ItemDataRole.UserRole) or 0) if it is not None else 0
                state = str(st.text() if st is not None else "")
                if fid > 0:
                    selected_ids.append(fid)
                    selected_rows.append((fid, state))

        if not selected_ids:
            return

        # Current id from clicked row.
        current_item = self._files_model.item(int(idx.row()), 0)
        current_id = int(current_item.data(Qt.ItemDataRole.UserRole) or 0) if current_item is not None else None

        all_missing = all(str(s).upper() == "MISSING" for _fid, s in selected_rows) and bool(selected_rows)

        menu = QMenu(self)

        act_open_file = menu.addAction("Open file with system default")
        act_open_file.triggered.connect(lambda: self._actions.open_file_with_default(current_id))

        act_reveal = menu.addAction("Open file location (reveal in Explorer)")
        act_reveal.triggered.connect(lambda: self._actions.reveal_in_explorer(current_id))

        act_open_root = menu.addAction("Open storage root location")
        act_open_root.triggered.connect(lambda: self._actions.open_storage_root_location(current_id))

        menu.addSeparator()

        copy_menu = menu.addMenu("Copy")
        act_c_name = copy_menu.addAction("Copy file name")
        act_c_name.triggered.connect(lambda: self._actions.copy_file_names(selected_ids))

        act_c_abs_dir = copy_menu.addAction("Copy absolute path (file name excluded)")
        act_c_abs_dir.triggered.connect(lambda: self._actions.copy_abs_dirs(selected_ids))

        act_c_rel_dir = copy_menu.addAction("Copy relative path (file name excluded)")
        act_c_rel_dir.triggered.connect(lambda: self._actions.copy_rel_dirs(selected_ids))

        act_c_checksum = copy_menu.addAction("Copy checksum")
        act_c_checksum.triggered.connect(lambda: self._actions.copy_checksums_sha256(selected_ids))

        menu.addSeparator()

        act_health = menu.addAction("Run health check")
        act_health.triggered.connect(lambda: self._actions.run_health_check(selected_ids))

        act_remove = menu.addAction("Remove from database")
        act_remove.setEnabled(all_missing)

        def _do_remove() -> None:
            if not all_missing:
                return
            resp = QMessageBox.question(
                self,
                "Remove from database",
                f"Remove {len(selected_ids)} missing record(s) from the database?\n\n"
                "This does not delete files from disk.",
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
            try:
                self._actions.remove_missing_from_database(selected_ids)
            except Exception:
                return

        act_remove.triggered.connect(_do_remove)

        menu.exec(self._files_view.viewport().mapToGlobal(pos))
