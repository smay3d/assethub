# src/assethub/ui/models/file_table_model.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


@dataclass(frozen=True)
class FileRow:
    """A single file record row as displayed in the Library tab."""

    file_id: int
    storage_id: int
    version_id: Optional[int]
    storage_name: str
    relative_path: str
    filename: str
    integrity_state: str
    size_bytes: Optional[int]
    mtime_unix: Optional[float]
    created_at: str


@dataclass(frozen=True)
class _Column:
    key: str
    header: str
    default_visible: bool
    display: Callable[[FileRow], str]
    sort_value: Callable[[FileRow], Any]


def _fmt_size(size_bytes: Optional[int]) -> str:
    if size_bytes is None:
        return ""
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{int(size_bytes)} B"


def _fmt_mtime(mtime_unix: Optional[float]) -> str:
    if mtime_unix is None:
        return ""
    try:
        dt = datetime.fromtimestamp(float(mtime_unix))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


class FileTableModel(QAbstractTableModel):
    """Table model for Library tab file listing (Stage 7.2).

    Notes:
      - DisplayRole returns formatted, human-readable values.
      - UserRole returns raw values intended for sorting.
    """

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[FileRow] = []
        self._truncated: bool = False
        self._total_in_db: Optional[int] = None

        self._columns: List[_Column] = [
            _Column(
                key="file_id",
                header="File ID",
                default_visible=False,
                display=lambda r: str(r.file_id),
                sort_value=lambda r: int(r.file_id),
            ),
            _Column(
                key="storage_id",
                header="Storage ID",
                default_visible=False,
                display=lambda r: str(r.storage_id),
                sort_value=lambda r: int(r.storage_id),
            ),
            _Column(
                key="version_id",
                header="Version ID",
                default_visible=False,
                display=lambda r: "" if r.version_id is None else str(r.version_id),
                sort_value=lambda r: -1 if r.version_id is None else int(r.version_id),
            ),
            _Column(
                key="storage_name",
                header="Storage",
                default_visible=True,
                display=lambda r: r.storage_name,
                sort_value=lambda r: r.storage_name.lower(),
            ),
            _Column(
                key="filename",
                header="Filename",
                default_visible=True,
                display=lambda r: r.filename,
                sort_value=lambda r: r.filename.lower(),
            ),
            _Column(
                key="relative_path",
                header="Relative Path",
                default_visible=True,
                display=lambda r: r.relative_path,
                sort_value=lambda r: r.relative_path.lower(),
            ),
            _Column(
                key="size_human",
                header="Size",
                default_visible=True,
                display=lambda r: _fmt_size(r.size_bytes),
                sort_value=lambda r: -1 if r.size_bytes is None else int(r.size_bytes),
            ),
            _Column(
                key="mtime_human",
                header="Modified",
                default_visible=True,
                display=lambda r: _fmt_mtime(r.mtime_unix),
                sort_value=lambda r: -1.0 if r.mtime_unix is None else float(r.mtime_unix),
            ),
            _Column(
                key="integrity_state",
                header="Integrity",
                default_visible=True,
                display=lambda r: r.integrity_state,
                sort_value=lambda r: r.integrity_state.lower(),
            ),
            _Column(
                key="size_bytes",
                header="Raw size_bytes",
                default_visible=False,
                display=lambda r: "" if r.size_bytes is None else str(r.size_bytes),
                sort_value=lambda r: -1 if r.size_bytes is None else int(r.size_bytes),
            ),
            _Column(
                key="mtime_unix",
                header="Raw mtime_unix",
                default_visible=False,
                display=lambda r: "" if r.mtime_unix is None else f"{float(r.mtime_unix):.3f}",
                sort_value=lambda r: -1.0 if r.mtime_unix is None else float(r.mtime_unix),
            ),
            _Column(
                key="created_at",
                header="Created",
                default_visible=False,
                display=lambda r: r.created_at,
                sort_value=lambda r: r.created_at,
            ),
        ]

    # -----------------
    # Qt model API
    # -----------------

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802,E501
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._columns):
                return self._columns[section].header
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None
        row_i = index.row()
        col_i = index.column()
        if not (0 <= row_i < len(self._rows)):
            return None
        if not (0 <= col_i < len(self._columns)):
            return None

        row = self._rows[row_i]
        col = self._columns[col_i]

        if role == Qt.ItemDataRole.DisplayRole:
            return col.display(row)

        if role == Qt.ItemDataRole.UserRole:
            return col.sort_value(row)

        # Convenience: show relative path as tooltip.
        if role == Qt.ItemDataRole.ToolTipRole:
            return row.relative_path

        return None

    # -----------------
    # Helpers
    # -----------------

    @property
    def columns(self) -> List[_Column]:
        return self._columns

    def set_rows(self, rows: List[FileRow], *, total_in_db: Optional[int] = None, truncated: bool = False) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self._total_in_db = total_in_db
        self._truncated = bool(truncated)
        self.endResetModel()

    def row_data(self, row_index: int) -> Optional[FileRow]:
        if 0 <= row_index < len(self._rows):
            return self._rows[row_index]
        return None

    def file_id_for_row(self, row_index: int) -> Optional[int]:
        row = self.row_data(row_index)
        return None if row is None else int(row.file_id)

    @property
    def truncated(self) -> bool:
        return self._truncated

    @property
    def total_in_db(self) -> Optional[int]:
        return self._total_in_db
