# tests/test_settings_tab_refresh.py

from __future__ import annotations

from pathlib import Path

from assethub.context import AppConfig, AppContext
from assethub.ui.views.settings_snapshot import collect_settings_snapshot


def test_settings_snapshot_refresh_smoke(tmp_path: Path) -> None:
    """Qt-free smoke test for Stage 7.4 Settings data.

    GUI/widget tests with PySide6 are prone to hard interpreter termination on
    some Windows setups when run under pytest. We instead verify the underlying
    snapshot logic that the Settings tab renders.
    """

    cfg = AppConfig(
        data_root=str(tmp_path / "AssetHub"),
        db_path=str(tmp_path / "AssetHub" / "DB" / "assethub.sqlite3"),
        sidecar_root=str(tmp_path / "AssetHub" / "SIDECARS"),
        preview_root=str(tmp_path / "AssetHub" / "CACHE" / "previews"),
        log_root=str(tmp_path / "AssetHub" / "LOGS"),
        ui={},
    )

    ctx = AppContext(config=cfg)
    ctx.initialize_core_services()

    snap = collect_settings_snapshot(ctx)

    assert snap.about["app_version"] != ""
    # schema_version may be "" during early init, or the latest schema version after init.
    assert snap.about["schema_version"] in {"", "4"}

    # Sanity: ui behavior keys present
    assert isinstance(snap.ui_behavior["library_row_cap"], int)
    assert len(snap.ui_behavior["supported_preview_formats"]) > 0

    ctx.shutdown()
