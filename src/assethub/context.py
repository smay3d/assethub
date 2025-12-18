# src/assethub/context.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Dict

from PySide6.QtCore import QThreadPool

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
    Global application context.

    Holds references to core subsystems so they can be shared between
    the UI, scanner, and other components.
    """

    config: AppConfig

    # Core subsystems (wired in Stage 5.6, implemented later):
    db_connection: Optional[Any] = None
    storage_manager: Optional[StorageManager] = None
    scanner: Optional[Scanner] = None
    preview_manager: Optional[PreviewManager] = None
    sidecar_manager: Optional[SidecarManager] = None
    health_checker: Optional[HealthChecker] = None
    thread_pool: Optional[QThreadPool] = None

    def initialize_core_services(self) -> None:
        """
        Initialize core service objects.

        Stage 6.1:
          - Open/create the SQLite database.
          - Ensure the minimal v0 schema exists.

        Stage 5.6 still applies for the remaining services:
          - Construct manager instances and the shared thread pool.
        """

        # Stage 6.1: create/open DB and ensure minimal schema exists.
        self.db_connection = get_connection(self.config.db_path)
        initialize_schema(self.db_connection)

        self.storage_manager = StorageManager(self.db_connection)
        # Stage 6.2: guarantee Unmanaged storage exists
        self.storage_manager.ensure_unmanaged_storage()
        self.sidecar_manager = SidecarManager(self.config.sidecar_root)
        self.preview_manager = PreviewManager()
        self.health_checker = HealthChecker()
        self.scanner = Scanner()

        # Shared Qt thread pool for background tasks
        self.thread_pool = QThreadPool.globalInstance()
