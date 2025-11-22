# src/assethub/config/defaults.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from assethub.context import AppConfig


def get_default_paths() -> Dict[str, str]:
    """
    Return default directory paths for AssetHub.

    For now, we use a folder named 'AssetHub' in the user's home directory.
    You can later add a settings UI to change this.
    """
    base = Path.home() / "AssetHub"

    return {
        "data_root": str(base),
        "db_path": str(base / "DB" / "assethub.sqlite3"),
        "sidecar_root": str(base / "SIDECARS"),
        "preview_root": str(base / "CACHE" / "previews"),
        "log_root": str(base / "LOGS"),
    }


def build_default_config() -> AppConfig:
    """
    Build an AppConfig instance using default paths and basic UI settings.
    """
    paths = get_default_paths()

    return AppConfig(
        data_root=paths["data_root"],
        db_path=paths["db_path"],
        sidecar_root=paths["sidecar_root"],
        preview_root=paths["preview_root"],
        log_root=paths["log_root"],
        ui={
            "theme": "dark",
            "language": "en",
        },
    )
