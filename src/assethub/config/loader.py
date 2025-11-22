# src/assethub/config/loader.py

from __future__ import annotations

from .defaults import build_default_config
from assethub.context import AppConfig


def load_app_config() -> AppConfig:
    """
    Load the application configuration.

    Skeleton implementation: returns defaults only.
    Later we will:
      - look for a user config file
      - merge overrides into the default config
    """
    return build_default_config()
