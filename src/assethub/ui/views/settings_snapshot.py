"""Pure (non-Qt) Settings snapshot helpers.

Stage 7.4 Settings tab is intentionally read-only and primarily for developer
visibility. Unit tests should not need to instantiate Qt widgets (which can be
unstable under pytest on some Windows setups). This module provides a pure
data snapshot that the UI can render.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from typing import Any, Optional

from assethub import __version__
from assethub.context import AppContext


@dataclass(frozen=True)
class SettingsSnapshot:
    about: dict[str, str]
    paths: dict[str, str]
    db_stats: dict[str, Any]
    ui_behavior: dict[str, Any]


def collect_settings_snapshot(ctx: AppContext) -> SettingsSnapshot:
    """Collect a UI-facing snapshot of current settings and DB stats.

    This function is deliberately Qt-free.
    """
    about = _collect_about(ctx)
    paths = _collect_paths(ctx)
    db_stats = _collect_db_stats(ctx)
    ui_behavior = _collect_ui_behavior(ctx)
    return SettingsSnapshot(about=about, paths=paths, db_stats=db_stats, ui_behavior=ui_behavior)


def _collect_about(ctx: AppContext) -> dict[str, str]:
    conn = ctx.db_connection
    schema_v = ""
    if conn is not None:
        try:
            row = conn.execute("SELECT MAX(version) FROM schema_version;").fetchone()
            schema_v = "" if not row else str(row[0] if row[0] is not None else "")
        except Exception:
            schema_v = ""

    return {
        "app_version": __version__,
        "schema_version": schema_v,
        "python": sys.version.split("\n", 1)[0],
        # Keep this Qt-free; PySide6 version is provided by the UI layer.
        "platform": platform.platform(),
    }


def _collect_paths(ctx: AppContext) -> dict[str, str]:
    cfg = ctx.config
    return {
        "data_root": cfg.data_root or "",
        "db_path": cfg.db_path or "",
        "sidecar_root": cfg.sidecar_root or "",
        "preview_root": cfg.preview_root or "",
        "log_root": cfg.log_root or "",
    }


def _collect_db_stats(ctx: AppContext) -> dict[str, Any]:
    conn = ctx.db_connection
    cfg = ctx.config

    def safe_count(sql: str) -> int:
        if conn is None:
            return 0
        try:
            row = conn.execute(sql).fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        except Exception:
            return 0

    stats: dict[str, Any] = {
        "storage_rows": safe_count("SELECT COUNT(*) FROM storage;"),
        "file_rows": safe_count("SELECT COUNT(*) FROM file;"),
        "missing_files": safe_count("SELECT COUNT(*) FROM file WHERE UPPER(integrity_state)='MISSING';"),
        "asset_rows": safe_count("SELECT COUNT(*) FROM asset;"),
        "version_rows": safe_count("SELECT COUNT(*) FROM version;"),
        "tag_rows": safe_count("SELECT COUNT(*) FROM tag;"),
        "asset_tag_rows": safe_count("SELECT COUNT(*) FROM asset_tag;"),
        "schema_version_rows": safe_count("SELECT COUNT(*) FROM schema_version;"),
        "unmanaged_present": safe_count("SELECT COUNT(*) FROM storage WHERE root_path IS NULL;") > 0,
    }

    db_size: Optional[int] = None
    try:
        if cfg.db_path and os.path.exists(cfg.db_path):
            db_size = int(os.path.getsize(cfg.db_path))
    except Exception:
        db_size = None
    stats["db_file_size_bytes"] = db_size

    return stats


def _collect_ui_behavior(ctx: AppContext) -> dict[str, Any]:
    """Collect UI behavior values that are stable and Qt-free."""
    from assethub.ui.ui_constants import (
        DEFAULT_VISIBLE_FILE_COLUMNS,
        LIBRARY_CAP_ROWS,
        PREVIEW_MAX_PIXEL_AREA,
        SUPPORTED_PREVIEW_FORMATS,
    )

    return {
        "library_row_cap": LIBRARY_CAP_ROWS,
        "default_visible_columns": list(DEFAULT_VISIBLE_FILE_COLUMNS),
        "supported_preview_formats": list(SUPPORTED_PREVIEW_FORMATS),
        "preview_pixel_cap": PREVIEW_MAX_PIXEL_AREA,
    }
