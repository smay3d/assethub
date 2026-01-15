# src/assethub/ui/views/settings_tab.py

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from assethub import __version__
from assethub.context import AppContext
from assethub.ui.ui_constants import (
    DEFAULT_VISIBLE_FILE_COLUMNS,
    LIBRARY_CAP_ROWS,
    PREVIEW_MAX_PIXEL_AREA,
    SUPPORTED_PREVIEW_FORMATS,
)
from assethub.ui.views.file_detail_pane import FileDetailPane
from assethub.ui.views.library_tab import LibraryTab


def _fmt_bytes(size_bytes: Optional[int]) -> str:
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


def _open_in_file_manager(path: str) -> None:
    """Open a folder (or a file's parent folder) in the OS file manager."""
    if not path:
        return
    p = os.path.normpath(path)
    target = p
    # If it's a file path (or doesn't exist), attempt to open its parent.
    if os.path.splitext(p)[1] and not os.path.isdir(p):
        parent = os.path.dirname(p)
        if parent:
            target = parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(target))


@dataclass(frozen=True)
class _UiKeyInfo:
    label: str
    key: str


class SettingsTab(QWidget):
    """Stage 7.4: Settings tab (read-only diagnostics + transparency)."""

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context

        self._build_ui()
        self.refresh()

    # -----------------
    # UI
    # -----------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        body = QWidget(scroll)
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # --- About ---
        self.grp_about = QGroupBox("About", body)
        about_form = QFormLayout(self.grp_about)
        self.lbl_app_version = QLabel("", self.grp_about)
        self.lbl_schema_version = QLabel("", self.grp_about)
        self.lbl_python = QLabel("", self.grp_about)
        self.lbl_pyside = QLabel("", self.grp_about)
        self.lbl_platform = QLabel("", self.grp_about)

        for lbl in [
            self.lbl_app_version,
            self.lbl_schema_version,
            self.lbl_python,
            self.lbl_pyside,
            self.lbl_platform,
        ]:
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        about_form.addRow("App version:", self.lbl_app_version)
        about_form.addRow("DB schema version:", self.lbl_schema_version)
        about_form.addRow("Python:", self.lbl_python)
        about_form.addRow("PySide6:", self.lbl_pyside)
        about_form.addRow("Platform:", self.lbl_platform)

        layout.addWidget(self.grp_about)

        # --- Paths ---
        self.grp_paths = QGroupBox("Paths", body)
        paths_form = QFormLayout(self.grp_paths)
        self._path_rows: dict[str, tuple[QLabel, QPushButton, QPushButton]] = {}

        def add_path_row(label: str, key: str) -> None:
            row = QWidget(self.grp_paths)
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(8)

            val = QLabel("", row)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setWordWrap(True)

            btn_copy = QPushButton("Copy", row)
            btn_open = QPushButton("Open", row)

            row_l.addWidget(val, stretch=1)
            row_l.addWidget(btn_copy)
            row_l.addWidget(btn_open)

            btn_copy.clicked.connect(lambda _=False, k=key: self._copy_path(k))
            btn_open.clicked.connect(lambda _=False, k=key: self._open_path(k))

            self._path_rows[key] = (val, btn_copy, btn_open)
            paths_form.addRow(label, row)

        add_path_row("Data root:", "data_root")
        add_path_row("DB path:", "db_path")
        add_path_row("Sidecar root:", "sidecar_root")
        add_path_row("Preview cache root:", "preview_root")
        add_path_row("Log root:", "log_root")

        layout.addWidget(self.grp_paths)

        # --- Database & Index Stats ---
        self.grp_db = QGroupBox("Database & Index Stats", body)
        db_form = QFormLayout(self.grp_db)

        self.lbl_count_storage = QLabel("", self.grp_db)
        self.lbl_count_file = QLabel("", self.grp_db)
        self.lbl_count_missing = QLabel("", self.grp_db)
        self.lbl_count_asset = QLabel("", self.grp_db)
        self.lbl_count_version = QLabel("", self.grp_db)
        self.lbl_count_tag = QLabel("", self.grp_db)
        self.lbl_count_asset_tag = QLabel("", self.grp_db)
        self.lbl_count_schema_rows = QLabel("", self.grp_db)
        self.lbl_unmanaged_present = QLabel("", self.grp_db)
        self.lbl_db_size = QLabel("", self.grp_db)

        for lbl in [
            self.lbl_count_storage,
            self.lbl_count_file,
            self.lbl_count_missing,
            self.lbl_count_asset,
            self.lbl_count_version,
            self.lbl_count_tag,
            self.lbl_count_asset_tag,
            self.lbl_count_schema_rows,
            self.lbl_unmanaged_present,
            self.lbl_db_size,
        ]:
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        db_form.addRow("storage rows:", self.lbl_count_storage)
        db_form.addRow("file rows:", self.lbl_count_file)
        db_form.addRow("missing files:", self.lbl_count_missing)
        db_form.addRow("asset rows:", self.lbl_count_asset)
        db_form.addRow("version rows:", self.lbl_count_version)
        db_form.addRow("tag rows:", self.lbl_count_tag)
        db_form.addRow("asset_tag rows:", self.lbl_count_asset_tag)
        db_form.addRow("schema_version rows:", self.lbl_count_schema_rows)
        db_form.addRow("Unmanaged present:", self.lbl_unmanaged_present)
        db_form.addRow("DB file size:", self.lbl_db_size)

        db_actions = QWidget(self.grp_db)
        db_actions_l = QHBoxLayout(db_actions)
        db_actions_l.setContentsMargins(0, 0, 0, 0)
        db_actions_l.setSpacing(8)
        self.btn_open_db_folder = QPushButton("Open DB folder", db_actions)
        self.btn_copy_diag = QPushButton("Copy diagnostics summary", db_actions)
        db_actions_l.addWidget(self.btn_open_db_folder)
        db_actions_l.addWidget(self.btn_copy_diag)
        db_actions_l.addStretch(1)
        db_form.addRow("", db_actions)

        self.btn_open_db_folder.clicked.connect(self._open_db_folder)
        self.btn_copy_diag.clicked.connect(self._copy_diagnostics_summary)

        layout.addWidget(self.grp_db)

        # --- UI Behavior ---
        self.grp_ui = QGroupBox("UI Behavior", body)
        ui_form = QFormLayout(self.grp_ui)

        self.lbl_row_cap = QLabel("", self.grp_ui)
        self.lbl_default_cols = QLabel("", self.grp_ui)
        self.lbl_preview_formats = QLabel("", self.grp_ui)
        self.lbl_preview_cap = QLabel("", self.grp_ui)
        self.lbl_qsettings_keys = QLabel("", self.grp_ui)

        for lbl in [
            self.lbl_row_cap,
            self.lbl_default_cols,
            self.lbl_preview_formats,
            self.lbl_preview_cap,
            self.lbl_qsettings_keys,
        ]:
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setWordWrap(True)

        ui_form.addRow("Library row cap:", self.lbl_row_cap)
        ui_form.addRow("Default visible columns:", self.lbl_default_cols)
        ui_form.addRow("Supported preview formats:", self.lbl_preview_formats)
        ui_form.addRow("Preview pixel cap (area):", self.lbl_preview_cap)
        ui_form.addRow("Layout persistence (QSettings):", self.lbl_qsettings_keys)

        layout.addWidget(self.grp_ui)

        layout.addStretch(1)

    # -----------------
    # Public API
    # -----------------

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Refresh whenever the Settings tab is shown (tab switch or window show).
        self.refresh()

    def refresh(self) -> None:
        """Refresh all displayed fields from current context + DB."""
        self._refresh_about()
        self._refresh_paths()
        self._refresh_db_stats()
        self._refresh_ui_behavior()

    # -----------------
    # Section refreshers
    # -----------------

    def _refresh_about(self) -> None:
        self.lbl_app_version.setText(__version__)

        schema_v = ""
        conn = self.context.db_connection
        if conn is not None:
            try:
                row = conn.execute("SELECT MAX(version) FROM schema_version;").fetchone()
                schema_v = "" if not row else str(row[0] if row[0] is not None else "")
            except Exception:
                schema_v = ""
        self.lbl_schema_version.setText(schema_v)

        self.lbl_python.setText(sys.version.split("\n", 1)[0])

        try:
            import PySide6  # type: ignore

            self.lbl_pyside.setText(getattr(PySide6, "__version__", ""))
        except Exception:
            self.lbl_pyside.setText("")

        self.lbl_platform.setText(platform.platform())

    def _refresh_paths(self) -> None:
        cfg = self.context.config
        mapping = {
            "data_root": cfg.data_root,
            "db_path": cfg.db_path,
            "sidecar_root": cfg.sidecar_root,
            "preview_root": cfg.preview_root,
            "log_root": cfg.log_root,
        }
        for key, value in mapping.items():
            row = self._path_rows.get(key)
            if row is None:
                continue
            label, btn_copy, btn_open = row
            label.setText(value or "")
            btn_copy.setEnabled(bool(value))
            btn_open.setEnabled(bool(value))

    def _refresh_db_stats(self) -> None:
        conn = self.context.db_connection
        cfg = self.context.config

        def safe_count(sql: str) -> int:
            if conn is None:
                return 0
            try:
                row = conn.execute(sql).fetchone()
                return int(row[0]) if row and row[0] is not None else 0
            except Exception:
                return 0

        storage_count = safe_count("SELECT COUNT(*) FROM storage;")
        file_count = safe_count("SELECT COUNT(*) FROM file;")
        missing_count = safe_count("SELECT COUNT(*) FROM file WHERE UPPER(integrity_state) = 'MISSING';")
        asset_count = safe_count("SELECT COUNT(*) FROM asset;")
        version_count = safe_count("SELECT COUNT(*) FROM version;")
        tag_count = safe_count("SELECT COUNT(*) FROM tag;")
        asset_tag_count = safe_count("SELECT COUNT(*) FROM asset_tag;")
        schema_rows = safe_count("SELECT COUNT(*) FROM schema_version;")
        unmanaged_rows = safe_count("SELECT COUNT(*) FROM storage WHERE root_path IS NULL;")

        self.lbl_count_storage.setText(str(storage_count))
        self.lbl_count_file.setText(str(file_count))
        self.lbl_count_missing.setText(str(missing_count))
        self.lbl_count_asset.setText(str(asset_count))
        self.lbl_count_version.setText(str(version_count))
        self.lbl_count_tag.setText(str(tag_count))
        self.lbl_count_asset_tag.setText(str(asset_tag_count))
        self.lbl_count_schema_rows.setText(str(schema_rows))
        self.lbl_unmanaged_present.setText("Yes" if unmanaged_rows > 0 else "No")

        db_size: Optional[int] = None
        try:
            if cfg.db_path and os.path.exists(cfg.db_path):
                db_size = int(os.path.getsize(cfg.db_path))
        except Exception:
            db_size = None
        self.lbl_db_size.setText(_fmt_bytes(db_size) if db_size is not None else "")

    def _refresh_ui_behavior(self) -> None:
        # Library
        self.lbl_row_cap.setText(str(LIBRARY_CAP_ROWS))
        self.lbl_default_cols.setText(", ".join(DEFAULT_VISIBLE_FILE_COLUMNS))

        # Preview
        self.lbl_preview_formats.setText(" ".join(SUPPORTED_PREVIEW_FORMATS))
        self.lbl_preview_cap.setText(str(PREVIEW_MAX_PIXEL_AREA))

        # Layout persistence keys (presence)
        keys = [
            _UiKeyInfo("Library splitter", getattr(LibraryTab, "_SETTINGS_KEY_HSPLIT", "")),
            _UiKeyInfo("Detail splitter", getattr(FileDetailPane, "_SETTINGS_KEY_VSPLIT", "")),
        ]

        s = QSettings()
        parts = []
        for k in keys:
            if not k.key:
                continue
            present = "Yes" if s.contains(k.key) else "No"
            parts.append(f"{k.label}: {k.key} (saved: {present})")
        self.lbl_qsettings_keys.setText("\n".join(parts))

    # -----------------
    # Actions
    # -----------------

    def _get_path_value(self, key: str) -> str:
        cfg = self.context.config
        return str(getattr(cfg, key, "") or "")

    def _copy_path(self, key: str) -> None:
        text = self._get_path_value(key)
        if not text:
            return
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text)

    def _open_path(self, key: str) -> None:
        p = self._get_path_value(key)
        if not p:
            return
        _open_in_file_manager(p)

    def _open_db_folder(self) -> None:
        db_path = self.context.config.db_path
        if not db_path:
            return
        _open_in_file_manager(db_path)

    def _copy_diagnostics_summary(self) -> None:
        cfg = self.context.config
        conn = self.context.db_connection

        def safe_count(sql: str) -> int:
            if conn is None:
                return 0
            try:
                row = conn.execute(sql).fetchone()
                return int(row[0]) if row and row[0] is not None else 0
            except Exception:
                return 0

        schema_v = ""
        if conn is not None:
            try:
                row = conn.execute("SELECT MAX(version) FROM schema_version;").fetchone()
                schema_v = "" if not row else str(row[0] if row[0] is not None else "")
            except Exception:
                schema_v = ""

        # Avoid backslashes in f-string expressions by keeping SQL in variables.
        q_missing = "SELECT COUNT(*) FROM file WHERE UPPER(integrity_state)='MISSING';"

        lines = [
            f"AssetHub version: {__version__}",
            f"Schema version: {schema_v}",
            "",
            "Paths:",
            f"  data_root: {cfg.data_root}",
            f"  db_path: {cfg.db_path}",
            f"  sidecar_root: {cfg.sidecar_root}",
            f"  preview_root: {cfg.preview_root}",
            f"  log_root: {cfg.log_root}",
            "",
            "Counts:",
            f"  storage: {safe_count('SELECT COUNT(*) FROM storage;')}",
            f"  file: {safe_count('SELECT COUNT(*) FROM file;')}",
            f"  missing_files: {safe_count(q_missing)}",
            f"  asset: {safe_count('SELECT COUNT(*) FROM asset;')}",
            f"  version: {safe_count('SELECT COUNT(*) FROM version;')}",
            f"  tag: {safe_count('SELECT COUNT(*) FROM tag;')}",
            f"  asset_tag: {safe_count('SELECT COUNT(*) FROM asset_tag;')}",
        ]

        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText("\n".join(lines))
