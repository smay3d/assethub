# src/assethub/ui/views/__init__.py
"""View widgets for different screens (Library, Scan, Settings, etc.).

NOTE:
We avoid importing PySide6-based widgets at package import time.
Eager imports here can trigger Qt initialization during unit tests or other
non-GUI contexts, and on some platforms it can even terminate the interpreter.

Import views directly from their modules, e.g.:
  from assethub.ui.views.library_tab import LibraryTab
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .file_detail_pane import FileDetailPane
    from .library_tab import LibraryTab
    from .scan_tab import ScanTab
    from .settings_tab import SettingsTab

__all__ = ["LibraryTab", "FileDetailPane", "ScanTab", "SettingsTab"]
