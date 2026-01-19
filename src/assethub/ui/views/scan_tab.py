# src/assethub/ui/views/scan_tab.py

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Event
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QInputDialog,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from assethub.context import AppContext
from assethub.core.db.connection import get_connection
from assethub.core.db.file_records import purge_all_missing_file_records
from assethub.core.db.schema import initialize_schema
from assethub.core.health.checker import HealthChecker
from assethub.core.scanner.scanner import Scanner
from assethub.core.storage.roots import StorageManager, StorageRoot
from assethub.core.events.event_hub import DbChanged, ScanFinished, HealthFinished


class _WorkerSignals(QObject):
    finished = Signal(object)  # result object
    error = Signal(str)


class _CancelableWorker(QRunnable):
    """Run a callable in a thread pool with a shared cancel event."""

    def __init__(
        self,
        *,
        fn: Callable[[Event], Any],
        cancel_event: Event,
        signals: _WorkerSignals,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._cancel = cancel_event
        self.signals = signals

    def run(self) -> None:
        try:
            result = self._fn(self._cancel)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))
            return
        self.signals.finished.emit(result)


@dataclass(frozen=True)
class ScanSummary:
    files_indexed: int
    canceled: bool
    elapsed_s: float


@dataclass(frozen=True)
class HealthSummary:
    counts_by_state: dict[str, int]
    changed_rows: int
    canceled: bool
    elapsed_s: float


class ScanTab(QWidget):
    """Stage 7.1: Scan tab UI (v0.1).

    Features:
      - Register / remove storage roots
      - Scan registered roots
      - Run health check across all tracked files
      - Press ESC to cancel an active scan / health job
    """

    scan_completed = Signal()
    health_completed = Signal()

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context

        self._current_job: Optional[str] = None
        self._cancel_event: Optional[Event] = None

        self._build_ui()
        self.refresh_roots()

    # -------------------------
    # UI construction
    # -------------------------

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        # Roots table + root buttons
        root_layout.addWidget(QLabel("Storage Roots"))
        self.roots_table = QTableWidget(self)
        self.roots_table.setColumnCount(4)
        self.roots_table.setHorizontalHeaderLabels(["ID", "Name", "Path", "Status"])
        self.roots_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.roots_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.roots_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.roots_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.roots_table.customContextMenuRequested.connect(self._on_roots_context_menu)
        self.roots_table.horizontalHeader().setStretchLastSection(True)
        self.roots_table.setColumnHidden(0, True)  # hide ID
        root_layout.addWidget(self.roots_table)

        roots_btn_row = QHBoxLayout()
        self.btn_add_root = QPushButton("Add Root…")
        self.btn_remove_root = QPushButton("Remove Root")
        self.btn_add_root.clicked.connect(self._on_add_root)
        self.btn_remove_root.clicked.connect(self._on_remove_root)
        roots_btn_row.addWidget(self.btn_add_root)
        roots_btn_row.addWidget(self.btn_remove_root)
        roots_btn_row.addStretch(1)
        root_layout.addLayout(roots_btn_row)

        # Action buttons
        root_layout.addWidget(QLabel("Actions"))
        actions_row = QHBoxLayout()
        self.btn_scan = QPushButton("Scan Roots")
        self.btn_health = QPushButton("Run Health Check")
        self.btn_cleanup_missing = QPushButton("Cleanup MISSING Files")
        self.btn_scan.clicked.connect(self._on_scan)
        self.btn_health.clicked.connect(self._on_health_check)
        self.btn_cleanup_missing.clicked.connect(self._on_cleanup_missing)
        actions_row.addWidget(self.btn_scan)
        actions_row.addWidget(self.btn_health)
        actions_row.addWidget(self.btn_cleanup_missing)
        actions_row.addStretch(1)
        root_layout.addLayout(actions_row)

        # Status
        self.status_label = QLabel("Idle")

        root_layout.addWidget(QLabel("Status"))
        root_layout.addWidget(self.status_label)

    # -------------------------
    # Public API
    # -------------------------

    def request_cancel_current_job(self) -> None:
        """Request cancellation of the current job (scan/health)."""
        if self._cancel_event is None or self._current_job is None:
            return
        if not self._cancel_event.is_set():
            self._cancel_event.set()
            self.status_label.setText(f"Cancel requested ({self._current_job})…")
            try:
                self.context.log.warn(f"Cancel requested: {self._current_job}")
            except Exception:
                pass

    def refresh_roots(self) -> None:
        sm = self._require_storage_manager()
        roots = sm.list_roots()

        self.roots_table.setRowCount(len(roots))
        for row, r in enumerate(roots):
            self._set_root_row(row, r)

        self.roots_table.resizeColumnsToContents()

    # -------------------------
    # Slots
    # -------------------------

    @Slot()
    def _on_add_root(self) -> None:
        if self._current_job is not None:
            QMessageBox.information(self, "AssetHub", "A job is running. Cancel or wait before adding roots.")
            try:
                self.context.log.warn("Add root blocked: job is running")
            except Exception:
                pass
            return

        start_dir = self.context.config.data_root
        path = QFileDialog.getExistingDirectory(self, "Select Storage Root", start_dir)
        if not path:
            try:
                self.context.log.info("Add root canceled")
            except Exception:
                pass
            return

        sm = self._require_storage_manager()
        root = sm.register_root(path)
        try:
            self.context.log.info(f"Registered storage root: {root.name} ({root.root_path})")
        except Exception:
            pass
        self.refresh_roots()
        # Stage 7.5: notify other views.
        self.context.event_hub.db_changed.emit(
            DbChanged(reason="storage_root_registered", payload={"storage_id": int(root.id)})
        )

    @Slot()
    def _on_remove_root(self) -> None:
        if self._current_job is not None:
            QMessageBox.information(self, "AssetHub", "A job is running. Cancel or wait before removing roots.")
            try:
                self.context.log.warn("Remove root blocked: job is running")
            except Exception:
                pass
            return

        selected = self.roots_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "AssetHub", "Select a storage root to remove.")
            try:
                self.context.log.info("Remove root: no selection")
            except Exception:
                pass
            return
        row = selected[0].row()
        storage_id = self._root_id_for_row(row)
        if storage_id is None:
            return

        sm = self._require_storage_manager()
        # Lookup details (so we can block Unmanaged and show a friendly message)
        roots = {r.id: r for r in sm.list_roots()}
        root = roots.get(storage_id)
        if root is None:
            return

        if root.root_path is None or str(root.status).upper() == StorageManager.UNMANAGED_STATUS:
            QMessageBox.warning(self, "AssetHub", "Cannot remove the Unmanaged storage root.")
            try:
                self.context.log.warn("Remove root blocked: Unmanaged root")
            except Exception:
                pass
            return

        in_use = sm.count_files_for_storage(storage_id)
        if in_use > 0:
            QMessageBox.warning(
                self,
                "AssetHub",
                "Cannot remove this root because it is referenced by tracked files. "
                "Remove associated file records first, then try again.",
            )
            try:
                self.context.log.warn(
                    f"Remove root blocked: referenced by tracked files (storage_id={int(storage_id)}, file_count={int(in_use)})"
                )
            except Exception:
                pass
            return

        confirm = QMessageBox.question(
            self,
            "Remove Storage Root",
            f"Remove storage root '{root.display_label}'?\n\n{root.root_path}",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            try:
                self.context.log.info(f"Remove root canceled: storage_id={int(storage_id)}")
            except Exception:
                pass
            return

        sm.unregister_root(storage_id)
        try:
            self.context.log.info(f"Unregistered storage root: {root.display_label} ({root.root_path})")
        except Exception:
            pass
        self.refresh_roots()
        # Stage 7.5: notify other views.
        self.context.event_hub.db_changed.emit(
            DbChanged(reason="storage_root_unregistered", payload={"storage_id": int(storage_id)})
        )

    @Slot()
    def _on_scan(self) -> None:
        try:
            self.context.log.info("Scan roots: started")
        except Exception:
            pass
        self._start_job("scan", self._scan_job)

    @Slot()
    def _on_health_check(self) -> None:
        try:
            self.context.log.info("Health check: started")
        except Exception:
            pass
        self._start_job("health", self._health_job)

    @Slot()
    def _on_cleanup_missing(self) -> None:
        """Remove all tracked file records currently marked MISSING.

        This does NOT delete files from disk; it only removes DB tracking rows.
        """
        if self._current_job is not None:
            QMessageBox.information(self, "AssetHub", "A job is running. Cancel or wait before cleanup.")
            try:
                self.context.log.warn("Cleanup missing blocked: job is running")
            except Exception:
                pass
            return

        conn = self.context.db_connection
        if conn is None:
            QMessageBox.warning(self, "AssetHub", "Database is not available.")
            try:
                self.context.log.error("Cleanup missing failed: database is not available")
            except Exception:
                pass
            return

        row = conn.execute("SELECT COUNT(*) FROM file WHERE UPPER(integrity_state)='MISSING';").fetchone()
        missing_count = int(row[0]) if row and row[0] is not None else 0

        if missing_count <= 0:
            QMessageBox.information(self, "AssetHub", "No MISSING records were found in the database.")
            try:
                self.context.log.info("Cleanup missing: no MISSING records")
            except Exception:
                pass
            return

        confirm = QMessageBox.question(
            self,
            "Cleanup MISSING Files",
            (
                f"Found {missing_count} tracked file record(s) marked MISSING.\n\n"
                "Remove all MISSING records from the database?\n\n"
                "This does NOT delete files from disk; it only removes tracking rows."
            ),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            try:
                self.context.log.info("Cleanup missing canceled")
            except Exception:
                pass
            return

        deleted = purge_all_missing_file_records(conn)
        try:
            self.context.log.info(f"Cleanup missing: removed {deleted} MISSING file record(s) from database")
        except Exception:
            pass

        if deleted > 0:
            self.context.event_hub.db_changed.emit(
                DbChanged(reason="missing_records_purged", payload={"count": int(deleted)})
            )

    # -------------------------
    # Job control
    # -------------------------

    def _start_job(self, job_name: str, fn: Callable[[Event], Any]) -> None:
        if self._current_job is not None:
            QMessageBox.information(self, "AssetHub", "A job is already running. Press ESC to cancel it.")
            try:
                self.context.log.warn(f"Start job blocked: already running ({self._current_job})")
            except Exception:
                pass
            return

        if self.context.thread_pool is None:
            raise RuntimeError("AppContext thread_pool is not initialized")

        self._current_job = job_name
        self._cancel_event = Event()

        self._set_busy(True)
        self.status_label.setText(f"Running: {job_name}… (press ESC to cancel)")

        signals = _WorkerSignals()
        signals.finished.connect(self._on_job_finished)
        signals.error.connect(self._on_job_error)

        worker = _CancelableWorker(fn=fn, cancel_event=self._cancel_event, signals=signals)
        self.context.thread_pool.start(worker)

    @Slot(object)
    def _on_job_finished(self, result: object) -> None:
        job = self._current_job
        self._set_busy(False)
        self._current_job = None
        self._cancel_event = None

        if isinstance(result, ScanSummary):
            tag = "canceled" if result.canceled else "ok"
            self.status_label.setText(f"Scan complete ({tag})")
            try:
                self.context.log.info(
                    f"Scan roots: indexed {result.files_indexed} file(s) in {result.elapsed_s:.2f}s ({tag})"
                )
            except Exception:
                pass
            self.scan_completed.emit()
            # Stage 7.5: Central event hub emissions.
            self.context.event_hub.scan_finished.emit(
                ScanFinished(
                    summary={
                        "files_indexed": int(result.files_indexed),
                        "canceled": bool(result.canceled),
                        "elapsed_s": float(result.elapsed_s),
                    }
                )
            )
            if int(result.files_indexed) > 0:
                self.context.event_hub.db_changed.emit(
                    DbChanged(reason="scan_index_updated", payload={"files_indexed": int(result.files_indexed)})
                )
        elif isinstance(result, HealthSummary):
            tag = "canceled" if result.canceled else "ok"
            self.status_label.setText(f"Health check complete ({tag})")
            counts = ", ".join(f"{k}={v}" for k, v in sorted(result.counts_by_state.items()))
            try:
                self.context.log.info(f"Health check: {counts} in {result.elapsed_s:.2f}s ({tag})")
            except Exception:
                pass
            self.health_completed.emit()
            # Stage 7.5: Central event hub emissions.
            self.context.event_hub.health_finished.emit(
                HealthFinished(
                    summary={
                        "counts_by_state": dict(result.counts_by_state),
                        "changed_rows": int(result.changed_rows),
                        "canceled": bool(result.canceled),
                        "elapsed_s": float(result.elapsed_s),
                    }
                )
            )
            if int(result.changed_rows) > 0:
                self.context.event_hub.db_changed.emit(
                    DbChanged(reason="health_states_updated", payload={"changed_rows": int(result.changed_rows)})
                )
        else:
            self.status_label.setText(f"Done: {job or 'job'}")
            try:
                self.context.log.info(f"Finished job: {job or 'job'}")
            except Exception:
                pass

    @Slot(str)
    def _on_job_error(self, message: str) -> None:
        job = self._current_job
        self._set_busy(False)
        self._current_job = None
        self._cancel_event = None
        self.status_label.setText(f"Error: {job or 'job'}")
        try:
            self.context.log.error(f"{job or 'job'} failed: {message}")
        except Exception:
            pass
        QMessageBox.critical(self, "AssetHub", f"{job or 'Job'} failed:\n\n{message}")

    def _set_busy(self, busy: bool) -> None:
        self.btn_add_root.setEnabled(not busy)
        self.btn_remove_root.setEnabled(not busy)
        self.btn_scan.setEnabled(not busy)
        self.btn_health.setEnabled(not busy)
        self.btn_cleanup_missing.setEnabled(not busy)

    # -------------------------
    # Background task implementations
    # -------------------------

    def _scan_job(self, cancel: Event) -> ScanSummary:
        start = time.perf_counter()
        conn = get_connection(self.context.config.db_path)
        try:
            initialize_schema(conn)
            storage = StorageManager(conn)
            storage.ensure_unmanaged_storage()
            scanner = Scanner(conn, storage)
            res = scanner.scan_all(cancel_check=cancel.is_set)
            elapsed = time.perf_counter() - start
            return ScanSummary(files_indexed=res.files_indexed, canceled=res.canceled, elapsed_s=elapsed)
        finally:
            conn.close()

    def _health_job(self, cancel: Event) -> HealthSummary:
        start = time.perf_counter()
        conn = get_connection(self.context.config.db_path)
        try:
            initialize_schema(conn)
            storage = StorageManager(conn)
            storage.ensure_unmanaged_storage()
            health = HealthChecker(conn, storage)
            results = health.check_all_files(cancel_check=cancel.is_set)
            counts: dict[str, int] = {}
            for r in results:
                counts[r.new_state] = counts.get(r.new_state, 0) + 1
            elapsed = time.perf_counter() - start
            return HealthSummary(
                counts_by_state=counts,
                changed_rows=int(getattr(health, "last_changed_count", 0)),
                canceled=cancel.is_set(),
                elapsed_s=elapsed,
            )
        finally:
            conn.close()

    # -------------------------
    # Helpers
    # -------------------------

    def _set_root_row(self, row: int, root: StorageRoot) -> None:
        id_item = QTableWidgetItem(str(root.id))
        id_item.setData(Qt.ItemDataRole.UserRole, int(root.id))

        name_item = QTableWidgetItem(root.display_label)
        if (root.display_name or "").strip():
            # Preserve the underlying default name for debugging.
            name_item.setToolTip(f"Default name: {root.name}")
        path_item = QTableWidgetItem(root.root_path or "(Unmanaged)")
        status_item = QTableWidgetItem(root.status)

        self.roots_table.setItem(row, 0, id_item)
        self.roots_table.setItem(row, 1, name_item)
        self.roots_table.setItem(row, 2, path_item)
        self.roots_table.setItem(row, 3, status_item)

    # -------------------------
    # Context menu: storage roots
    # -------------------------

    @Slot(object)
    def _on_roots_context_menu(self, pos) -> None:
        """Right-click context menu for storage roots (Stage 7.6.2)."""
        try:
            idx = self.roots_table.indexAt(pos)
            if not idx.isValid():
                return

            row = idx.row()
            storage_id = self._root_id_for_row(row)
            if storage_id is None:
                return

            sm = self._require_storage_manager()
            roots = {r.id: r for r in sm.list_roots()}
            root = roots.get(int(storage_id))
            if root is None:
                return

            menu = QMenu(self)

            act_rename = menu.addAction("Rename (display name)…")
            act_remove = menu.addAction("Remove root from tracking…")

            # Unmanaged is protected from destructive actions.
            if root.root_path is None or str(root.status).upper() == StorageManager.UNMANAGED_STATUS:
                act_rename.setEnabled(False)
                act_remove.setEnabled(False)

            chosen = menu.exec(self.roots_table.viewport().mapToGlobal(pos))
            if chosen is None:
                return

            if chosen == act_rename:
                self._rename_storage_root(root)
            elif chosen == act_remove:
                self._remove_root_from_tracking(root)
        except Exception:
            return

    def _rename_storage_root(self, root: StorageRoot) -> None:
        """Prompt the user to set/clear a storage root display name."""
        if root.root_path is None or str(root.status).upper() == StorageManager.UNMANAGED_STATUS:
            QMessageBox.warning(self, "AssetHub", "Cannot rename the Unmanaged storage root.")
            return

        current = (root.display_name or "").strip()
        text, ok = QInputDialog.getText(
            self,
            "Rename storage root",
            "Display name (leave empty to clear):",
            text=current,
        )
        if not ok:
            return

        sm = self._require_storage_manager()
        try:
            old, new = sm.set_display_name(int(root.id), text)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "AssetHub", f"Rename failed:\n\n{exc}")
            return

        # Refresh this table immediately.
        self.refresh_roots()

        try:
            self.context.log.info(
                f"Storage root renamed: id={int(root.id)} '{(old or '')}' -> '{(new or '')}'"
            )
        except Exception:
            pass

        self.context.event_hub.db_changed.emit(
            DbChanged(
                reason="storage_renamed",
                payload={"storage_id": int(root.id), "old": old or "", "new": new or ""},
            )
        )

    def _remove_root_from_tracking(self, root: StorageRoot) -> None:
        """Remove a storage root and all associated tracked file rows (DB-only).

        This is the destructive counterpart to the "Remove Root" button, which
        only unregisters roots that have no associated file records.

        Notes:
            - Does not delete files from disk.
            - Disallows Unmanaged.
        """
        if self._current_job is not None:
            QMessageBox.information(
                self, "AssetHub", "A job is running. Cancel or wait before removing roots."
            )
            return

        if root.root_path is None or str(root.status).upper() == StorageManager.UNMANAGED_STATUS:
            QMessageBox.warning(self, "AssetHub", "Cannot remove the Unmanaged storage root.")
            return

        sm = self._require_storage_manager()
        try:
            count = sm.count_files_for_storage(int(root.id))
        except Exception:
            count = 0

        msg = (
            f"Remove storage root from tracking?\n\n"
            f"Name: {root.display_label}\n"
            f"Path: {root.root_path}\n\n"
            f"This will remove {int(count)} tracked file record(s) from the database.\n"
            "This does NOT delete files from disk."
        )

        confirm = QMessageBox.question(self, "Remove root from tracking", msg)
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            removed = sm.remove_root_from_tracking(int(root.id))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "AssetHub", f"Remove failed:\n\n{exc}")
            return

        # Refresh Scan roots immediately.
        self.refresh_roots()

        try:
            self.context.log.warn(
                f"Removed root from tracking: {root.display_label} ({root.root_path}); removed {int(removed)} file record(s)"
            )
        except Exception:
            pass

        # Notify other views (Library/Settings) to refresh.
        self.context.event_hub.db_changed.emit(
            DbChanged(
                reason="storage_removed",
                payload={"storage_id": int(root.id), "files_removed": int(removed)},
            )
        )
    def _root_id_for_row(self, row: int) -> Optional[int]:
        item = self.roots_table.item(row, 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        try:
            return int(data)
        except Exception:
            return None

    def _require_storage_manager(self) -> StorageManager:
        sm = self.context.storage_manager
        if sm is None:
            raise RuntimeError("StorageManager is not initialized")
        return sm
