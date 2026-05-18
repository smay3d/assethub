# src/assethub/core/db/scan_exclusions.py
"""Per-root scan extension exclusion helpers.

Extensions are stored and returned normalized: lowercase, no leading dot.
All write functions apply normalization before touching the DB.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable


def _normalize(extension: str) -> str:
    return extension.lstrip(".").lower().strip()


def get_exclusions(conn: sqlite3.Connection, storage_id: int) -> frozenset[str]:
    """Return the set of excluded extensions for a storage root.

    Returns an empty frozenset if no exclusions are configured.
    Extensions are returned normalized (lowercase, no dot).
    """
    rows = conn.execute(
        "SELECT extension FROM storage_scan_exclusion WHERE storage_id=?;",
        (int(storage_id),),
    ).fetchall()
    return frozenset(str(r[0]) for r in rows)


def add_exclusion(conn: sqlite3.Connection, storage_id: int, extension: str) -> None:
    """Add a single extension to the exclusion list for a root.

    Normalizes the extension before inserting. Duplicate insertions are ignored.
    """
    ext = _normalize(extension)
    if not ext:
        return
    conn.execute(
        "INSERT OR IGNORE INTO storage_scan_exclusion(storage_id, extension) VALUES (?, ?);",
        (int(storage_id), ext),
    )
    conn.commit()


def remove_exclusion(conn: sqlite3.Connection, storage_id: int, extension: str) -> None:
    """Remove a single extension from the exclusion list for a root.

    No-op if the extension is not present.
    """
    ext = _normalize(extension)
    conn.execute(
        "DELETE FROM storage_scan_exclusion WHERE storage_id=? AND extension=?;",
        (int(storage_id), ext),
    )
    conn.commit()


def set_exclusions(
    conn: sqlite3.Connection,
    storage_id: int,
    extensions: Iterable[str],
) -> None:
    """Replace the full exclusion set for a root.

    Deletes all existing exclusions for the root, then inserts the new set.
    Normalizes all extensions before inserting. Duplicates in input are ignored.
    """
    sid = int(storage_id)
    normalized = {_normalize(e) for e in extensions if _normalize(e)}
    conn.execute(
        "DELETE FROM storage_scan_exclusion WHERE storage_id=?;",
        (sid,),
    )
    for ext in sorted(normalized):
        conn.execute(
            "INSERT OR IGNORE INTO storage_scan_exclusion(storage_id, extension) VALUES (?, ?);",
            (sid, ext),
        )
    conn.commit()
