"""Simple file selection dialog.

Stage 9.3.3: used for binding files to an asset from the Assets view.

This is intentionally minimal (v0): a filter box and a checklist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


@dataclass(frozen=True)
class FileChoice:
    file_id: int
    label: str


class FileSelectDialog(QDialog):
    """Checklist picker with a simple text filter."""

    def __init__(self, *, parent=None, title: str = "Select Files", files: List[FileChoice]):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._files = list(files)

        root = QVBoxLayout(self)

        root.addWidget(QLabel("Filter:", self))
        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText("type to filter…")
        root.addWidget(self._filter)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        root.addWidget(self._list, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        root.addWidget(buttons)

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._filter.textChanged.connect(self._apply_filter)

        self._populate()
        self._apply_filter("")

    def _populate(self) -> None:
        self._list.clear()
        for c in self._files:
            it = QListWidgetItem(str(c.label), self._list)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, int(c.file_id))

    def _apply_filter(self, text: str) -> None:
        t = str(text or "").strip().lower()
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is None:
                continue
            s = str(it.text() or "").lower()
            it.setHidden(bool(t) and (t not in s))

    def selected_file_ids(self) -> List[int]:
        out: List[int] = []
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is None:
                continue
            if it.checkState() == Qt.CheckState.Checked:
                out.append(int(it.data(Qt.ItemDataRole.UserRole) or 0))
        return [i for i in out if i > 0]


def prompt_select_files(
    *,
    parent=None,
    title: str,
    files: List[FileChoice],
) -> Optional[List[int]]:
    if not files:
        return None
    dlg = FileSelectDialog(parent=parent, title=title, files=files)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    ids = dlg.selected_file_ids()
    return ids if ids else None
