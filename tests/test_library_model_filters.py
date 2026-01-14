# tests/test_library_model_filters.py

import pytest


def test_library_model_and_proxy_filters() -> None:
    try:
        from PySide6.QtCore import QCoreApplication, Qt
    except ModuleNotFoundError:
        pytest.skip("PySide6 not installed in this test environment")

    # Ensure a Qt application instance exists for QObject-based models.
    app = QCoreApplication.instance()
    if app is None:
        _ = QCoreApplication([])

    from assethub.ui.models.file_table_model import FileRow, FileTableModel
    from assethub.ui.views.library_tab import FileFilterProxyModel

    model = FileTableModel()
    rows = [
        FileRow(
            file_id=1,
            storage_id=10,
            version_id=None,
            storage_name="RootA",
            relative_path="textures/wood_planks.png",
            filename="wood_planks.png",
            integrity_state="OK",
            size_bytes=2048,
            mtime_unix=1000.0,
            created_at="2025-01-01 00:00:00",
        ),
        FileRow(
            file_id=2,
            storage_id=10,
            version_id=None,
            storage_name="RootA",
            relative_path="textures/metal_plate.png",
            filename="metal_plate.png",
            integrity_state="MISSING",
            size_bytes=1024,
            mtime_unix=2000.0,
            created_at="2025-01-01 00:00:00",
        ),
        FileRow(
            file_id=3,
            storage_id=20,
            version_id=5,
            storage_name="RootB",
            relative_path="refs/moodboard.jpg",
            filename="moodboard.jpg",
            integrity_state="UNRESOLVED",
            size_bytes=999,
            mtime_unix=3000.0,
            created_at="2025-01-01 00:00:00",
        ),
    ]
    model.set_rows(rows, total_in_db=3, truncated=False)

    proxy = FileFilterProxyModel()
    proxy.setSourceModel(model)

    assert proxy.rowCount() == 3

    proxy.set_integrity("MISSING")
    assert proxy.rowCount() == 1

    proxy.set_integrity(None)
    proxy.set_storage_id(20)
    assert proxy.rowCount() == 1

    proxy.set_storage_id(None)
    proxy.set_search_text("wood")
    assert proxy.rowCount() == 1

    # Sorting: size column ("Size") should sort by raw bytes, not display text.
    size_col = 6  # see FileTableModel column order
    proxy.set_search_text("")
    proxy.sort(size_col, Qt.SortOrder.AscendingOrder)
    first = proxy.index(0, 0)
    first_src = proxy.mapToSource(first)
    first_id = model.file_id_for_row(first_src.row())
    assert first_id == 3  # 999 bytes smallest
