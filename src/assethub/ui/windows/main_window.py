# src/assethub/ui/windows/main_window.py

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from assethub.ui.views.scan_tab import ScanTab
from assethub.context import AppContext


class MainWindow(QMainWindow):
    """
    Main application window for AssetHub.

    Skeleton: just creates a tab widget with placeholder tabs.
    """

    def __init__(self, context: AppContext) -> None:
        super().__init__()

        self.context = context
        self.setWindowTitle("AssetHub (v0.1)")

        central = QWidget(self)
        layout = QVBoxLayout(central)

        tabs = QTabWidget(central)

        # Placeholder tabs (Stage 7.x will implement these)
        tabs.addTab(QWidget(), "Library")
        tabs.addTab(QWidget(), "Detail")

        # Stage 7.1 implemented tab
        self.scan_tab = ScanTab(self.context)
        tabs.addTab(self.scan_tab, "Scan")

        tabs.addTab(QWidget(), "Settings")

        layout.addWidget(tabs)
        self.setCentralWidget(central)

        # Global cancel shortcut (press ESC)
        self._esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._esc_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._esc_shortcut.activated.connect(self._on_escape)

        self._debug_print_context_status()

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
