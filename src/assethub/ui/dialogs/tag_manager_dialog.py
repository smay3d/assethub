"""Tag manager dialog.

Stage 9.1: provides CRUD for tags (name + semantic color).

This dialog performs database I/O through core.db.tags helpers.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from assethub.context import AppContext
from assethub.core.db.tags import create_tag, delete_tag, list_tags, rename_tag, set_tag_color


class TagManagerDialog(QDialog):
    """Modal dialog to create, rename, recolor, and delete tags."""

    def __init__(self, *, parent: Optional[QWidget], context: AppContext) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Manage Tags")
        self.resize(560, 520)
        self.context = context

        self._build_ui()
        self.refresh()

    # -----------------
    # Public API
    # -----------------

    def refresh(self) -> None:
        conn = self.context.db_connection
        if conn is None:
            return

        tags = list_tags(conn)
        self._table.setRowCount(0)
        for t in tags:
            r = self._table.rowCount()
            self._table.insertRow(r)

            it_name = QTableWidgetItem(str(t.name))
            it_name.setData(Qt.ItemDataRole.UserRole, int(t.id))
            it_name.setFlags(it_name.flags() & ~Qt.ItemFlag.ItemIsEditable)

            it_color = QTableWidgetItem(str(t.color))
            it_color.setFlags(it_color.flags() & ~Qt.ItemFlag.ItemIsEditable)
            qc = QColor(str(t.color))
            if qc.isValid():
                it_color.setBackground(qc)

            self._table.setItem(r, 0, it_name)
            self._table.setItem(r, 1, it_color)

        self._table.resizeColumnsToContents()

    # -----------------
    # UI
    # -----------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        root.addWidget(QLabel("Create, rename, recolor, or delete tags."))

        self._table = QTableWidget(self)
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Name", "Color"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("Add")
        self._btn_rename = QPushButton("Rename")
        self._btn_color = QPushButton("Set Color")
        self._btn_delete = QPushButton("Delete")
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_rename)
        btn_row.addWidget(self._btn_color)
        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self._btn_add.clicked.connect(self._on_add)
        self._btn_rename.clicked.connect(self._on_rename)
        self._btn_color.clicked.connect(self._on_set_color)
        self._btn_delete.clicked.connect(self._on_delete)

        self._btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._btn_box.rejected.connect(self.reject)
        root.addWidget(self._btn_box)

    def _selected_tag_id(self) -> int:
        rows = self._table.selectionModel().selectedRows(0)
        if not rows:
            return 0
        idx = rows[0]
        it = self._table.item(int(idx.row()), 0)
        return int(it.data(Qt.ItemDataRole.UserRole) or 0) if it is not None else 0

    def _selected_tag_name(self) -> str:
        rows = self._table.selectionModel().selectedRows(0)
        if not rows:
            return ""
        it = self._table.item(int(rows[0].row()), 0)
        return str(it.text()) if it is not None else ""

    # -----------------
    # Actions
    # -----------------

    def _on_add(self) -> None:
        conn = self.context.db_connection
        if conn is None:
            return

        name, ok = QInputDialog.getText(self, "Add Tag", "Tag name:")
        if not ok:
            return
        name = str(name or "").strip()
        if not name:
            return

        color = QColorDialog.getColor(QColor("#808080"), self, "Tag Color")
        if not color.isValid():
            return
        hex_color = color.name().lower()

        try:
            create_tag(conn, name=name, color=hex_color, commit=True)
        except Exception as e:
            QMessageBox.warning(self, "Add Tag", f"Failed to add tag:\n\n{e}")
            return

        self.refresh()

    def _on_rename(self) -> None:
        conn = self.context.db_connection
        if conn is None:
            return
        tid = self._selected_tag_id()
        if tid <= 0:
            return

        current = self._selected_tag_name()
        new_name, ok = QInputDialog.getText(self, "Rename Tag", "New name:", text=current)
        if not ok:
            return
        new_name = str(new_name or "").strip()
        if not new_name or new_name == current:
            return

        try:
            rename_tag(conn, tag_id=tid, new_name=new_name, commit=True)
        except Exception as e:
            QMessageBox.warning(self, "Rename Tag", f"Failed to rename tag:\n\n{e}")
            return

        self.refresh()

    def _on_set_color(self) -> None:
        conn = self.context.db_connection
        if conn is None:
            return
        tid = self._selected_tag_id()
        if tid <= 0:
            return

        # Seed picker with current color if possible.
        it_color = self._table.item(int(self._table.currentRow()), 1)
        seed = QColor("#808080")
        if it_color is not None:
            qc = QColor(str(it_color.text()))
            if qc.isValid():
                seed = qc

        color = QColorDialog.getColor(seed, self, "Tag Color")
        if not color.isValid():
            return
        hex_color = color.name().lower()

        try:
            set_tag_color(conn, tag_id=tid, color=hex_color, commit=True)
        except Exception as e:
            QMessageBox.warning(self, "Set Tag Color", f"Failed to set color:\n\n{e}")
            return

        self.refresh()

    def _on_delete(self) -> None:
        conn = self.context.db_connection
        if conn is None:
            return
        tid = self._selected_tag_id()
        if tid <= 0:
            return

        name = self._selected_tag_name()
        resp = QMessageBox.question(
            self,
            "Delete Tag",
            f"Delete tag '{name}'?\n\nThis will remove it from all assets.",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        try:
            delete_tag(conn, tag_id=tid, commit=True)
        except Exception as e:
            QMessageBox.warning(self, "Delete Tag", f"Failed to delete tag:\n\n{e}")
            return

        self.refresh()
