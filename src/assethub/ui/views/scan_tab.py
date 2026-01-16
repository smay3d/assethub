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
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from assethub.context import AppContext
from assethub.core.db.connection import get_connection
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
        self.btn_scan.clicked.connect(self._on_scan)
        self.btn_health.clicked.connect(self._on_health_check)
        actions_row.addWidget(self.btn_scan)
        actions_row.addWidget(self.btn_health)
        actions_row.addStretch(1)
        root_layout.addLayout(actions_row)

        # Status + log
        self.status_label = QLabel("Idle")
        self.log_box = QTextEdit(self)
        self.log_box.setReadOnly(True)

        root_layout.addWidget(QLabel("Status"))
        root_layout.addWidget(self.status_label)
        root_layout.addWidget(QLabel("Summary"))
        root_layout.addWidget(self.log_box)

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
            self._append_log(f"[cancel] Requested cancel for {self._current_job} job")

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
            return

        start_dir = self.context.config.data_root
        path = QFileDialog.getExistingDirectory(self, "Select Storage Root", start_dir)
        if not path:
            return

        sm = self._require_storage_manager()
        root = sm.register_root(path)
        self._append_log(f"[storage] Registered root: {root.name} ({root.root_path})")
        self.refresh_roots()
        # Stage 7.5: notify other views.
        self.context.event_hub.db_changed.emit(
            DbChanged(reason="storage_root_registered", payload={"storage_id": int(root.id)})
        )

    @Slot()
    def _on_remove_root(self) -> None:
        if self._current_job is not None:
            QMessageBox.information(self, "AssetHub", "A job is running. Cancel or wait before removing roots.")
            return

        selected = self.roots_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "AssetHub", "Select a storage root to remove.")
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
            return

        in_use = sm.count_files_for_storage(storage_id)
        if in_use > 0:
            QMessageBox.warning(
                self,
                "AssetHub",
                "Cannot remove this root because it is referenced by tracked files. "
                "Remove associated file records first, then try again.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Remove Storage Root",
            f"Remove storage root '{root.name}'?\n\n{root.root_path}",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        sm.unregister_root(storage_id)
        self._append_log(f"[storage] Unregistered root: {root.name} ({root.root_path})")
        self.refresh_roots()
        # Stage 7.5: notify other views.
        self.context.event_hub.db_changed.emit(
            DbChanged(reason="storage_root_unregistered", payload={"storage_id": int(storage_id)})
        )

    @Slot()
    def _on_scan(self) -> None:
        self._start_job("scan", self._scan_job)

    @Slot()
    def _on_health_check(self) -> None:
        self._start_job("health", self._health_job)

    # -------------------------
    # Job control
    # -------------------------

    def _start_job(self, job_name: str, fn: Callable[[Event], Any]) -> None:
        if self._current_job is not None:
            QMessageBox.information(self, "AssetHub", "A job is already running. Press ESC to cancel it.")
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
            self._append_log(f"[scan] Indexed {result.files_indexed} files in {result.elapsed_s:.2f}s ({tag})")
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
            self._append_log(f"[health] {counts} in {result.elapsed_s:.2f}s ({tag})")
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
            self._append_log(f"[job] Finished {job or 'job'}")

    @Slot(str)
    def _on_job_error(self, message: str) -> None:
        job = self._current_job
        self._set_busy(False)
        self._current_job = None
        self._cancel_event = None
        self.status_label.setText(f"Error: {job or 'job'}")
        self._append_log(f"[error] {job or 'job'}: {message}")
        QMessageBox.critical(self, "AssetHub", f"{job or 'Job'} failed:\n\n{message}")

    def _set_busy(self, busy: bool) -> None:
        self.btn_add_root.setEnabled(not busy)
        self.btn_remove_root.setEnabled(not busy)
        self.btn_scan.setEnabled(not busy)
        self.btn_health.setEnabled(not busy)

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

    def _append_log(self, line: str) -> None:
        self.log_box.append(line)

    def _set_root_row(self, row: int, root: StorageRoot) -> None:
        id_item = QTableWidgetItem(str(root.id))
        id_item.setData(Qt.ItemDataRole.UserRole, int(root.id))

        name_item = QTableWidgetItem(root.name)
        path_item = QTableWidgetItem(root.root_path or "(Unmanaged)")
        status_item = QTableWidgetItem(root.status)

        self.roots_table.setItem(row, 0, id_item)
        self.roots_table.setItem(row, 1, name_item)
        self.roots_table.setItem(row, 2, path_item)
        self.roots_table.setItem(row, 3, status_item)

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
