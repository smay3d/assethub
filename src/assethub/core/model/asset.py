# src/assethub/core/model/asset.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Asset:
    id: int
    name: str
    slug: str
    created_at: str  # ISO8601, refine later
