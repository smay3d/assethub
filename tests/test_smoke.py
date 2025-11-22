# tests/test_smoke.py

from assethub import __version__
from assethub.config.loader import load_app_config
from assethub.context import AppContext


def test_version_exists() -> None:
    assert isinstance(__version__, str)
    assert __version__ != ""


def test_load_app_config_returns_appconfig() -> None:
    cfg = load_app_config()
    from assethub.context import AppConfig

    assert isinstance(cfg, AppConfig)
    assert cfg.data_root
    assert cfg.db_path
    assert cfg.sidecar_root


def test_app_context_initializes_managers() -> None:
    cfg = load_app_config()
    ctx = AppContext(config=cfg)
    ctx.initialize_core_services()

    assert ctx.storage_manager is not None
    assert ctx.scanner is not None
    assert ctx.preview_manager is not None
    assert ctx.sidecar_manager is not None
    assert ctx.health_checker is not None
    assert ctx.thread_pool is not None
