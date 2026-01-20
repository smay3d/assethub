# src/assethub/context.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Dict

try:
    from PySide6.QtCore import QThreadPool  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    QThreadPool = None  # type: ignore

import threading

from .core.storage.roots import StorageManager
from .core.scanner.scanner import Scanner
from .core.previews.manager import PreviewManager
from .core.sidecar.manager import SidecarManager
from .core.health.checker import HealthChecker
from .core.events.event_hub import EventHub
from .core.utils.app_log import AppLog
from .core.db.connection import get_connection
from .core.db.schema import initialize_schema, get_schema_version


@dataclass
class AppConfig:
    """Minimal configuration used by `AppContext`.

    This will expand over time. For v0, it primarily stores key paths and
    simple UI settings.
    """

    data_root: str
    db_path: str
    sidecar_root: str
    preview_root: str
    log_root: str
    ui: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AppContext:
    """Composition root for the running application.

    Owns long-lived services (DB connection, StorageManager, Scanner, etc.)
    and provides a single shared access point for UI and background jobs.
    """

    config: AppConfig

    # Stage 7.5: central non-Qt signaling
    event_hub: EventHub = field(default_factory=EventHub)

    # Stage 7.6: global app log (Qt-free; UI attaches a sink)
    log: AppLog = field(default_factory=AppLog)

    # Core subsystems:
    db_connection: Optional[Any] = None
    storage_manager: Optional[StorageManager] = None
    scanner: Optional[Scanner] = None
    preview_manager: Optional[PreviewManager] = None
    sidecar_manager: Optional[SidecarManager] = None
    health_checker: Optional[HealthChecker] = None
    thread_pool: Optional[QThreadPool] = None

    class _ThreadPoolFallback:
        """Very small fallback pool for non-Qt environments (tests/CI).

        This is not a full QThreadPool replacement. It only supports `.start(runnable)`
        where runnable has a `.run()` method.
        """

        def start(self, runnable: Any) -> None:
            t = threading.Thread(target=getattr(runnable, "run"), daemon=True)
            t.start()

    def initialize_core_services(self) -> None:
        """
        Initialize all core application services.

        Services are created in dependency order and are owned by the
        AppContext for the lifetime of the application.
        """
        # Initialize core services in dependency order.

        # Database (open connection and ensure minimal schema)
        self.db_connection = get_connection(self.config.db_path)
        initialize_schema(self.db_connection)
        try:
            schema_v = get_schema_version(self.db_connection)
            self.log.info(f"DB schema ready (v{schema_v})")
        except Exception:
            # Logging must never prevent startup.
            self.log.info("DB schema ready")

        # Storage and indexing
        self.storage_manager = StorageManager(self.db_connection)
        self.storage_manager.ensure_unmanaged_storage()  # guarantee Unmanaged storage exists
        self.scanner = Scanner(self.db_connection, self.storage_manager)

        # Health checking (DB + Storage dependent)
        self.health_checker = HealthChecker(self.db_connection, self.storage_manager)

        # Auxiliary managers
        self.sidecar_manager = SidecarManager(self.config.sidecar_root)
        self.preview_manager = PreviewManager()

        # Shared Qt thread pool for background tasks (fallback if Qt not installed)
        if QThreadPool is not None:
            self.thread_pool = QThreadPool.globalInstance()
        else:  # pragma: no cover
            self.thread_pool = self._ThreadPoolFallback()

    def shutdown(self) -> None:
        """
        Cleanly release resources owned by the application context.

        This should be called when the application is exiting.
        """
        conn = self.db_connection
        if conn is not None:
            conn.close()
            self.db_connection = None