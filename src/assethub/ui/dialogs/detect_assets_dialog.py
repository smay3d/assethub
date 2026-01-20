"""Detect Assets proposals dialog (Stage 8.4).

This dialog presents detection proposals (generated in Stage 8.3) and lets the
user optionally adjust:
  - asset type (generic / image_sequence / texture_set)
  - asset display name
  - which file members to include

The dialog itself performs no database I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from assethub.core.detection.engine import DetectionProposal, DetectionResult
from assethub.core.detection.apply import ApplyItem


_TYPE_LABELS = {
    "generic": "Generic",
    "image_sequence": "Image Sequence",
    "texture_set": "Texture Set",
}


@dataclass
class _EditableProposal:
    type: str
    key: str
    suggested_name: str
    reason: str
    file_ids: List[int]
    selected_file_ids: List[int]
    demoted_from: Optional[str] = None


class DetectAssetsDialog(QDialog):
    """Modal dialog for previewing and applying detection proposals."""

    def __init__(
        self,
        *,
        parent: Optional[QWidget],
        storage_label: str,
        detection: DetectionResult,
        file_id_to_relpath: Dict[int, str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Detect Assets")
        self.setModal(True)
        self.resize(980, 640)

        self._file_map = dict(file_id_to_relpath)
        self._items: List[_EditableProposal] = []
        for p in detection.proposals:
            fids = list(p.file_ids)
            self._items.append(
                _EditableProposal(
                    type=str(p.type),
                    key=str(p.key),
                    suggested_name=str(p.suggested_name),
                    reason=str(p.reason),
                    file_ids=fids,
                    selected_file_ids=list(fids),
                )
            )

        self._build_ui(storage_label=storage_label, detection=detection)
        self._populate_list()
        if self.list_proposals.count() > 0:
            self.list_proposals.setCurrentRow(0)

    # -------------------------
    # Public API
    # -------------------------

    def build_apply_items(self) -> List[ApplyItem]:
        out: List[ApplyItem] = []
        for it in self._items:
            fids = [int(x) for x in it.selected_file_ids if int(x) > 0]
            if not fids:
                continue
            out.append(ApplyItem(type=it.type, key=it.key, name=it.suggested_name, file_ids=fids))
        return out

    # -------------------------
    # UI
    # -------------------------

    def _build_ui(self, *, storage_label: str, detection: DetectionResult) -> None:
        root = QVBoxLayout(self)

        header = QLabel(f"Storage Root: <b>{storage_label}</b>")
        header.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(header)

        summ = detection.summary
        summary_line = (
            f"Files considered: {summ.total_considered} | "
            f"Skipped owned: {summ.skipped_owned} | "
            f"Skipped excluded: {summ.skipped_excluded} | "
            f"Proposals: {len(detection.proposals)}"
        )
        root.addWidget(QLabel(summary_line))

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(splitter, 1)

        # Left: proposal list
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.list_proposals = QListWidget(left)
        self.list_proposals.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_proposals.currentRowChanged.connect(self._on_select_proposal)
        left_layout.addWidget(QLabel("Proposals"))
        left_layout.addWidget(self.list_proposals, 1)

        splitter.addWidget(left)

        # Right: details
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Details form
        box = QGroupBox("Selected Proposal", right)
        form = QFormLayout(box)

        self.lbl_key = QLabel("-")
        self.lbl_reason = QLabel("-")
        self.lbl_reason.setWordWrap(True)

        self.combo_type = QComboBox(box)
        self.combo_type.addItem(_TYPE_LABELS["generic"], "generic")
        self.combo_type.addItem(_TYPE_LABELS["image_sequence"], "image_sequence")
        self.combo_type.addItem(_TYPE_LABELS["texture_set"], "texture_set")
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)

        self.edit_name = QLineEdit(box)
        self.edit_name.textEdited.connect(self._on_name_edited)

        form.addRow("Type", self.combo_type)
        form.addRow("Name", self.edit_name)
        form.addRow("Key", self.lbl_key)
        form.addRow("Reason", self.lbl_reason)

        right_layout.addWidget(box)

        # File checklist
        files_box = QGroupBox("Files", right)
        files_layout = QVBoxLayout(files_box)
        self.list_files = QListWidget(files_box)
        self.list_files.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        files_layout.addWidget(self.list_files, 1)

        btns = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_none = QPushButton("Select None")
        self.btn_select_all.clicked.connect(self._on_select_all)
        self.btn_select_none.clicked.connect(self._on_select_none)
        btns.addWidget(self.btn_select_all)
        btns.addWidget(self.btn_select_none)
        btns.addStretch(1)
        files_layout.addLayout(btns)

        right_layout.addWidget(files_box, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        # Footer
        self._btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._btn_apply = self._btn_box.addButton("Apply", QDialogButtonBox.ButtonRole.AcceptRole)
        self._btn_apply.clicked.connect(self._on_apply_clicked)
        self._btn_box.rejected.connect(self.reject)
        root.addWidget(self._btn_box)

    def _populate_list(self) -> None:
        self.list_proposals.clear()
        for it in self._items:
            label = _TYPE_LABELS.get(it.type, it.type)
            count = len(it.selected_file_ids)
            text = f"{label}: {it.suggested_name}  ({count})"
            item = QListWidgetItem(text)
            self.list_proposals.addItem(item)

    def _refresh_list_row(self, row: int) -> None:
        if row < 0 or row >= len(self._items):
            return
        it = self._items[row]
        label = _TYPE_LABELS.get(it.type, it.type)
        count = len(it.selected_file_ids)
        text = f"{label}: {it.suggested_name}  ({count})"
        lw_item = self.list_proposals.item(row)
        if lw_item is not None:
            lw_item.setText(text)

    # -------------------------
    # Selection / editing
    # -------------------------

    @Slot(int)
    def _on_select_proposal(self, row: int) -> None:
        if row < 0 or row >= len(self._items):
            self._clear_detail()
            return
        it = self._items[row]

        self._set_combo_value(it.type)
        self.edit_name.setText(it.suggested_name)
        self.lbl_key.setText(it.key)
        self.lbl_reason.setText(it.reason)

        self._populate_files(it)

    def _clear_detail(self) -> None:
        self._set_combo_value("generic")
        self.edit_name.setText("")
        self.lbl_key.setText("-")
        self.lbl_reason.setText("-")
        self.list_files.clear()

    def _populate_files(self, it: _EditableProposal) -> None:
        self.list_files.clear()
        # Deterministic order by relative path, then id.
        fids = sorted(it.file_ids, key=lambda fid: (self._file_map.get(int(fid), ""), int(fid)))
        for fid in fids:
            rel = self._file_map.get(int(fid), f"(id={int(fid)})")
            cb = QCheckBox(rel)
            cb.setProperty("file_id", int(fid))
            cb.setChecked(int(fid) in set(int(x) for x in it.selected_file_ids))
            cb.stateChanged.connect(self._on_file_checkbox_changed)
            lw = QListWidgetItem(self.list_files)
            lw.setFlags(lw.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            self.list_files.addItem(lw)
            self.list_files.setItemWidget(lw, cb)

    def _current(self) -> Optional[_EditableProposal]:
        row = self.list_proposals.currentRow()
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row]

    def _set_combo_value(self, value: str) -> None:
        v = str(value)
        for i in range(self.combo_type.count()):
            if self.combo_type.itemData(i) == v:
                self.combo_type.blockSignals(True)
                self.combo_type.setCurrentIndex(i)
                self.combo_type.blockSignals(False)
                return

    @Slot()
    def _on_name_edited(self) -> None:
        it = self._current()
        if it is None:
            return
        it.suggested_name = self.edit_name.text().strip()
        self._refresh_list_row(self.list_proposals.currentRow())

    @Slot(int)
    def _on_type_changed(self, _idx: int) -> None:
        it = self._current()
        if it is None:
            return
        v = self.combo_type.currentData()
        it.type = str(v)
        self._refresh_list_row(self.list_proposals.currentRow())
        # Enforce demotion rule immediately if needed.
        self._enforce_texture_min_files(it)

    @Slot(int)
    def _on_file_checkbox_changed(self, _state: int) -> None:
        it = self._current()
        if it is None:
            return
        cb = self.sender()
        if not isinstance(cb, QCheckBox):
            return
        fid = cb.property("file_id")
        try:
            fid_i = int(fid)
        except Exception:
            return

        selected = set(int(x) for x in it.selected_file_ids)
        if cb.isChecked():
            selected.add(fid_i)
        else:
            selected.discard(fid_i)
        it.selected_file_ids = sorted(selected)
        self._refresh_list_row(self.list_proposals.currentRow())
        self._enforce_texture_min_files(it)

    @Slot()
    def _on_select_all(self) -> None:
        it = self._current()
        if it is None:
            return
        it.selected_file_ids = list(it.file_ids)
        self._populate_files(it)
        self._refresh_list_row(self.list_proposals.currentRow())
        self._enforce_texture_min_files(it)

    @Slot()
    def _on_select_none(self) -> None:
        it = self._current()
        if it is None:
            return
        it.selected_file_ids = []
        self._populate_files(it)
        self._refresh_list_row(self.list_proposals.currentRow())
        self._enforce_texture_min_files(it)

    def _enforce_texture_min_files(self, it: _EditableProposal) -> None:
        if it.type != "texture_set":
            return
        if len(it.selected_file_ids) >= 2:
            return
        it.demoted_from = "texture_set"
        it.type = "generic"
        self._set_combo_value("generic")
        self._refresh_list_row(self.list_proposals.currentRow())

    # -------------------------
    # Apply
    # -------------------------

    @Slot()
    def _on_apply_clicked(self) -> None:
        # Validate at least one proposal has files.
        apply_items = self.build_apply_items()
        if not apply_items:
            QMessageBox.information(self, "AssetHub", "No files are selected. Nothing to apply.")
            return
        self.accept()
