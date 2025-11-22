# src/assethub/core/storage/roots.py

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class StorageRoot:
    id: int
    name: str
    path: str
    status: str  # e.g. "OK", "UNMOUNTED", "READ_ONLY", "UNMANAGED"


class StorageManager:
    """
    Manage storage roots and resolve absolute paths to logical storage entries.
    """

    def __init__(self) -> None:
        self.roots: List[StorageRoot] = []

    # TODO: add methods for register_root, find_root_for_path, etc.
