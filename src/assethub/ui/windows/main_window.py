# src/assethub/ui/windows/main_window.py

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QTabWidget,
    QVBoxLayout,
)
from assethub.context import AppContext


class MainWindow(QMainWindow):
    """
    Main application window for AssetHub.

    Skeleton: just creates a tab widget with placeholder tabs.
    """

    def __init__(self, context: AppContext) -> None:
        super().__init__()

        self.context = context
        self.setWindowTitle("AssetHub (v0 skeleton)")

        central = QWidget(self)
        layout = QVBoxLayout(central)

        tabs = QTabWidget(central)
        tabs.addTab(QWidget(), "Library")
        tabs.addTab(QWidget(), "Detail")
        tabs.addTab(QWidget(), "Scan")
        tabs.addTab(QWidget(), "Settings")

        layout.addWidget(tabs)
        self.setCentralWidget(central)
        self._debug_print_context_status()

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
