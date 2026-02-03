"""DB helpers for manual file->asset bindings.

Stage 9.3 introduces *authoritative user intent* in the form of a durable binding:

  file_binding(file_id PRIMARY KEY, asset_id)

Semantics:
  - A file may be bound to at most one asset at a time.
  - Binding is asset-level (not version-level).
  - Binding does not retroactively mutate historical version snapshots.
  - When new versions are created (fork/version-up/etc), bound files are
    automatically included in the new version's membership.

This module is Qt-free and safe to import in tests.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class FileBinding:
    file_id: int
    asset_id: int
    created_at: str


def get_file_binding(conn: sqlite3.Connection, *, file_id: int) -> Optional[FileBinding]:
    """Return the binding for a file_id, if present."""
    row = conn.execute(
        "SELECT file_id, asset_id, created_at FROM file_binding WHERE file_id=? LIMIT 1;",
        (int(file_id),),
    ).fetchone()
    if row is None:
        return None
    return FileBinding(file_id=int(row[0]), asset_id=int(row[1]), created_at=str(row[2]))


def get_bound_asset_id(conn: sqlite3.Connection, *, file_id: int) -> Optional[int]:
    """Return asset_id a file is bound to, else None."""
    row = conn.execute(
        "SELECT asset_id FROM file_binding WHERE file_id=? LIMIT 1;",
        (int(file_id),),
    ).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def list_bound_file_ids_for_asset(conn: sqlite3.Connection, *, asset_id: int) -> List[int]:
    """List file_ids bound to an asset."""
    rows = conn.execute(
        "SELECT file_id FROM file_binding WHERE asset_id=? ORDER BY file_id ASC;",
        (int(asset_id),),
    ).fetchall()
    return [int(r[0]) for r in rows]


def get_bindings_for_files(conn: sqlite3.Connection, *, file_ids: Sequence[int]) -> Dict[int, int]:
    """Return mapping file_id -> asset_id for any bound files in file_ids."""
    ids = [int(x) for x in file_ids if int(x) > 0]
    if not ids:
        return {}
    ph = ",".join(["?"] * len(ids))
    rows = conn.execute(
        f"SELECT file_id, asset_id FROM file_binding WHERE file_id IN ({ph});",
        tuple(ids),
    ).fetchall()
    return {int(r[0]): int(r[1]) for r in rows}


def bind_files_to_asset(
    conn: sqlite3.Connection,
    *,
    asset_id: int,
    file_ids: Sequence[int],
    allow_rebind: bool = False,
    commit: bool = True,
) -> int:
    """Bind file_ids to an asset.

    Args:
        asset_id: Target asset id.
        file_ids: File row ids.
        allow_rebind: If False (default), raises if any file is already bound
            to a *different* asset. If True, will rebind (overwrite) those rows.
        commit: Commit when finished.

    Returns:
        Number of files bound (attempted inserts/updates).
    """
    aid = int(asset_id)
    if aid <= 0:
        raise ValueError("asset_id must be positive")
    ids = sorted({int(x) for x in file_ids if int(x) > 0})
    if not ids:
        return 0

    # Validate asset exists.
    row = conn.execute("SELECT 1 FROM asset WHERE id=? LIMIT 1;", (aid,)).fetchone()
    if row is None:
        raise ValueError("asset_id not found")

    # Validate file rows exist.
    ph = ",".join(["?"] * len(ids))
    existing = {
        int(r[0])
        for r in conn.execute(
            f"SELECT id FROM file WHERE id IN ({ph});",
            tuple(ids),
        ).fetchall()
    }
    missing = [i for i in ids if i not in existing]
    if missing:
        raise ValueError("file_ids contain missing file rows")

    # Enforce/rebind rule.
    bound_map = get_bindings_for_files(conn, file_ids=ids)
    conflicts = [fid for fid, other_aid in bound_map.items() if int(other_aid) != aid]
    if conflicts and not allow_rebind:
        raise ValueError("One or more file_ids are already bound to a different asset")

    def _do() -> None:
        if allow_rebind:
            conn.executemany(
                "INSERT INTO file_binding(file_id, asset_id) VALUES (?, ?) "
                "ON CONFLICT(file_id) DO UPDATE SET asset_id=excluded.asset_id;",
                [(int(fid), aid) for fid in ids],
            )
        else:
            conn.executemany(
                "INSERT OR REPLACE INTO file_binding(file_id, asset_id) VALUES (?, ?);",
                [(int(fid), aid) for fid in ids],
            )

    if commit:
        with conn:
            _do()
    else:
        _do()
    return int(len(ids))


def unbind_files(
    conn: sqlite3.Connection,
    *,
    file_ids: Sequence[int],
    commit: bool = True,
) -> int:
    """Remove bindings for file_ids. Returns number of affected rows."""
    ids = sorted({int(x) for x in file_ids if int(x) > 0})
    if not ids:
        return 0
    ph = ",".join(["?"] * len(ids))

    def _do() -> int:
        cur = conn.execute(f"DELETE FROM file_binding WHERE file_id IN ({ph});", tuple(ids))
        return int(cur.rowcount or 0)

    if commit:
        with conn:
            return _do()
    return _do()


def ensure_bound_files_in_version(
    conn: sqlite3.Connection,
    *,
    asset_id: int,
    version_id: int,
) -> int:
    """Ensure bound files for an asset are members of version_id.

    Returns number of membership rows attempted (not necessarily newly inserted).
    """
    aid = int(asset_id)
    vid = int(version_id)
    if aid <= 0 or vid <= 0:
        return 0

    bound = list_bound_file_ids_for_asset(conn, asset_id=aid)
    if not bound:
        return 0

    conn.executemany(
        "INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (?, ?);",
        [(vid, int(fid)) for fid in bound],
    )
    return int(len(bound))
