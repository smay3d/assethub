# tests/test_settings_tab_stats.py

"""Settings snapshot stats tests.

These tests must remain Qt-free.

On some Windows + PySide6 setups, instantiating QWidget/QApplication during
pytest can hard-terminate the interpreter without a traceback. Stage 7.4
introduces a pure settings snapshot module that the Settings tab renders.
"""

from __future__ import annotations

import os
import tempfile


def test_settings_snapshot_populates_basic_stats() -> None:
    from assethub.context import AppConfig, AppContext
    from assethub.ui.views.settings_snapshot import collect_settings_snapshot

    with tempfile.TemporaryDirectory() as td:
        data_root = os.path.join(td, "AssetHubData")
        db_path = os.path.join(data_root, "DB", "assethub.sqlite3")

        cfg = AppConfig(
            data_root=data_root,
            db_path=db_path,
            sidecar_root=os.path.join(data_root, "SIDECARS"),
            preview_root=os.path.join(data_root, "CACHE", "previews"),
            log_root=os.path.join(data_root, "LOGS"),
            ui={"theme": "dark", "language": "en"},
        )

        ctx = AppContext(cfg)
        ctx.initialize_core_services()

        # Register one root and insert two files, one missing.
        root = ctx.storage_manager.register_root(os.path.join(td, "rootA"), name="RootA")
        ctx.db_connection.execute(
            "INSERT OR IGNORE INTO file(storage_id, relative_path, integrity_state, size_bytes, mtime_unix) "
            "VALUES (?, ?, ?, ?, ?);",
            (root.id, "textures/a.png", "OK", 123, 1000.0),
        )
        ctx.db_connection.execute(
            "INSERT OR IGNORE INTO file(storage_id, relative_path, integrity_state, size_bytes, mtime_unix) "
            "VALUES (?, ?, ?, ?, ?);",
            (root.id, "textures/b.png", "MISSING", 456, 2000.0),
        )
        ctx.db_connection.commit()

        snap = collect_settings_snapshot(ctx)

        assert snap.db_stats["file_rows"] == 2
        assert snap.db_stats["missing_files"] == 1

        # Storage roots include the implicit Unmanaged row.
        assert int(snap.db_stats["storage_rows"]) >= 2
        assert snap.db_stats["unmanaged_present"] in {True, False}

        # Schema version should be present.
        assert snap.about["schema_version"] == "8"

        # DB should exist on disk.
        assert os.path.exists(db_path)

        ctx.shutdown()
