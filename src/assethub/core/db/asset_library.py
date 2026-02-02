"""Read-only DB helpers for asset-level browsing.

Stage 8.5 introduces an asset-level Library mode in the UI. These helpers provide
small, testable queries to support that view.

Design goals:
- Qt-free, safe to import in tests.
- Deterministic ordering.
- Read-only (no DB mutations).
"""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import List, Optional, Dict, Any

from assethub.core.model.version import Version
from assethub.core.db.versions import list_versions_for_asset


@dataclass(frozen=True)
class AssetRow:
    asset_id: int
    storage_id: int
    name: str
    type: str
    key: str
    latest_version_id: Optional[int]
    latest_version_label: str
    version_count: int
    file_count: int
    missing_count: int


def list_assets(
    conn: sqlite3.Connection, *, storage_id: Optional[int] = None
) -> List[AssetRow]:
    """List assets (optionally filtered by storage root), with summary counts.

    Args:
        conn: SQLite connection.
        storage_id: If provided, only assets belonging to this storage root are returned.
            If None, assets across all storage roots are returned.

    Returns:
        A list of AssetRow ordered by (lower(name), asset_id).
    """
    params: List[Any] = []
    where = ""
    if storage_id is not None:
        where = "WHERE a.storage_id=?"
        params.append(int(storage_id))

    rows = conn.execute(
        f"""
        SELECT
            a.id,
            a.storage_id,
            a.name,
            a.type,
            a.key,
            (
                SELECT v.id
                FROM version v
                WHERE v.asset_id=a.id AND COALESCE(v.is_discarded, 0)=0
                ORDER BY v.sort_key DESC
                LIMIT 1
            ) AS latest_version_id,
            COALESCE((
                SELECT v.label
                FROM version v
                WHERE v.asset_id=a.id AND COALESCE(v.is_discarded, 0)=0
                ORDER BY v.sort_key DESC
                LIMIT 1
            ), '') AS latest_version_label,
            (
                SELECT COUNT(1)
                FROM version v
                WHERE v.asset_id=a.id
            ) AS version_count,
            (
                SELECT COUNT(DISTINCT vf.file_id)
                FROM version_file vf
                JOIN version v2 ON v2.id=vf.version_id
                WHERE v2.asset_id=a.id
            ) AS file_count,
            (
                SELECT COUNT(DISTINCT vf.file_id)
                FROM version_file vf
                JOIN version v2 ON v2.id=vf.version_id
                JOIN file f ON f.id=vf.file_id
                WHERE v2.asset_id=a.id
                  AND f.integrity_state='MISSING'
                  AND COALESCE(v2.is_discarded, 0)=0
            ) AS missing_count
        FROM asset a
        {where}
        ORDER BY LOWER(a.name), a.id;
        """,
        tuple(params),
    ).fetchall()

    out: List[AssetRow] = []
    for r in rows:
        latest_id = None if r[5] is None else int(r[5])
        out.append(
            AssetRow(
                asset_id=int(r[0]),
                storage_id=int(r[1]),
                name=str(r[2]),
                type=str(r[3]),
                key=str(r[4]),
                latest_version_id=latest_id,
                latest_version_label=str(r[6] or ""),
                version_count=int(r[7] or 0),
                file_count=int(r[8] or 0),
                missing_count=int(r[9] or 0),
            )
        )
    return out


def list_assets_for_storage(conn: sqlite3.Connection, storage_id: int) -> List[AssetRow]:
    """Compatibility wrapper for storage-filtered listing."""
    return list_assets(conn, storage_id=int(storage_id))


def list_versions(conn: sqlite3.Connection, *, asset_id: int) -> List[Version]:
    """List versions for a given asset, ordered by sort_key."""
    return list_versions_for_asset(conn, int(asset_id))


def list_files_for_version(conn: sqlite3.Connection, *, version_id: int) -> List[Dict[str, Any]]:
    """List files attached to a version, ordered deterministically.

    Returns dicts with keys:
      - file_id
      - storage_id
      - relative_path
      - integrity_state
      - size_bytes
      - mtime_unix
    """
    rows = conn.execute(
        """
        SELECT f.id, f.storage_id, f.relative_path, f.integrity_state, f.size_bytes, f.mtime_unix
        FROM version_file vf
        JOIN file f ON f.id=vf.file_id
        WHERE vf.version_id=?
        ORDER BY f.relative_path, f.id;
        """,
        (int(version_id),),
    ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "file_id": int(r[0]),
                "storage_id": int(r[1]),
                "relative_path": str(r[2]),
                "integrity_state": str(r[3]),
                "size_bytes": None if r[4] is None else int(r[4]),
                "mtime_unix": None if r[5] is None else float(r[5]),
            }
        )
    return out
