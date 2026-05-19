"""DB helpers for duplicate file detection.

Queries file records grouped by SHA-256 checksum to identify files with
identical content across storage roots.

Qt-free. All functions accept a sqlite3.Connection and return plain dataclasses.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class DuplicateFile:
    file_id: int
    storage_id: int
    storage_name: str
    relative_path: str
    size_bytes: Optional[int]
    integrity_state: str


@dataclass(frozen=True)
class DuplicateGroup:
    checksum: str
    file_count: int
    files: List[DuplicateFile]


def query_duplicate_groups(conn: sqlite3.Connection) -> List[DuplicateGroup]:
    """Return all groups of files that share a SHA-256 checksum.

    Only files with a non-NULL checksum are considered. Groups are sorted
    by file_count DESC, then by size_bytes DESC (most overlap first).

    Args:
        conn: SQLite connection with an initialized v9+ schema.

    Returns:
        List of DuplicateGroup, one per unique duplicated checksum.
        Empty list when no duplicates exist.
    """
    rows = conn.execute(
        """
        SELECT
            f.id,
            f.storage_id,
            COALESCE(NULLIF(s.display_name, ''), s.name) AS storage_name,
            f.relative_path,
            f.size_bytes,
            f.integrity_state,
            f.checksum
        FROM file f
        JOIN storage s ON s.id = f.storage_id
        WHERE f.checksum IN (
            SELECT checksum
            FROM file
            WHERE checksum IS NOT NULL
            GROUP BY checksum
            HAVING COUNT(*) > 1
        )
        ORDER BY f.checksum, f.storage_id, f.relative_path;
        """
    ).fetchall()

    # Assemble groups from the ordered flat result.
    groups_by_checksum: dict[str, list[DuplicateFile]] = {}
    order: list[str] = []
    for file_id, storage_id, storage_name, rel_path, size_bytes, integrity, checksum in rows:
        dup_file = DuplicateFile(
            file_id=int(file_id),
            storage_id=int(storage_id),
            storage_name=str(storage_name),
            relative_path=str(rel_path),
            size_bytes=None if size_bytes is None else int(size_bytes),
            integrity_state=str(integrity),
        )
        cs = str(checksum)
        if cs not in groups_by_checksum:
            groups_by_checksum[cs] = []
            order.append(cs)
        groups_by_checksum[cs].append(dup_file)

    groups = [
        DuplicateGroup(
            checksum=cs,
            file_count=len(files),
            files=files,
        )
        for cs, files in ((cs, groups_by_checksum[cs]) for cs in order)
    ]

    # Sort: most copies first, then largest size first.
    groups.sort(
        key=lambda g: (
            -g.file_count,
            -(g.files[0].size_bytes or 0),
        )
    )
    return groups


def get_duplicate_file_ids(conn: sqlite3.Connection) -> frozenset[int]:
    """Return the set of file IDs that share a checksum with at least one other file.

    Used by FileTableModel to decorate the Tags column. O(1) membership testing.

    Args:
        conn: SQLite connection with an initialized v9+ schema.

    Returns:
        frozenset of file IDs that are part of a duplicate group.
    """
    rows = conn.execute(
        """
        SELECT id
        FROM file
        WHERE checksum IS NOT NULL
          AND checksum IN (
              SELECT checksum
              FROM file
              WHERE checksum IS NOT NULL
              GROUP BY checksum
              HAVING COUNT(*) > 1
          );
        """
    ).fetchall()
    return frozenset(int(r[0]) for r in rows)


def count_checksummed_files(conn: sqlite3.Connection) -> Tuple[int, int]:
    """Return (checksummed, total) file counts.

    Used by DuplicatesView to populate the status banner.

    Args:
        conn: SQLite connection with an initialized v9+ schema.

    Returns:
        Tuple of (number of files with non-NULL checksum, total file count).
    """
    row = conn.execute(
        "SELECT COUNT(CASE WHEN checksum IS NOT NULL THEN 1 END), COUNT(*) FROM file;"
    ).fetchone()
    if row is None:
        return (0, 0)
    return (int(row[0]), int(row[1]))
