"""Clipboard helpers.

Kept tiny and defensive. In unit tests (no QApplication), these are no-ops.
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication


def set_clipboard_text(text: str) -> None:
    try:
        app = QGuiApplication.instance()
        if app is None:
            return
        cb = QGuiApplication.clipboard()
        if cb is None:
            return
        cb.setText(text or "")
    except Exception:
        return
