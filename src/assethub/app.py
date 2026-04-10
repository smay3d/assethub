# src/assethub/app.py

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtWidgets import QApplication

from .context import AppContext
from .config.loader import load_app_config
from .ui.windows.main_window import MainWindow


_qt_app: Optional[QApplication] = None


def _ensure_qt_application() -> QApplication:
    """Create the QApplication singleton if it doesn't exist."""
    global _qt_app

    if _qt_app is None:
        _qt_app = QApplication(sys.argv)

    return _qt_app


def run_app() -> None:
    """
    Main application entry point for AssetHub.

    Startup sequence (Stage 5.6):
    1. Load config.
    2. Create AppContext.
    3. Initialize core services (managers, thread pool).
    4. Construct and show MainWindow.
    5. Enter Qt event loop.
    """
    app = _ensure_qt_application()

    # QSettings relies on org/app name being set before first use.
    app.setOrganizationName("AssetHub")
    app.setApplicationName("AssetHub")

    # Fusion gives consistent cross-platform appearance and works well with
    # custom palettes (required for reliable dark mode).
    app.setStyle("Fusion")

    # Apply QSS and saved theme (dark/light) before any widgets are created.
    from assethub.ui.style.qss import _APP_QSS, apply_theme, is_dark_mode_enabled  # noqa: PLC0415
    app.setStyleSheet(_APP_QSS)
    apply_theme(is_dark_mode_enabled())

    config = load_app_config()
    context = AppContext(config=config)
    context.initialize_core_services()

    window = MainWindow(context)
    window.show()

    sys.exit(app.exec())
