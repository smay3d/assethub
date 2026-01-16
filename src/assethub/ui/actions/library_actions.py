"""Library selection actions.

Stage 7.5.3: move list interactions into a reusable action layer.

Design notes:
- This module may import Qt helpers (QDesktopServices/QUrl/QMessageBox), but it
  must not create QApplication instances or widgets at import time.
- DB operations are delegated to core helpers when possible for testability.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

from assethub.context import AppContext
from assethub.core.db.file_records import (
    FileRecordInfo,
    delete_missing_file_records,
    fetch_file_records,
)
from assethub.core.health.checker import HealthChecker
from assethub.core.utils.checksum import sha256_file
from assethub.ui.utils.clipboard import set_clipboard_text
from assethub.ui.views.file_detail_pane import compute_absolute_path


@dataclass(frozen=True)
class ChecksumLimits:
    max_files: int = 20
    max_total_bytes: int = 500 * 1024 * 1024  # 500MB


class LibraryActions:
    """Action helpers for the Library list.

    These functions should be callable from multiple views in the future.
    """

    def __init__(self, context: AppContext, *, parent: Optional[QWidget] = None) -> None:
        self.context = context
        self.parent = parent

    # -----------------
    # Path resolving
    # -----------------

    def fetch_records(self, file_ids: List[int]) -> List[FileRecordInfo]:
        conn = self.context.db_connection
        if conn is None:
            return []
        return fetch_file_records(conn, file_ids)

    @staticmethod
    def _abs_path_for_record(rec: FileRecordInfo) -> Optional[str]:
        return compute_absolute_path(rec.storage_root_path, rec.relative_path)

    # -----------------
    # Open / Reveal
    # -----------------

    def open_file_with_default(self, current_file_id: Optional[int]) -> None:
        if current_file_id is None:
            return
        recs = self.fetch_records([current_file_id])
        if not recs:
            return
        abs_path = self._abs_path_for_record(recs[0])
        if not abs_path:
            return
        if not os.path.exists(abs_path):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(abs_path))

    def reveal_in_explorer(self, current_file_id: Optional[int]) -> None:
        if current_file_id is None:
            return
        recs = self.fetch_records([current_file_id])
        if not recs:
            return
        abs_path = self._abs_path_for_record(recs[0])
        if not abs_path:
            return

        # Prefer selecting the file on Windows.
        try:
            if sys.platform.startswith("win"):
                # explorer expects '/select,' with comma.
                subprocess.Popen(["explorer", "/select,", os.path.normpath(abs_path)])
                return
        except Exception:
            pass

        folder = os.path.dirname(abs_path)
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def open_storage_root_location(self, current_file_id: Optional[int]) -> None:
        if current_file_id is None:
            return
        recs = self.fetch_records([current_file_id])
        if not recs:
            return
        root = recs[0].storage_root_path
        if not root:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(root))

    # -----------------
    # Copy
    # -----------------

    def copy_file_names(self, file_ids: List[int]) -> None:
        recs = self.fetch_records(file_ids)
        names: List[str] = []
        for r in recs:
            rel = r.relative_path.replace("\\", "/")
            names.append(rel.split("/")[-1] if "/" in rel else rel)
        set_clipboard_text("\n".join(names))

    def copy_abs_dirs(self, file_ids: List[int]) -> None:
        recs = self.fetch_records(file_ids)
        out: List[str] = []
        for r in recs:
            abs_path = self._abs_path_for_record(r)
            if not abs_path:
                out.append("<UNRESOLVED>")
                continue
            out.append(os.path.dirname(os.path.normpath(abs_path)))
        set_clipboard_text("\n".join(out))

    def copy_rel_dirs(self, file_ids: List[int]) -> None:
        recs = self.fetch_records(file_ids)
        out: List[str] = []
        for r in recs:
            rel = r.relative_path.replace("\\", "/")
            d = os.path.dirname(rel)
            out.append(d.replace("\\", "/"))
        set_clipboard_text("\n".join(out))

    def copy_checksums_sha256(self, file_ids: List[int], *, limits: ChecksumLimits = ChecksumLimits()) -> None:
        recs = self.fetch_records(file_ids)
        if not recs:
            return

        if len(recs) > limits.max_files:
            self._warn(
                f"Checksum copy limited to {limits.max_files} files at a time.\n"
                f"Selected: {len(recs)}"
            )
            return

        total_bytes = 0
        for r in recs:
            if r.size_bytes is not None:
                total_bytes += int(r.size_bytes)
        if total_bytes > limits.max_total_bytes:
            mb = total_bytes / (1024 * 1024)
            self._warn(
                "Checksum copy limited by total size.\n"
                f"Selected size: {mb:.1f} MB\n"
                f"Limit: {limits.max_total_bytes / (1024 * 1024):.0f} MB"
            )
            return

        lines: List[str] = []
        for r in recs:
            abs_path = self._abs_path_for_record(r)
            if not abs_path or not os.path.exists(abs_path):
                lines.append("<UNAVAILABLE>")
                continue
            try:
                lines.append(sha256_file(abs_path))
            except Exception:
                lines.append("<UNAVAILABLE>")
        set_clipboard_text("\n".join(lines))

    # -----------------
    # Health
    # -----------------

    def run_health_check(self, file_ids: List[int]) -> None:
        if not file_ids:
            return
        conn = self.context.db_connection
        storage = self.context.storage_manager
        if conn is None or storage is None:
            return

        health = HealthChecker(conn, storage)
        health.check_files([int(x) for x in file_ids])
        changed = int(health.last_changed_count)

        # Always emit a health_finished summary.
        try:
            self.context.event_hub.health_finished.emit(
                {
                    "targeted": True,
                    "checked_count": len(file_ids),
                    "changed_rows": changed,
                }
            )
        except Exception:
            pass

        # Only emit db_changed if rows changed.
        if changed > 0:
            try:
                self.context.event_hub.db_changed.emit(
                    reason="health_check_targeted",
                    payload={"changed_rows": changed, "checked_count": len(file_ids)},
                )
            except Exception:
                pass

    # -----------------
    # DB removal
    # -----------------

    def remove_missing_from_database(self, file_ids: List[int]) -> int:
        """Remove missing-only records from DB.

        Returns number of deleted rows.
        Raises ValueError if selection includes non-missing.
        """
        conn = self.context.db_connection
        if conn is None:
            return 0
        deleted = delete_missing_file_records(conn, file_ids)
        if deleted > 0:
            try:
                self.context.event_hub.db_changed.emit(
                    reason="file_records_deleted",
                    payload={"count": deleted},
                )
            except Exception:
                pass
        return deleted

    # -----------------
    # UI helpers
    # -----------------

    def _warn(self, message: str) -> None:
        try:
            QMessageBox.warning(self.parent, "AssetHub", message)
        except Exception:
            return
