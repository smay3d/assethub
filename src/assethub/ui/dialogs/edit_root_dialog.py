# src/assethub/ui/dialogs/edit_root_dialog.py
"""EditRootDialog — view and edit per-root scan exclusions."""

from __future__ import annotations

import sqlite3

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
        parent: QWidget | None = None,
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
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.clicked.connect(self._on_save)
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
        added = False
        for ext in parts:
            if not ext:
                continue
            if ext not in existing:
                self._list.addItem(QListWidgetItem(ext))
                existing.add(ext)
                added = True
        if added:
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
