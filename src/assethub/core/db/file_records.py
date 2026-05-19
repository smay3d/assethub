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


@dataclass(frozen=True)
class LibraryFileRow:
    file_id: int
    version_id: Optional[int]
    storage_id: int
    storage_name: str
    relative_path: str
    integrity_state: str
    size_bytes: Optional[int]
    mtime_unix: Optional[float]
    created_at: str
    bound_asset_id: Optional[int]
    bound_asset_name: str
    owned_version_count: int


@dataclass(frozen=True)
class LibraryQueryResult:
    rows: List[LibraryFileRow]
    total_in_db: int
    truncated: bool


_LIBRARY_FILE_SELECT = """
    SELECT
        file.id,
        file.version_id,
        file.storage_id,
        COALESCE(NULLIF(storage.display_name, ''), storage.name) AS storage_label,
        file.relative_path,
        file.integrity_state,
        file.size_bytes,
        file.mtime_unix,
        file.created_at,
        fb.asset_id AS bound_asset_id,
        COALESCE(a.name, '') AS bound_asset_name,
        (
            SELECT COUNT(1)
            FROM version_file vf
            JOIN version v ON v.id = vf.version_id
            WHERE vf.file_id = file.id
              AND COALESCE(v.is_discarded, 0) = 0
        ) AS owned_version_count
    FROM file
    JOIN storage ON storage.id = file.storage_id
    LEFT JOIN file_binding fb ON fb.file_id = file.id
    LEFT JOIN asset a ON a.id = fb.asset_id
"""


def _build_library_row(raw: tuple) -> LibraryFileRow:
    (
        file_id, version_id, storage_id, storage_name,
        rel, integrity, size_b, mtime_u, created_at,
        bound_asset_id, bound_asset_name, owned_version_count,
    ) = raw
    return LibraryFileRow(
        file_id=int(file_id),
        version_id=None if version_id is None else int(version_id),
        storage_id=int(storage_id),
        storage_name=str(storage_name),
        relative_path=str(rel),
        integrity_state=str(integrity),
        size_bytes=None if size_b is None else int(size_b),
        mtime_unix=None if mtime_u is None else float(mtime_u),
        created_at=str(created_at),
        bound_asset_id=None if bound_asset_id is None else int(bound_asset_id),
        bound_asset_name=str(bound_asset_name or ""),
        owned_version_count=int(owned_version_count or 0),
    )


def query_library_files(
    conn: sqlite3.Connection,
    *,
    search_text: str = "",
    limit: int = 10_000,
) -> LibraryQueryResult:
    """Query file records for the Library tab with optional server-side search.

    Search is applied in SQL (LIKE on relative_path), so files beyond ``limit``
    are reachable when a search term is active — the LIMIT applies after filtering.

    Args:
        conn: SQLite connection with an initialized schema.
        search_text: Case-insensitive substring to match against relative_path.
            Empty string returns all files (up to limit).
        limit: Maximum number of rows to return. One extra row is fetched to
            detect truncation without a separate COUNT query on the full result.

    Returns:
        LibraryQueryResult with rows, total_in_db (unfiltered count), and
        a truncated flag indicating whether results were capped.
    """
    total_row = conn.execute("SELECT COUNT(*) FROM file;").fetchone()
    total_in_db = int(total_row[0]) if total_row else 0

    term = (search_text or "").strip()
    if term:
        pattern = f"%{term}%"
        raw_rows = conn.execute(
            _LIBRARY_FILE_SELECT
            + " WHERE file.relative_path LIKE ? COLLATE NOCASE"
            + " ORDER BY file.id LIMIT ?;",
            (pattern, limit + 1),
        ).fetchall()
    else:
        raw_rows = conn.execute(
            _LIBRARY_FILE_SELECT + " ORDER BY file.id LIMIT ?;",
            (limit + 1,),
        ).fetchall()

    truncated = len(raw_rows) > limit
    if truncated:
        raw_rows = raw_rows[:limit]

    rows = [_build_library_row(r) for r in raw_rows]
    return LibraryQueryResult(rows=rows, total_in_db=total_in_db, truncated=truncated)


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
    """Return file ids for records currently marked MISSING."""
    # Stage 9.2: Ignore missing files that belong to discarded versions.
    rows = conn.execute(
        """
        SELECT f.id
        FROM file f
        LEFT JOIN version v ON v.id=f.version_id
        WHERE UPPER(f.integrity_state)='MISSING'
          AND (v.is_discarded IS NULL OR v.is_discarded=0)
        ORDER BY f.id;
        """
    ).fetchall()
    return [int(r[0]) for r in rows]


def delete_file_records(conn: sqlite3.Connection, file_ids: Iterable[int]) -> int:
    """Delete file records by id.

    Notes:
        This is a DB-only operation. It does not delete any files on disk.

    Returns:
        Number of deleted rows.
    """
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
    """Delete all file records currently marked MISSING (DB-only).

    Returns:
        Number of deleted rows.
    """
    before = conn.total_changes
    # Stage 9.2: Do not purge missing files under discarded versions.
    conn.execute(
        """
        DELETE FROM file
        WHERE id IN (
            SELECT f.id
            FROM file f
            LEFT JOIN version v ON v.id=f.version_id
            WHERE UPPER(f.integrity_state)='MISSING'
              AND (v.is_discarded IS NULL OR v.is_discarded=0)
        );
        """
    )
    conn.commit()
    return int(conn.total_changes - before)
