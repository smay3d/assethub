# src/assethub/core/utils/paths.py

from __future__ import annotations

from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    """Create the directory if missing and return it."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
