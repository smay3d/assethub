# src/assethub/core/model/version.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Version:
    id: int
    asset_id: int
    semver: str
