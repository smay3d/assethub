# src/assethub/core/model/asset.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Asset:
    id: int
    storage_id: int
    type: str
    key: str
    name: str
    slug: Optional[str]
    created_at: str  # ISO8601, refine later
    updated_at: str  # ISO8601, refine later
