# tests/test_ui_imports.py

import pytest


def test_main_window_import() -> None:
    try:
        import PySide6  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("PySide6 not installed in this test environment")

    from assethub.ui.windows.main_window import MainWindow  # noqa: F401


def test_settings_tab_import() -> None:
    try:
        import PySide6  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("PySide6 not installed in this test environment")

    from assethub.ui.views.settings_tab import SettingsTab  # noqa: F401
