# src/assethub/context.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Dict


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

    # Core subsystems (to be wired in later stages):
    db_connection: Optional[Any] = None
    storage_manager: Optional[Any] = None
    scanner: Optional[Any] = None
    preview_manager: Optional[Any] = None
    sidecar_manager: Optional[Any] = None
    health_checker: Optional[Any] = None
    thread_pool: Optional[Any] = None  # Will likely be a QThreadPool

    def initialize_core_services(self) -> None:
        """
        Initialize core services.

        This will be filled in a later stage when the actual implementations
        exist. For now it's a structural placeholder.
        """

        # TODO: instantiate db_connection, storage_manager, etc.
        pass