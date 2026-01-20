"""DB helpers for Version rows.

Stage 8 introduces artist-friendly versioning:
- Internal monotonic ordering via `sort_key`.
- User-facing label (default scheme vNN => v01, v02, ...).

This module is Qt-free and safe to import in tests.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional, Tuple

from assethub.core.model.asset import Asset
from assethub.core.model.version import Version


def _label_for_scheme(sort_key: int, scheme: str) -> str:
    """Generate a label given a scheme.

    v0 supports only the default scheme 'vNN'.
    """
    sk = int(sort_key)
    s = str(scheme).strip() or "vNN"
    if s != "vNN":
        # Future-safe fallback: treat unknown schemes like vNN.
        s = "vNN"
    # Minimum 2-digit padding; grows naturally past 99.
    return f"v{sk:02d}"


def create_version(
    conn: sqlite3.Connection,
    *,
    asset_id: int,
    label: Optional[str] = None,
    scheme: str = "vNN",
) -> Version:
    """Create a new version for an asset.

    Chooses the next sort_key as (max+1) for the given asset.
    """

    aid = int(asset_id)
    if aid <= 0:
        raise ValueError("asset_id must be a positive integer")

    row = conn.execute(
        "SELECT COALESCE(MAX(sort_key), 0) FROM version WHERE asset_id=?;",
        (aid,),
    ).fetchone()
    next_sort = int(row[0] if row and row[0] is not None else 0) + 1

    lbl = str(label).strip() if label is not None else ""
    if not lbl:
        lbl = _label_for_scheme(next_sort, scheme)

    conn.execute(
        """
        INSERT INTO version(asset_id, label, sort_key, scheme)
        VALUES (?, ?, ?, ?);
        """,
        (aid, lbl, int(next_sort), str(scheme).strip() or "vNN"),
    )
    conn.commit()

    vid = conn.execute("SELECT last_insert_rowid();").fetchone()[0]
    return get_version(conn, int(vid))  # type: ignore[return-value]


def get_version(conn: sqlite3.Connection, version_id: int) -> Optional[Version]:
    """Fetch a Version by id."""
    row = conn.execute(
        """
        SELECT id, asset_id, label, sort_key, scheme, created_at, updated_at
        FROM version
        WHERE id=?
        LIMIT 1;
        """,
        (int(version_id),),
    ).fetchone()
    if row is None:
        return None
    return Version(
        id=int(row[0]),
        asset_id=int(row[1]),
        label=str(row[2]),
        sort_key=int(row[3]),
        scheme=str(row[4]),
        created_at=str(row[5]),
        updated_at=str(row[6]),
    )


def list_versions_for_asset(conn: sqlite3.Connection, asset_id: int) -> List[Version]:
    """List versions for an asset, ordered by sort_key."""
    rows = conn.execute(
        """
        SELECT id, asset_id, label, sort_key, scheme, created_at, updated_at
        FROM version
        WHERE asset_id=?
        ORDER BY sort_key;
        """,
        (int(asset_id),),
    ).fetchall()

    out: List[Version] = []
    for r in rows:
        out.append(
            Version(
                id=int(r[0]),
                asset_id=int(r[1]),
                label=str(r[2]),
                sort_key=int(r[3]),
                scheme=str(r[4]),
                created_at=str(r[5]),
                updated_at=str(r[6]),
            )
        )
    return out


def resolve_file_to_asset_version(
    conn: sqlite3.Connection, file_id: int
) -> Optional[Tuple[Asset, Version]]:
    """Resolve a file_id to (asset, version) via file.version_id.

    Returns None if the file has no assigned version.
    """

    row = conn.execute(
        """
        SELECT
            a.id, a.storage_id, a.type, a.key, a.name, a.slug, a.created_at, a.updated_at,
            v.id, v.asset_id, v.label, v.sort_key, v.scheme, v.created_at, v.updated_at
        FROM file f
        JOIN version v ON v.id = f.version_id
        JOIN asset a ON a.id = v.asset_id
        WHERE f.id=?
        LIMIT 1;
        """,
        (int(file_id),),
    ).fetchone()

    if row is None:
        return None

    asset = Asset(
        id=int(row[0]),
        storage_id=int(row[1]),
        type=str(row[2]),
        key=str(row[3]),
        name=str(row[4]),
        slug=None if row[5] is None else str(row[5]),
        created_at=str(row[6]),
        updated_at=str(row[7]),
    )
    version = Version(
        id=int(row[8]),
        asset_id=int(row[9]),
        label=str(row[10]),
        sort_key=int(row[11]),
        scheme=str(row[12]),
        created_at=str(row[13]),
        updated_at=str(row[14]),
    )
    return asset, version
