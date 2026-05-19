# src/assethub/core/model/file.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class File:
    id: int
    version_id: int
    storage_id: int
    relative_path: str
    integrity_state: str
    checksum: Optional[str] = None
