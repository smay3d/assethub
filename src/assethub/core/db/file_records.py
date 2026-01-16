"""DB helpers for file records.

Stage 7.5.3 introduces selection-based actions (delete missing, copy paths, etc.).
This module provides small, testable helpers that do NOT depend on Qt.

These helpers are intentionally conservative:
- They do not assume Qt is available.
- They validate inputs where it prevents destructive mistakes.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class FileRecordInfo:
    file_id: int
    storage_id: int
    storage_name: str
    storage_root_path: Optional[str]
    relative_path: str
    integrity_state: str
    size_bytes: Optional[int]


def _placeholders(n: int) -> str:
    return ",".join(["?"] * n)


def fetch_file_records(conn: sqlite3.Connection, file_ids: Iterable[int]) -> List[FileRecordInfo]:
    """Fetch file records with joined storage info.

    Returns records ordered by file.id.
    """
    ids = [int(x) for x in file_ids]
    if not ids:
        return []

    ph = _placeholders(len(ids))
    rows = conn.execute(
        f"""
        SELECT
            file.id,
            file.storage_id,
            COALESCE(NULLIF(storage.display_name, ''), storage.name) AS storage_label,
            storage.root_path,
            file.relative_path,
            file.integrity_state,
            file.size_bytes
        FROM file
        JOIN storage ON storage.id = file.storage_id
        WHERE file.id IN ({ph})
        ORDER BY file.id;
        """,
        tuple(ids),
    ).fetchall()

    out: List[FileRecordInfo] = []
    for file_id, storage_id, storage_name, root_path, rel, integrity_state, size_bytes in rows:
        out.append(
            FileRecordInfo(
                file_id=int(file_id),
                storage_id=int(storage_id),
                storage_name=str(storage_name),
                storage_root_path=None if root_path is None else str(root_path),
                relative_path=str(rel),
                integrity_state=str(integrity_state),
                size_bytes=None if size_bytes is None else int(size_bytes),
            )
        )
    return out


def fetch_missing_file_ids(conn: sqlite3.Connection) -> List[int]:
    rows = conn.execute("SELECT id FROM file WHERE UPPER(integrity_state)='MISSING' ORDER BY id;").fetchall()
    return [int(r[0]) for r in rows]


def delete_file_records(conn: sqlite3.Connection, file_ids: Iterable[int]) -> int:
    ids = [int(x) for x in file_ids]
    if not ids:
        return 0

    before = conn.total_changes
    ph = _placeholders(len(ids))
    conn.execute(f"DELETE FROM file WHERE id IN ({ph});", tuple(ids))
    conn.commit()
    return int(conn.total_changes - before)


def delete_missing_file_records(conn: sqlite3.Connection, file_ids: Iterable[int]) -> int:
    """Delete file records only if ALL specified ids are currently MISSING.

    Raises:
        ValueError: if any selected record is not MISSING.
    """
    ids = [int(x) for x in file_ids]
    if not ids:
        return 0

    ph = _placeholders(len(ids))
    rows = conn.execute(
        f"SELECT id, integrity_state FROM file WHERE id IN ({ph});",
        tuple(ids),
    ).fetchall()

    state_by_id = {int(r[0]): str(r[1]).upper() for r in rows}
    # If any are missing from DB, treat as invalid (caller likely has stale selection)
    for fid in ids:
        if fid not in state_by_id:
            raise ValueError(f"File id not found: {fid}")
        if state_by_id[fid] != "MISSING":
            raise ValueError("All selected files must be MISSING to remove from database")

    return delete_file_records(conn, ids)


def purge_all_missing_file_records(conn: sqlite3.Connection) -> int:
    """Delete all file rows currently marked MISSING."""
    before = conn.total_changes
    conn.execute("DELETE FROM file WHERE UPPER(integrity_state)='MISSING';")
    conn.commit()
    return int(conn.total_changes - before)
