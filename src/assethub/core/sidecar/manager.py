# src/assethub/core/sidecar/manager.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class SidecarManager:
    """
    Handle reading and writing of sidecar JSON files in SIDECARS/<asset-id>/.
    """

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    # TODO: add methods for load_asset_json, save_asset_json, etc.
