# src/assethub/core/model/version.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Version:
    id: int
    asset_id: int
    label: str
    sort_key: int
    scheme: str
    is_discarded: int
    user_label: str
    created_at: str  # ISO8601, refine later
    updated_at: str  # ISO8601, refine later
