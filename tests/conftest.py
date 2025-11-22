# tests/conftest.py
"""
Pytest configuration for AssetHub.

Ensures that the src/ directory is on sys.path so tests can import
the assethub package without installing it.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]  # .../AssetHub
    src_dir = root / "src"
    src_str = str(src_dir)

    if src_dir.is_dir() and src_str not in sys.path:
        sys.path.insert(0, src_str)


_ensure_src_on_path()
