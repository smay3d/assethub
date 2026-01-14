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
from .core.db.connection import get_connection
from .core.db.schema import initialize_schema


@dataclass
class AppConfig:
    """
    Minimal config representation used by AppContext.

    This will be extended in later stages, but for now stores basic paths
    and UI-related settings.
    """

    data_root: str
    db_path: str
    sidecar_root: str
    preview_root: str
    log_root: str
    ui: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AppContext:
    """
    AppContext is the composition root of the AssetHub application.

    It owns and initializes all long-lived core services such as the
    database connection, storage manager, scanner, and health checker.
    UI layers and other subsystems should treat AppContext as the single
    authoritative access point for shared application state.

    AppContext is responsible for the lifetime of the resources it
    creates and must be explicitly shut down when the application exits.
    """

    config: AppConfig

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

        # Storage and indexing
        self.storage_manager = StorageManager(self.db_connection)
        self.storage_manager.ensure_unmanaged_storage() # guarantee Unmanaged storage exists
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