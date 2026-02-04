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
from PySide6.QtWidgets import QMessageBox, QWidget, QInputDialog

from assethub.context import AppContext
from assethub.core.events.event_hub import DbChanged, HealthFinished
from assethub.core.db.file_records import (
    FileRecordInfo,
    delete_missing_file_records,
    fetch_file_records,
)
from assethub.core.db.asset_library import list_assets
from assethub.core.db.file_bindings import get_bindings_for_files, bind_files_to_asset, unbind_files
from assethub.core.db.binding_versioning import version_up_for_binding_change

from assethub.core.health.checker import HealthChecker
from assethub.core.utils.checksum import sha256_file
from assethub.ui.utils.clipboard import set_clipboard_text
from assethub.ui.views.file_detail_pane import compute_absolute_path
from assethub.ui.dialogs.file_select_dialog import FileChoice, prompt_select_files


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
        """Open the current file with the OS-default application."""
        if current_file_id is None:
            return
        recs = self.fetch_records([current_file_id])
        if not recs:
            self._log_warn(f"Open file: record not found (id={int(current_file_id)})")
            return
        abs_path = self._abs_path_for_record(recs[0])
        if not abs_path:
            self._log_warn(f"Open file: could not resolve path (id={int(current_file_id)})")
            return
        if not os.path.exists(abs_path):
            self._log_warn(f"Open file: missing on disk (id={int(current_file_id)})")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(abs_path))
        self._log_info(f"Open file: {recs[0].relative_path}")

    def reveal_in_explorer(self, current_file_id: Optional[int]) -> None:
        """Reveal the current file in the platform file manager."""
        if current_file_id is None:
            return
        recs = self.fetch_records([current_file_id])
        if not recs:
            self._log_warn(f"Reveal: record not found (id={int(current_file_id)})")
            return
        abs_path = self._abs_path_for_record(recs[0])
        if not abs_path:
            self._log_warn(f"Reveal: could not resolve path (id={int(current_file_id)})")
            return

        # Prefer selecting the file on Windows.
        try:
            if sys.platform.startswith("win"):
                # explorer expects '/select,' with comma.
                subprocess.Popen(["explorer", "/select,", os.path.normpath(abs_path)])
                self._log_info(f"Reveal in Explorer: {recs[0].relative_path}")
                return
        except Exception:
            pass

        folder = os.path.dirname(abs_path)
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            self._log_info(f"Open folder: {folder}")

    def open_storage_root_location(self, current_file_id: Optional[int]) -> None:
        """Open the storage root folder for the current file."""
        if current_file_id is None:
            return
        recs = self.fetch_records([current_file_id])
        if not recs:
            self._log_warn(f"Open storage root: record not found (id={int(current_file_id)})")
            return
        root = recs[0].storage_root_path
        if not root:
            self._log_warn(f"Open storage root: unresolved root (id={int(current_file_id)})")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(root))
        self._log_info(f"Open storage root: {root}")

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
        self._log_info(f"Copy: file name(s) to clipboard (count={len(names)})")

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
        self._log_info(f"Copy: absolute dir(s) to clipboard (count={len(out)})")

    def copy_rel_dirs(self, file_ids: List[int]) -> None:
        recs = self.fetch_records(file_ids)
        out: List[str] = []
        for r in recs:
            rel = r.relative_path.replace("\\", "/")
            d = os.path.dirname(rel)
            out.append(d.replace("\\", "/"))
        set_clipboard_text("\n".join(out))
        self._log_info(f"Copy: relative dir(s) to clipboard (count={len(out)})")

    def copy_checksums_sha256(self, file_ids: List[int], *, limits: ChecksumLimits = ChecksumLimits()) -> None:
        """Copy SHA256 checksums for the selected file set (best-effort)."""
        recs = self.fetch_records(file_ids)
        if not recs:
            self._log_warn("Copy checksum: no records found")
            return

        if len(recs) > limits.max_files:
            self._log_warn(
                f"Copy checksum: blocked by file-count limit (selected={len(recs)}, max={limits.max_files})"
            )
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
            self._log_warn(
                f"Copy checksum: blocked by size limit (selected={mb:.1f}MB, max={limits.max_total_bytes / (1024 * 1024):.0f}MB)"
            )
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
        self._log_info(f"Copy: checksum(s) to clipboard (count={len(lines)})")

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

        try:
            self.context.log.info(
                f"Targeted health check: checked {len(file_ids)} file(s); changed {changed} row(s)."
            )
        except Exception:
            pass

        # Always emit a health_finished summary.
        try:
            self.context.event_hub.health_finished.emit(
                HealthFinished(
                    summary={
                        "targeted": True,
                        "checked_count": len(file_ids),
                        "changed_rows": changed,
                    }
                )
            )
        except Exception:
            pass

        # Only emit db_changed if rows changed.
        if changed > 0:
            try:
                self.context.event_hub.db_changed.emit(
                    DbChanged(
                        reason="health_check_targeted",
                        payload={"changed_rows": changed, "checked_count": len(file_ids)},
                    )
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
        try:
            self.context.log.info(
                f"Remove missing selection: removed {deleted} file record(s) from database (selection={len(file_ids)})."
            )
        except Exception:
            pass
        if deleted > 0:
            try:
                self.context.event_hub.db_changed.emit(
                    DbChanged(
                        reason="file_records_deleted",
                        payload={"count": deleted},
                    )
                )
            except Exception:
                pass
        return deleted


    # -----------------
    # Manual bindings (Stage 9.3)
    # -----------------

    def prompt_pick_asset(self, *, title: str = "Select Asset", storage_id: Optional[int] = None) -> Optional[int]:
        """Prompt the user to pick an asset_id.

        Args:
            title: Dialog title.
            storage_id: Optional storage filter.

        Returns:
            asset_id, or None if cancelled.
        """
        conn = self.context.db_connection
        if conn is None:
            self._warn("Database not available.")
            return None
        try:
            rows = list_assets(conn, storage_id=storage_id) if storage_id is not None else list_assets(conn)
        except Exception as e:
            self._warn(f"Failed to load assets: {e}")
            return None

        if not rows:
            self._warn("No assets exist yet.")
            return None

        items: List[str] = []
        ids: List[int] = []
        for r in rows:
            ids.append(int(r.asset_id))
            name = str(r.name or "")
            typ = str(r.type or "")
            key = str(r.key or "")
            items.append(f"{name}  —  {typ}  —  {key}  (id={int(r.asset_id)})")

        choice, ok = QInputDialog.getItem(self.parent, title, "Choose an asset:", items, 0, False)
        if not ok:
            return None
        try:
            idx = items.index(str(choice))
            return int(ids[idx])
        except Exception:
            return None

    def prompt_pick_unassigned_files(
        self,
        *,
        title: str = "Select Files",
        storage_id: Optional[int] = None,
        limit: int = 2000,
    ) -> Optional[List[int]]:
        """Prompt the user to select *unassigned* files.

        Unassigned means:
          - Not manually bound to any asset, AND
          - Not participating in any non-discarded version.

        This is a minimal v0 helper (filter + checklist). We intentionally
        avoid a heavy table UI here.
        """
        conn = self.context.db_connection
        if conn is None:
            self._warn("Database not available.")
            return None

        params: List[object] = []
        where = ""
        if storage_id is not None:
            where = "AND f.storage_id=?"
            params.append(int(storage_id))

        try:
            rows = conn.execute(
                f"""
                SELECT
                    f.id,
                    s.display_name,
                    f.relative_path
                FROM file f
                JOIN storage s ON s.id=f.storage_id
                LEFT JOIN file_binding fb ON fb.file_id=f.id
                WHERE fb.asset_id IS NULL
                  {where}
                  AND NOT EXISTS(
                      SELECT 1
                      FROM version_file vf
                      JOIN version v ON v.id=vf.version_id
                      WHERE vf.file_id=f.id AND COALESCE(v.is_discarded,0)=0
                  )
                ORDER BY LOWER(f.relative_path), f.id
                LIMIT ?;
                """,
                (*params, int(limit)),
            ).fetchall()
        except Exception as e:
            self._warn(f"Failed to load files: {e}")
            return None

        if not rows:
            self._warn("No unassigned files found.")
            return None

        choices: List[FileChoice] = []
        for fid, sname, rel in rows:
            label = f"{str(rel)}  —  {str(sname)}  (id={int(fid)})"
            choices.append(FileChoice(file_id=int(fid), label=label))

        return prompt_select_files(parent=self.parent, title=title, files=choices)

    def bind_files_to_asset_with_prompt(
        self,
        *,
        asset_id: int,
        file_ids: List[int],
        allow_rebind: bool = True,
    ) -> int:
        """Bind file_ids to asset_id, optionally confirming rebinding.

        If allow_rebind is True and some files are already bound to a different asset,
        the user is prompted to confirm the rebind.
        """
        conn = self.context.db_connection
        if conn is None:
            return 0

        ids = [int(x) for x in file_ids if int(x) > 0]
        if not ids:
            return 0

        target_aid = int(asset_id)
        bound_map = {}
        try:
            bound_map = get_bindings_for_files(conn, file_ids=ids)
        except Exception:
            bound_map = {}

        # Only treat as a real operation if at least one selected file would
        # change binding (unbound -> bound, or bound to other -> rebind).
        changed_ids = [fid for fid in ids if int(bound_map.get(int(fid), -1)) != int(target_aid)]
        if not changed_ids:
            self._log_info("Manual bind: selection already bound to the target asset.")
            return 0

        conflicts = {fid: aid for fid, aid in bound_map.items() if int(aid) != target_aid}
        if conflicts and allow_rebind:
            resp = QMessageBox.question(
                self.parent,
                "Rebind files?",
                f"{len(conflicts)} selected file(s) are already bound to another asset.\n\n"
                "Rebind them to the new asset?\n\n"
                "(Files can only be bound to one asset at a time.)",
            )
            if resp != QMessageBox.StandardButton.Yes:
                return 0

        # Version-up semantics: binding changes are asset-level authority.
        # Any change should create a new version snapshot for the affected assets.
        affected_old: dict[int, List[int]] = {}
        for fid, old_aid in conflicts.items():
            affected_old.setdefault(int(old_aid), []).append(int(fid))

        try:
            with conn:
                n = bind_files_to_asset(
                    conn,
                    asset_id=target_aid,
                    file_ids=changed_ids,
                    allow_rebind=bool(allow_rebind),
                    commit=False,
                )

                version_map: dict[int, int] = {}

                # Old assets: remove the moved file(s) from the new snapshot.
                for old_aid, moved_ids in affected_old.items():
                    try:
                        res = version_up_for_binding_change(
                            conn,
                            asset_id=int(old_aid),
                            removed_file_ids=list(moved_ids),
                            note="rebind: files moved away",
                        )
                        version_map[int(old_aid)] = int(res.new_version_id)
                    except Exception:
                        continue

                # Target asset: ensure newly bound files are included.
                try:
                    res_t = version_up_for_binding_change(
                        conn,
                        asset_id=int(target_aid),
                        removed_file_ids=None,
                        note="manual bind",
                    )
                    version_map[int(target_aid)] = int(res_t.new_version_id)
                except Exception:
                    pass

        except Exception as e:
            self._warn(str(e))
            return 0

        if n > 0:
            self._log_info(f"Manual bind: bound {n} file(s) to asset_id={target_aid}.")
            try:
                self.context.event_hub.db_changed.emit(
                    DbChanged(
                        reason="file_binding_changed",
                        payload={
                            "asset_id": target_aid,
                            "count": int(n),
                            "affected_assets": sorted({int(target_aid), *list(affected_old.keys())}),
                        },
                    )
                )
            except Exception:
                pass
        return int(n)

    def unbind_files(self, file_ids: List[int]) -> int:
        """Remove manual bindings for file_ids."""
        conn = self.context.db_connection
        if conn is None:
            return 0
        ids = [int(x) for x in file_ids if int(x) > 0]
        if not ids:
            return 0
        # Pre-fetch which assets will be affected so we can version-up with removals.
        pre_map = {}
        try:
            pre_map = get_bindings_for_files(conn, file_ids=ids)
        except Exception:
            pre_map = {}

        removed_by_asset: dict[int, List[int]] = {}
        for fid, aid in pre_map.items():
            removed_by_asset.setdefault(int(aid), []).append(int(fid))

        try:
            with conn:
                n = unbind_files(conn, file_ids=ids, commit=False)

                # Version-up any affected assets, removing the unbound file(s) from the new snapshot.
                for aid, rm_ids in removed_by_asset.items():
                    try:
                        version_up_for_binding_change(
                            conn,
                            asset_id=int(aid),
                            removed_file_ids=list(rm_ids),
                            note="manual unbind",
                        )
                    except Exception:
                        continue

        except Exception as e:
            self._warn(str(e))
            return 0
        if n > 0:
            self._log_info(f"Manual bind: unbound {n} file(s).")
            try:
                self.context.event_hub.db_changed.emit(
                    DbChanged(
                        reason="file_binding_changed",
                        payload={
                            "count": int(n),
                            "asset_ids": sorted({int(a) for a in removed_by_asset.keys()}),
                        },
                    )
                )
            except Exception:
                pass
        return int(n)

    # -----------------
    # UI helpers
    # -----------------

    def _warn(self, message: str) -> None:
        try:
            QMessageBox.warning(self.parent, "AssetHub", message)
        except Exception:
            return

    # -----------------
    # Logging helpers
    # -----------------

    def _log_info(self, message: str) -> None:
        try:
            self.context.log.info(str(message))
        except Exception:
            return

    def _log_warn(self, message: str) -> None:
        try:
            self.context.log.warn(str(message))
        except Exception:
            return
