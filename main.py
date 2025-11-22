"""
AssetHub entry point script.

This is a thin wrapper that prepares sys.path and delegates to assethub.app.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _prepare_sys_path() -> None:
    """Ensure the src/ directory is on sys.path for local development."""
    root = Path(__file__).resolve().parent
    src_dir = root / "src"
    src_str = str(src_dir)

    if src_dir.is_dir() and src_str not in sys.path:
        sys.path.insert(0, src_str)


def main() -> None:
    _prepare_sys_path()

    # Import here so assethub is resolved after sys.path adjustment
    from assethub.app import run_app

    run_app()


if __name__ == '__main__':
    main()