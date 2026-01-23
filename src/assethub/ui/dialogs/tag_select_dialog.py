"""Tag selection / edit dialog.

Stage 9.1:
- originally used as a simple picker for bulk add/remove operations.

Stage 9.1.1:
- used as a single "Edit tags…" dialog that supports tri-state checkboxes for
  multi-asset selections:
    - Checked: tag is present on all selected assets
    - PartiallyChecked: tag is present on some selected assets
    - Unchecked: tag is present on none of the selected assets

This dialog does not touch the database; it receives Tag models + initial state
and reports intended add/remove changes for the caller to apply.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from assethub.core.model.tag import Tag


def _color_icon(hex_color: str) -> QIcon:
    px = QPixmap(12, 12)
    px.fill(Qt.GlobalColor.transparent)
    c = QColor(str(hex_color))
    if not c.isValid():
        c = QColor("#808080")
    px.fill(c)
    return QIcon(px)


class TagSelectDialog(QDialog):
    """Modal dialog for selecting/editing tags via checkboxes."""

    def __init__(
        self,
        *,
        parent: Optional[QWidget],
        title: str,
        tags: List[Tag],
        initial_states: Optional[Dict[int, Qt.CheckState]] = None,
        allow_tristate: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(title)
        self.resize(460, 560)

        self._tags = list(tags)
        self._allow_tristate = bool(allow_tristate)

        self._initial_states: Dict[int, Qt.CheckState] = dict(initial_states or {})
        self._touched: Set[int] = set()
        self._populating: bool = False

        self._build_ui()
        self._populate()

    # -----------------
    # Results
    # -----------------

    def selected_tag_ids(self) -> List[int]:
        """Return checked ids (legacy behavior; ignores tri-state partials)."""
        out: List[int] = []
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is None:
                continue
            if it.checkState() == Qt.CheckState.Checked:
                tid = int(it.data(Qt.ItemDataRole.UserRole) or 0)
                if tid > 0:
                    out.append(tid)
        return out

    def changes(self) -> Tuple[List[int], List[int]]:
        """Return (add_ids, remove_ids) based on user-touched checkbox changes."""
        add_ids: List[int] = []
        remove_ids: List[int] = []

        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is None:
                continue
            tid = int(it.data(Qt.ItemDataRole.UserRole) or 0)
            if tid <= 0 or tid not in self._touched:
                continue

            st = it.checkState()
            if st == Qt.CheckState.Checked:
                add_ids.append(tid)
            elif st == Qt.CheckState.Unchecked:
                remove_ids.append(tid)
            else:
                # If a user somehow ends on PartiallyChecked, treat it as no-op.
                pass

        return add_ids, remove_ids

    # -----------------
    # UI
    # -----------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        hdr = QLabel("Edit tags")
        hdr.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(hdr)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search tags…")
        self._search.textChanged.connect(self._apply_filter)
        root.addWidget(self._search)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._list.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._list, 1)

        self._btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._btn_ok = self._btn_box.addButton("Apply", QDialogButtonBox.ButtonRole.AcceptRole)
        self._btn_box.rejected.connect(self.reject)
        self._btn_ok.clicked.connect(self.accept)
        root.addWidget(self._btn_box)

    def _populate(self) -> None:
        self._populating = True
        try:
            self._list.clear()
            for t in self._tags:
                tid = int(t.id)
                text = str(t.name)
                it = QListWidgetItem(text)
                it.setData(Qt.ItemDataRole.UserRole, tid)

                flags = it.flags() | Qt.ItemFlag.ItemIsUserCheckable
                if self._allow_tristate:
                    flags = flags | Qt.ItemFlag.ItemIsAutoTristate
                it.setFlags(flags)

                st = self._initial_states.get(tid, Qt.CheckState.Unchecked)
                # If tristate not allowed, coerce partial -> unchecked.
                if (not self._allow_tristate) and st == Qt.CheckState.PartiallyChecked:
                    st = Qt.CheckState.Unchecked
                it.setCheckState(st)

                it.setIcon(_color_icon(t.color))
                self._list.addItem(it)

            self._apply_filter(self._search.text())
        finally:
            self._populating = False

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is None:
                continue
            if not needle:
                it.setHidden(False)
                continue
            it.setHidden(needle not in it.text().lower())

    def _on_item_changed(self, it: QListWidgetItem) -> None:
        if self._populating:
            return
        tid = int(it.data(Qt.ItemDataRole.UserRole) or 0)
        if tid > 0:
            self._touched.add(tid)
