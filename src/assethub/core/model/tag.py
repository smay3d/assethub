# src/assethub/core/model/tag.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Tag:
    id: int
    name: str
