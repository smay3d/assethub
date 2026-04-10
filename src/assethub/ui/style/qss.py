# src/assethub/ui/style/qss.py
"""
Theme helpers for AssetHub.

Provides light/dark mode support via QPalette + QSS.
All QSS colors use palette() references so they adapt to whichever palette
is active — there is only one stylesheet, not separate light/dark variants.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

SETTINGS_KEY_DARK_MODE = "ui/dark_mode"

# Shared stylesheet that uses palette() references.
# Applies correctly under both the default (light) and dark palette.
_APP_QSS = """
/* ---- Group boxes ---- */
QGroupBox {
    font-weight: 600;
    border: 1px solid palette(mid);
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}

/* ---- Tables ---- */
QTableView {
    gridline-color: palette(mid);
}
QTableView::item {
    padding: 1px 6px;
}
QHeaderView::section {
    background-color: palette(button);
    color: palette(buttonText);
    padding: 4px 8px;
    border: none;
    border-right: 1px solid palette(mid);
    border-bottom: 1px solid palette(mid);
    font-weight: 600;
}
QHeaderView::section:first {
    border-left: none;
}

/* ---- Tab bar ---- */
QTabBar::tab {
    padding: 5px 16px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    border-bottom: 2px solid palette(highlight);
}
QTabBar::tab:hover:!selected {
    border-bottom: 2px solid palette(midlight);
}

/* ---- Mode-toggle tool buttons (Files | Assets) ---- */
QToolButton[checkable="true"]:checked {
    background-color: palette(highlight);
    color: palette(highlightedText);
    border-radius: 3px;
    padding: 2px 6px;
}
QToolButton[checkable="true"]:!checked {
    border-radius: 3px;
    padding: 2px 6px;
}
QToolButton[checkable="true"]:!checked:hover {
    background-color: palette(midlight);
}

/* ---- Log / plain-text area ---- */
QPlainTextEdit {
    font-family: Consolas, "Courier New", monospace;
    font-size: 11px;
}

/* ---- Splitter handles (hairline) ---- */
QSplitter::handle {
    background: palette(mid);
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}

/* ---- Scroll bars (Fusion style override — slimmer) ---- */
QScrollBar:vertical {
    width: 10px;
}
QScrollBar:horizontal {
    height: 10px;
}
"""


def _build_dark_palette() -> QPalette:
    """Return a dark QPalette for AssetHub."""
    p = QPalette()

    # Main surface colors
    p.setColor(QPalette.ColorRole.Window,        QColor(45, 45, 48))
    p.setColor(QPalette.ColorRole.WindowText,    QColor(210, 210, 210))
    p.setColor(QPalette.ColorRole.Base,          QColor(30, 30, 32))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(38, 38, 42))
    p.setColor(QPalette.ColorRole.Text,          QColor(210, 210, 210))

    # Buttons / controls
    p.setColor(QPalette.ColorRole.Button,        QColor(58, 58, 62))
    p.setColor(QPalette.ColorRole.ButtonText,    QColor(210, 210, 210))

    # Accents & links
    p.setColor(QPalette.ColorRole.Highlight,        QColor(45, 95, 175))
    p.setColor(QPalette.ColorRole.HighlightedText,  QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link,             QColor(90, 150, 230))
    p.setColor(QPalette.ColorRole.BrightText,       QColor(255, 100, 100))

    # Borders / separators
    p.setColor(QPalette.ColorRole.Mid,      QColor(70, 70, 75))
    p.setColor(QPalette.ColorRole.Midlight, QColor(80, 80, 86))
    p.setColor(QPalette.ColorRole.Dark,     QColor(25, 25, 27))
    p.setColor(QPalette.ColorRole.Shadow,   QColor(10, 10, 12))

    # Tooltip
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(60, 60, 65))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(210, 210, 210))

    # Disabled colors (keep visually distinct but muted)
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(100, 100, 105))

    return p


def apply_theme(dark: bool) -> None:
    """Apply light or dark theme to the running QApplication."""
    app = QApplication.instance()
    if app is None:
        return
    if dark:
        app.setPalette(_build_dark_palette())
    else:
        # Restore the default Fusion palette (already set by setStyle).
        app.setPalette(QPalette())
    # The shared QSS is palette()-aware and does not need re-applying.


def is_dark_mode_enabled() -> bool:
    """Read dark mode preference from QSettings."""
    s = QSettings()
    val = s.value(SETTINGS_KEY_DARK_MODE, False)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


def set_dark_mode(dark: bool) -> None:
    """Persist dark mode preference and immediately apply the new theme."""
    s = QSettings()
    s.setValue(SETTINGS_KEY_DARK_MODE, dark)
    apply_theme(dark)
