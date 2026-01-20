"""DB helpers for Asset rows.

Stage 8.x introduces asset-aware behavior. This module provides small, testable
helpers that do NOT depend on Qt.

Conventions:
- Assets are storage-scoped and uniquely identified by (storage_id, type, key).
- These helpers keep logic conservative (validate basic inputs, no UI concerns).
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from assethub.core.model.asset import Asset


def create_asset(
    conn: sqlite3.Connection,
    *,
    storage_id: int,
    type: str,
    key: str,
    name: str,
    slug: Optional[str] = None,
    commit: bool = True,
) -> Asset:
    """Create-or-fetch an asset by its storage-scoped identity.

    Args:
        conn: SQLite connection.
        storage_id: Owning storage root id.
        type: Asset type (e.g. generic, image_sequence, texture_set).
        key: Stable grouping key (rule-derived).
        name: User-facing display name.
        slug: Optional slug (not relied on for identity in v0).

    Returns:
        The created or existing Asset.

    Raises:
        ValueError: if required inputs are empty.
    """

    sid = int(storage_id)
    t = str(type).strip()
    k = str(key).strip()
    n = str(name).strip()
    if sid <= 0:
        raise ValueError("storage_id must be a positive integer")
    if not t:
        raise ValueError("type must be non-empty")
    if not k:
        raise ValueError("key must be non-empty")
    if not n:
        raise ValueError("name must be non-empty")

    # Create-or-ignore by the v3 uniqueness boundary.
    conn.execute(
        """
        INSERT OR IGNORE INTO asset(storage_id, type, key, name, slug)
        VALUES (?, ?, ?, ?, ?);
        """,
        (sid, t, k, n, slug),
    )
    if commit:
        conn.commit()

    row = conn.execute(
        """
        SELECT id, storage_id, type, key, name, slug, created_at, updated_at
        FROM asset
        WHERE storage_id=? AND type=? AND key=?
        ORDER BY id
        LIMIT 1;
        """,
        (sid, t, k),
    ).fetchone()

    if row is None:
        raise RuntimeError("create_asset failed to create or locate asset")

    return Asset(
        id=int(row[0]),
        storage_id=int(row[1]),
        type=str(row[2]),
        key=str(row[3]),
        name=str(row[4]),
        slug=None if row[5] is None else str(row[5]),
        created_at=str(row[6]),
        updated_at=str(row[7]),
    )


def get_asset(conn: sqlite3.Connection, asset_id: int) -> Optional[Asset]:
    """Fetch an Asset by id."""
    row = conn.execute(
        """
        SELECT id, storage_id, type, key, name, slug, created_at, updated_at
        FROM asset
        WHERE id=?
        LIMIT 1;
        """,
        (int(asset_id),),
    ).fetchone()
    if row is None:
        return None
    return Asset(
        id=int(row[0]),
        storage_id=int(row[1]),
        type=str(row[2]),
        key=str(row[3]),
        name=str(row[4]),
        slug=None if row[5] is None else str(row[5]),
        created_at=str(row[6]),
        updated_at=str(row[7]),
    )


def list_assets_for_storage(conn: sqlite3.Connection, storage_id: int) -> List[Asset]:
    """List assets for a storage root, ordered by id."""
    rows = conn.execute(
        """
        SELECT id, storage_id, type, key, name, slug, created_at, updated_at
        FROM asset
        WHERE storage_id=?
        ORDER BY id;
        """,
        (int(storage_id),),
    ).fetchall()

    out: List[Asset] = []
    for r in rows:
        out.append(
            Asset(
                id=int(r[0]),
                storage_id=int(r[1]),
                type=str(r[2]),
                key=str(r[3]),
                name=str(r[4]),
                slug=None if r[5] is None else str(r[5]),
                created_at=str(r[6]),
                updated_at=str(r[7]),
            )
        )
    return out
