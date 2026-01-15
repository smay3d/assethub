# src/assethub/ui/windows/main_window.py

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from assethub import __version__
from assethub.ui.views.library_tab import LibraryTab
from assethub.ui.views.scan_tab import ScanTab
from assethub.ui.views.settings_tab import SettingsTab
from assethub.context import AppContext


class MainWindow(QMainWindow):
    """
    Main application window for AssetHub.

    Skeleton: just creates a tab widget with placeholder tabs.
    """

    def __init__(self, context: AppContext) -> None:
        super().__init__()

        self.context = context
        self.setWindowTitle(f"AssetHub (v{__version__})")

        central = QWidget(self)
        layout = QVBoxLayout(central)

        self.tabs = QTabWidget(central)

        # Stage 7.2 implemented tab
        self.library_tab = LibraryTab(self.context)
        self.tabs.addTab(self.library_tab, "Library")

        # Stage 7.1 implemented tab
        self.scan_tab = ScanTab(self.context)
        self.tabs.addTab(self.scan_tab, "Scan")

        # Stage 7.4 implemented tab
        self.settings_tab = SettingsTab(self.context)
        self.tabs.addTab(self.settings_tab, "Settings")

        # Refresh Library after scans/health checks.
        self.scan_tab.scan_completed.connect(self.library_tab.refresh)
        self.scan_tab.health_completed.connect(self.library_tab.refresh)

        # Keep Settings current when system state changes.
        self.scan_tab.scan_completed.connect(self.settings_tab.refresh)
        self.scan_tab.health_completed.connect(self.settings_tab.refresh)

        # Auto-refresh Settings whenever user enters the tab.
        self.tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        # Global cancel shortcut (press ESC)
        self._esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._esc_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._esc_shortcut.activated.connect(self._on_escape)

        self._debug_print_context_status()

    def _on_tab_changed(self, index: int) -> None:
        w = self.tabs.widget(index)
        if w is self.settings_tab:
            self.settings_tab.refresh()

    def _on_escape(self) -> None:
        """Forward ESC to the active cancellable job (if any)."""
        if hasattr(self, "scan_tab"):
            self.scan_tab.request_cancel_current_job()

    def _debug_print_context_status(self) -> None:
        """
        Temporary Stage 5.6 diagnostic:
        Print the initialization status of core managers to the console.
        """
        print("\n=== AssetHub Stage 5.6 Context Check ===")
        print(f"Context object:     {type(self.context).__name__}")
        print(f"Storage Manager:    {type(self.context.storage_manager).__name__}")
        print(f"Scanner:            {type(self.context.scanner).__name__}")
        print(f"Preview Manager:    {type(self.context.preview_manager).__name__}")
        print(f"Sidecar Manager:    {type(self.context.sidecar_manager).__name__}")
        print(f"Health Checker:     {type(self.context.health_checker).__name__}")
        print(f"Thread Pool:        {self.context.thread_pool}")
        print("=======================================\n")
