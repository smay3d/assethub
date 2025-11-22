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
