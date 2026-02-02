"""Dialog for resolving version-number conflicts during detection apply.

Stage 9.2: Some multi-file assets can have mismatched version numbers across
their member files (e.g. albedo v03 + normal v05). Before writing to the DB,
we prompt the user to either:
  - Split into multiple versions (recommended)
  - Force all files into a single chosen version
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class VersionConflictResolution:
    mode: str  # 'split' or 'force'
    forced_version: Optional[int] = None


class VersionConflictDialog(QDialog):
    """Resolve a single version conflict."""

    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        asset_name: str,
        version_to_files: Dict[Optional[int], List[str]],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resolve Version Conflict")
        self.setModal(True)

        self._resolution: Optional[VersionConflictResolution] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel(f"Asset: <b>{asset_name}</b>")
        title.setTextFormat(Qt.RichText)
        root.addWidget(title)

        info = QLabel(
            "Multiple version numbers were detected across the selected files. "
            "Choose how you want AssetHub to handle this before applying."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        # Preview: list each detected version bucket.
        preview = QGroupBox("Detected versions")
        pv = QVBoxLayout(preview)
        pv.setContentsMargins(10, 10, 10, 10)
        pv.setSpacing(6)
        for vn in sorted([k for k in version_to_files.keys() if k is not None]):
            pv.addWidget(QLabel(f"v{int(vn):02d} ({len(version_to_files[vn])} file(s))"))
        if None in version_to_files:
            pv.addWidget(QLabel(f"Unversioned ({len(version_to_files[None])} file(s))"))
        root.addWidget(preview)

        # Options
        self._rb_split = QRadioButton("Split into separate versions (recommended)")
        self._rb_force = QRadioButton("Force all files into one version")
        self._rb_split.setChecked(True)
        root.addWidget(self._rb_split)
        root.addWidget(self._rb_force)

        force_row = QHBoxLayout()
        force_row.setContentsMargins(18, 0, 0, 0)
        force_row.setSpacing(8)
        force_row.addWidget(QLabel("Target:"))
        self._cmb_force = QComboBox()
        self._cmb_force.setEnabled(False)
        # Populate combo deterministically.
        for vn in sorted([k for k in version_to_files.keys() if k is not None]):
            self._cmb_force.addItem(f"v{int(vn):02d}", int(vn))
        if None in version_to_files:
            self._cmb_force.addItem("Unversioned", None)
        force_row.addWidget(self._cmb_force, 1)
        root.addLayout(force_row)

        # File list (optional context)
        files_list = QListWidget()
        files_list.setMinimumHeight(120)
        files_list.setSelectionMode(QListWidget.NoSelection)
        for vn, files in version_to_files.items():
            header = f"v{int(vn):02d}" if vn is not None else "Unversioned"
            it = QListWidgetItem(header)
            it.setFlags(Qt.ItemIsEnabled)
            it.setData(Qt.UserRole, None)
            files_list.addItem(it)
            for f in files:
                sub = QListWidgetItem(f"  {f}")
                sub.setFlags(Qt.ItemIsEnabled)
                files_list.addItem(sub)
        root.addWidget(files_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._rb_force.toggled.connect(self._on_force_toggled)

    def _on_force_toggled(self, checked: bool) -> None:
        self._cmb_force.setEnabled(bool(checked))

    def _on_accept(self) -> None:
        if self._rb_split.isChecked():
            self._resolution = VersionConflictResolution(mode="split")
        else:
            data = self._cmb_force.currentData()
            forced: Optional[int]
            if data is None:
                forced = None
            else:
                forced = int(data)
            self._resolution = VersionConflictResolution(mode="force", forced_version=forced)
        self.accept()

    def resolution(self) -> Optional[VersionConflictResolution]:
        return self._resolution
