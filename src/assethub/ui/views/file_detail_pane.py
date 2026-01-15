# src/assethub/ui/views/file_detail_pane.py

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QGuiApplication, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QToolButton,
    QSizePolicy,
    QScrollArea,
    QSplitter,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)


SUPPORTED_PREVIEW_FORMATS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
SUPPORTED_PREVIEW_TEXT = (
    "Preview unavailable. Supported formats: "
    + " ".join(SUPPORTED_PREVIEW_FORMATS)
)


@dataclass(frozen=True)
class FileDetails:
    file_id: int
    version_id: Optional[int]
    storage_id: int
    storage_name: str
    storage_root_path: Optional[str]
    storage_status: str

    relative_path: str
    filename: str
    integrity_state: str
    size_bytes: Optional[int]
    mtime_unix: Optional[float]
    created_at: str

    absolute_path: Optional[str]


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


def compute_absolute_path(root_path: Optional[str], relative_path: str) -> Optional[str]:
    """Compute an absolute path if the storage root path is known."""
    if not root_path:
        return None
    # relative_path is stored as forward-slash normalized. Convert for local OS.
    rel_local = relative_path.replace("/", os.sep)
    return os.path.normpath(os.path.join(str(root_path), rel_local))


class _ImagePreviewLabel(QLabel):
    """A QLabel that rescales a stored pixmap to its current size."""

    # Cap decoded/displayed pixels to ~1/4 of 1440p (2560*1440*0.25 ≈ 921,600).
    MAX_PIXEL_AREA = 921_600

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._original: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_original_pixmap(self, pixmap: Optional[QPixmap]) -> None:
        self._original = pixmap
        self._apply_scaled()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_scaled()

    def _apply_scaled(self) -> None:
        if self._original is None or self._original.isNull():
            self.setPixmap(QPixmap())
            return

        w = max(1, int(self.width()))
        h = max(1, int(self.height()))

        # Apply a pixel-area cap so we don't ever display gigantic pixmaps.
        area = w * h
        if area > self.MAX_PIXEL_AREA:
            scale = (self.MAX_PIXEL_AREA / float(area)) ** 0.5
            w = max(1, int(w * scale))
            h = max(1, int(h * scale))

        scaled = self._original.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)


class FileDetailPane(QWidget):
    """Right-side detail pane for Library tab (Stage 7.3).

    Shows a best-effort preview and read-only details for a selected file.
    """

    def __init__(self, conn: sqlite3.Connection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._current_file_id: Optional[int] = None
        self._current_details: Optional[FileDetails] = None
        self._did_restore_splitters: bool = False

        self._build_ui()
        self.clear()

    # -----------------
    # Public API
    # -----------------

    @property
    def current_file_id(self) -> Optional[int]:
        return self._current_file_id

    @property
    def current_absolute_path(self) -> Optional[str]:
        return None if self._current_details is None else self._current_details.absolute_path

    def clear(self) -> None:
        self._current_file_id = None
        self._current_details = None
        self._stack.setCurrentWidget(self._empty)

    def set_file_id(self, file_id: int) -> None:
        self._current_file_id = int(file_id)
        self.refresh()

    def refresh(self) -> None:
        if self._current_file_id is None:
            self.clear()
            return

        details = self._load_details(self._current_file_id)
        if details is None:
            self.clear()
            return

        self._current_details = details
        self._render(details)
        self._stack.setCurrentWidget(self._content)

    # -----------------
    # UI
    # -----------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        self._stack = QStackedLayout()
        root.addLayout(self._stack)

        # Empty state
        self._empty = QWidget(self)
        empty_layout = QVBoxLayout(self._empty)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.addStretch(1)
        self._empty_label = QLabel("Select a file in Library to view details", self._empty)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Low contrast: rely on palette rather than hard-coded colors.
        self._empty_label.setEnabled(False)
        empty_layout.addWidget(self._empty_label)
        empty_layout.addStretch(1)
        self._stack.addWidget(self._empty)

        # Content
        self._content = QWidget(self)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._content)

        # Vertical splitter inside the detail pane:
        # top = preview, bottom = details (scrollable).
        self._vsplit = QSplitter(Qt.Orientation.Vertical, self._content)
        content_layout.addWidget(self._vsplit, stretch=1)

        # -----------------
        # Preview container (resizable via splitter handle)
        # -----------------
        self._preview_frame = QFrame(self._content)
        self._preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._preview_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Keep minimums modest so the main window can fit on smaller monitors.
        self._preview_frame.setMinimumHeight(140)
        self._preview_frame.setMinimumWidth(200)

        preview_layout = QVBoxLayout(self._preview_frame)
        preview_layout.setContentsMargins(6, 6, 6, 6)

        self._preview_stack = QStackedLayout()
        preview_layout.addLayout(self._preview_stack)

        self._preview_image = _ImagePreviewLabel(self._preview_frame)
        self._preview_stack.addWidget(self._preview_image)

        self._preview_fallback = QLabel(SUPPORTED_PREVIEW_TEXT, self._preview_frame)
        self._preview_fallback.setWordWrap(True)
        self._preview_fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_fallback.setEnabled(False)
        self._preview_stack.addWidget(self._preview_fallback)

        self._vsplit.addWidget(self._preview_frame)

        # -----------------
        # Details container (scrollable)
        # -----------------
        self._details_scroll = QScrollArea(self._content)
        self._details_scroll.setWidgetResizable(True)
        self._details_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._details_host = QWidget(self._details_scroll)
        self._details_scroll.setWidget(self._details_host)

        details_layout = QVBoxLayout(self._details_host)
        details_layout.setContentsMargins(0, 0, 0, 0)

        # Core fields
        self._core_form = QFormLayout()
        self._core_form.setContentsMargins(0, 8, 0, 0)

        self._lbl_filename = QLabel("", self._details_host)
        self._lbl_integrity = QLabel("", self._details_host)
        self._lbl_storage = QLabel("", self._details_host)
        self._lbl_root = QLabel("", self._details_host)
        self._lbl_rel = QLabel("", self._details_host)
        self._lbl_abs = QLabel("", self._details_host)
        self._lbl_size = QLabel("", self._details_host)
        self._lbl_mtime = QLabel("", self._details_host)

        for w in [
            self._lbl_storage,
            self._lbl_root,
            self._lbl_rel,
            self._lbl_abs,
        ]:
            w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Prevent long paths from expanding the splitter: wrap value labels.
        for w in [
            self._lbl_filename,
            self._lbl_integrity,
            self._lbl_storage,
            self._lbl_root,
            self._lbl_rel,
            self._lbl_abs,
            self._lbl_size,
            self._lbl_mtime,
        ]:
            w.setWordWrap(True)
            w.setMinimumWidth(0)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            w.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._core_form.addRow("Filename:", self._lbl_filename)
        self._core_form.addRow("Integrity:", self._lbl_integrity)
        self._core_form.addRow("Storage:", self._lbl_storage)
        self._core_form.addRow("Root path:", self._lbl_root)
        self._core_form.addRow("Relative path:", self._lbl_rel)
        self._core_form.addRow("Absolute path:", self._lbl_abs)
        self._core_form.addRow("Size:", self._lbl_size)
        self._core_form.addRow("Modified:", self._lbl_mtime)

        details_layout.addLayout(self._core_form)

        # Advanced section (collapsible)
        self._adv_toggle = QToolButton(self._details_host)
        self._adv_toggle.setText("Advanced")
        self._adv_toggle.setCheckable(True)
        self._adv_toggle.setChecked(False)
        self._adv_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._adv_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self._adv_container = QWidget(self._details_host)
        self._adv_container.setVisible(False)
        adv_form = QFormLayout(self._adv_container)
        adv_form.setContentsMargins(8, 8, 8, 8)

        self._adv_file_id = QLabel("", self._adv_container)
        self._adv_storage_id = QLabel("", self._adv_container)
        self._adv_version_id = QLabel("", self._adv_container)
        self._adv_size_bytes = QLabel("", self._adv_container)
        self._adv_mtime_unix = QLabel("", self._adv_container)
        self._adv_created = QLabel("", self._adv_container)

        for w in [
            self._adv_file_id,
            self._adv_storage_id,
            self._adv_version_id,
            self._adv_size_bytes,
            self._adv_mtime_unix,
            self._adv_created,
        ]:
            w.setWordWrap(True)
            w.setMinimumWidth(0)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            w.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        adv_form.addRow("file.id:", self._adv_file_id)
        adv_form.addRow("storage_id:", self._adv_storage_id)
        adv_form.addRow("version_id:", self._adv_version_id)
        adv_form.addRow("size_bytes:", self._adv_size_bytes)
        adv_form.addRow("mtime_unix:", self._adv_mtime_unix)
        adv_form.addRow("created_at:", self._adv_created)

        def _on_adv_toggled(checked: bool) -> None:
            self._adv_container.setVisible(checked)
            self._adv_toggle.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )

        self._adv_toggle.toggled.connect(_on_adv_toggled)

        details_layout.addWidget(self._adv_toggle)
        details_layout.addWidget(self._adv_container)
        details_layout.addStretch(1)

        self._vsplit.addWidget(self._details_scroll)

        # Default splitter sizing (preview ~40%, details ~60%)
        self._vsplit.setStretchFactor(0, 2)
        self._vsplit.setStretchFactor(1, 3)

        # Persist splitter state.
        self._vsplit.splitterMoved.connect(lambda *_: self._save_splitter_state())


    # -----------------
    # Splitter persistence
    # -----------------

    _SETTINGS_KEY_VSPLIT = "ui/library/detail_pane/vsplitter_state"

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._did_restore_splitters:
            self._restore_splitter_state()
            self._did_restore_splitters = True

    def _settings(self) -> QSettings:
        # Uses the application’s organization/app name if set; otherwise a local default store.
        return QSettings()

    def _save_splitter_state(self) -> None:
        try:
            s = self._settings()
            s.setValue(self._SETTINGS_KEY_VSPLIT, self._vsplit.saveState())
        except Exception:
            # Persistence should never break the UI.
            return

    def _restore_splitter_state(self) -> None:
        try:
            s = self._settings()
            state = s.value(self._SETTINGS_KEY_VSPLIT)
            if state:
                ok = self._vsplit.restoreState(state)
                if ok:
                    return
        except Exception:
            pass

        # Fallback default sizing based on current widget height.
        h = max(1, int(self.height()))
        self._vsplit.setSizes([int(h * 0.4), int(h * 0.6)])

    # -----------------
    # Data loading
    # -----------------

    def _load_details(self, file_id: int) -> Optional[FileDetails]:
        row = self._conn.execute(
            """
            SELECT
                file.id,
                file.version_id,
                file.storage_id,
                storage.name,
                storage.root_path,
                storage.status,
                file.relative_path,
                file.integrity_state,
                file.size_bytes,
                file.mtime_unix,
                file.created_at
            FROM file
            JOIN storage ON storage.id = file.storage_id
            WHERE file.id = ?;
            """,
            (int(file_id),),
        ).fetchone()
        if not row:
            return None

        (
            fid,
            vid,
            sid,
            sname,
            root_path,
            sstatus,
            rel,
            integrity,
            size_b,
            mtime_u,
            created_at,
        ) = row

        rel_s = str(rel)
        filename = rel_s.split("/")[-1] if "/" in rel_s else rel_s
        abs_path = compute_absolute_path(None if root_path is None else str(root_path), rel_s)

        return FileDetails(
            file_id=int(fid),
            version_id=None if vid is None else int(vid),
            storage_id=int(sid),
            storage_name=str(sname),
            storage_root_path=None if root_path is None else str(root_path),
            storage_status=str(sstatus),
            relative_path=rel_s,
            filename=filename,
            integrity_state=str(integrity),
            size_bytes=None if size_b is None else int(size_b),
            mtime_unix=None if mtime_u is None else float(mtime_u),
            created_at=str(created_at),
            absolute_path=abs_path,
        )

    # -----------------
    # Rendering
    # -----------------

    def _render(self, d: FileDetails) -> None:
        self._lbl_filename.setText(d.filename)
        self._lbl_integrity.setText(str(d.integrity_state))
        self._lbl_storage.setText(d.storage_name)
        self._lbl_root.setText("" if d.storage_root_path is None else d.storage_root_path)
        self._lbl_rel.setText(d.relative_path)
        self._lbl_abs.setText("" if d.absolute_path is None else d.absolute_path)
        self._lbl_size.setText(_fmt_size(d.size_bytes))
        self._lbl_mtime.setText(_fmt_mtime(d.mtime_unix))

        # Advanced
        self._adv_file_id.setText(str(d.file_id))
        self._adv_storage_id.setText(str(d.storage_id))
        self._adv_version_id.setText("" if d.version_id is None else str(d.version_id))
        self._adv_size_bytes.setText("" if d.size_bytes is None else str(d.size_bytes))
        self._adv_mtime_unix.setText("" if d.mtime_unix is None else f"{float(d.mtime_unix):.3f}")
        self._adv_created.setText(d.created_at)

        self._render_preview(d)

    def _render_preview(self, d: FileDetails) -> None:
        # Default: fallback message
        self._preview_image.set_original_pixmap(None)
        self._preview_stack.setCurrentWidget(self._preview_fallback)

        if not d.absolute_path:
            return

        p = Path(d.absolute_path)
        suffix = p.suffix.lower()
        if suffix not in SUPPORTED_PREVIEW_FORMATS:
            return

        if not p.exists() or not p.is_file():
            return

        pix = self._load_capped_pixmap(str(p))
        if pix is None or pix.isNull():
            return

        self._preview_image.set_original_pixmap(pix)
        self._preview_stack.setCurrentWidget(self._preview_image)

    @classmethod
    def _load_capped_pixmap(cls, path: str) -> Optional[QPixmap]:
        """Load an image with a decode cap so we avoid huge textures."""
        reader = QImageReader(path)
        if not reader.canRead():
            return None

        size = reader.size()
        if size.isValid():
            w = max(1, int(size.width()))
            h = max(1, int(size.height()))
            area = w * h
            if area > _ImagePreviewLabel.MAX_PIXEL_AREA:
                scale = (_ImagePreviewLabel.MAX_PIXEL_AREA / float(area)) ** 0.5
                sw = max(1, int(w * scale))
                sh = max(1, int(h * scale))
                reader.setScaledSize(size.__class__(sw, sh))  # QSize without importing

        img = reader.read()
        if img.isNull():
            return None
        return QPixmap.fromImage(img)

    # -----------------
    # Convenience actions
    # -----------------

    @staticmethod
    def copy_to_clipboard(text: str) -> None:
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text)
