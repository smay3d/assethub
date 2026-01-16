# src/assethub/core/storage/roots.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import os
import sqlite3


@dataclass(frozen=True)
class StorageRoot:
    id: int
    name: str
    display_name: Optional[str]
    root_path: Optional[str]
    status: str  # e.g. "OK", "UNMOUNTED", "READ_ONLY", "UNMANAGED"

    @property
    def display_label(self) -> str:
        """Primary UI label for this root.

        Rule: if display_name is non-empty -> use it, else fall back to name.
        """
        dn = (self.display_name or "").strip()
        return dn if dn else self.name


class StorageManager:
    """Persist and resolve storage roots.

    Stage 6.2 responsibilities:
      - Register storage roots in the DB
      - Guarantee a single "Unmanaged" storage row exists
      - Resolve absolute paths -> (storage_id, relative_path)
    """

    UNMANAGED_NAME = "Unmanaged"
    UNMANAGED_STATUS = "UNMANAGED"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ---------------------------
    # Public API
    # ---------------------------

    def ensure_unmanaged_storage(self) -> StorageRoot:
        """Ensure there is exactly one Unmanaged storage entry.

        Note: SQLite UNIQUE(root_path) does not prevent multiple NULLs, so we enforce
        the singleton invariant in code.
        """
        rows = self._conn.execute(
            "SELECT id, name, display_name, root_path, status FROM storage WHERE root_path IS NULL ORDER BY id;"
        ).fetchall()

        if not rows:
            cur = self._conn.execute(
                "INSERT INTO storage(name, root_path, status) VALUES (?, NULL, ?);",
                (self.UNMANAGED_NAME, self.UNMANAGED_STATUS),
            )
            self._conn.commit()
            return StorageRoot(
                id=int(cur.lastrowid),
                name=self.UNMANAGED_NAME,
                display_name=None,
                root_path=None,
                status=self.UNMANAGED_STATUS,
            )

        # Keep the first, delete any extras (enforce singleton)
        keep = rows[0]
        extras = rows[1:]
        if extras:
            extra_ids = [int(r[0]) for r in extras]
            self._conn.executemany("DELETE FROM storage WHERE id = ?;", [(i,) for i in extra_ids])
            self._conn.commit()

        # Normalize the kept row to expected name/status if needed
        keep_id, keep_name, keep_display, keep_root, keep_status = (
            int(keep[0]),
            str(keep[1]),
            (None if keep[2] is None else str(keep[2])),
            keep[3],
            str(keep[4]),
        )
        if keep_name != self.UNMANAGED_NAME or keep_status != self.UNMANAGED_STATUS:
            self._conn.execute(
                "UPDATE storage SET name = ?, status = ? WHERE id = ?;",
                (self.UNMANAGED_NAME, self.UNMANAGED_STATUS, keep_id),
            )
            self._conn.commit()
            keep_name, keep_status = self.UNMANAGED_NAME, self.UNMANAGED_STATUS

        return StorageRoot(id=keep_id, name=keep_name, display_name=keep_display, root_path=None, status=keep_status)

    def register_root(self, path: str, name: Optional[str] = None, status: str = "OK") -> StorageRoot:
        """Register a storage root path in the DB (idempotent)."""
        root_path = self._norm_abs(path)
        if name is None:
            name = Path(root_path).name or root_path

        # Insert if missing (root_path is UNIQUE)
        self._conn.execute(
            "INSERT OR IGNORE INTO storage(name, root_path, status) VALUES (?, ?, ?);",
            (name, root_path, status),
        )
        self._conn.commit()

        # Update name/status in case the row already existed and caller wants to adjust
        self._conn.execute(
            "UPDATE storage SET name = ?, status = ? WHERE root_path = ?;",
            (name, status, root_path),
        )
        self._conn.commit()

        row = self._conn.execute(
            "SELECT id, name, display_name, root_path, status FROM storage WHERE root_path = ?;",
            (root_path,),
        ).fetchone()
        assert row is not None
        return StorageRoot(
            id=int(row[0]),
            name=str(row[1]),
            display_name=None if row[2] is None else str(row[2]),
            root_path=str(row[3]),
            status=str(row[4]),
        )

    def list_roots(self) -> List[StorageRoot]:
        """List all storage rows (including Unmanaged)."""
        rows = self._conn.execute(
            "SELECT id, name, display_name, root_path, status FROM storage ORDER BY id;"
        ).fetchall()
        return [
            StorageRoot(
                id=int(r[0]),
                name=str(r[1]),
                display_name=None if r[2] is None else str(r[2]),
                root_path=(str(r[3]) if r[3] is not None else None),
                status=str(r[4]),
            )
            for r in rows
        ]

    def set_display_name(self, storage_id: int, display_name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """Set the user-facing display name for a storage root.

        Returns:
            (old_value, new_value) as stored in DB (None means cleared).

        Notes:
            - Disallows the Unmanaged singleton.
            - Does not rename anything on disk.
        """
        sid = int(storage_id)

        row = self._conn.execute(
            "SELECT display_name, root_path, status FROM storage WHERE id = ?;",
            (sid,),
        ).fetchone()
        if row is None:
            return None, None

        old, root_path, status = row[0], row[1], str(row[2])
        if root_path is None or status.upper() == self.UNMANAGED_STATUS:
            raise ValueError("Cannot rename Unmanaged storage")

        new_clean = (display_name or "").strip()
        new_db = None if not new_clean else new_clean

        self._conn.execute(
            "UPDATE storage SET display_name = ? WHERE id = ?;",
            (new_db, sid),
        )
        self._conn.commit()
        return (None if old is None else str(old)), new_db

    def count_files_for_storage(self, storage_id: int) -> int:
        """Return number of tracked files referencing a given storage_id."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM file WHERE storage_id = ?;",
            (int(storage_id),),
        ).fetchone()
        assert row is not None
        return int(row[0])

    def unregister_root(self, storage_id: int) -> None:
        """Unregister a storage root by id.

        Notes:
          - This blocks deletion of the Unmanaged singleton.
          - Callers should ensure there are no tracked files referencing the root.
        """
        sid = int(storage_id)
        row = self._conn.execute(
            "SELECT id, root_path, status FROM storage WHERE id = ?;",
            (sid,),
        ).fetchone()
        if row is None:
            return

        _id, root_path, status = int(row[0]), row[1], str(row[2])
        if root_path is None or status.upper() == self.UNMANAGED_STATUS:
            raise ValueError("Cannot unregister Unmanaged storage")

        self._conn.execute("DELETE FROM storage WHERE id = ?;", (sid,))
        self._conn.commit()

    def remove_root_from_tracking(self, storage_id: int) -> int:
        """Remove a storage root *and* all associated tracked file rows.

        This is a DB-only operation. It does not delete anything from disk.

        Rules:
          - Deletes all `file` rows for the given storage_id, then deletes the
            `storage` row, inside a single transaction.
          - Disallows the Unmanaged singleton.

        Returns:
            The number of file rows removed.
        """
        sid = int(storage_id)

        row = self._conn.execute(
            "SELECT id, root_path, status FROM storage WHERE id = ?;",
            (sid,),
        ).fetchone()
        if row is None:
            return 0

        _id, root_path, status = int(row[0]), row[1], str(row[2])
        if root_path is None or status.upper() == self.UNMANAGED_STATUS:
            raise ValueError("Cannot remove the Unmanaged storage root")

        # Count before deletion (for confirmations and logging).
        files_removed = self.count_files_for_storage(sid)

        # Transactional cascade: files first (FK RESTRICT), then storage.
        with self._conn:
            self._conn.execute("DELETE FROM file WHERE storage_id = ?;", (sid,))
            self._conn.execute("DELETE FROM storage WHERE id = ?;", (sid,))

        return int(files_removed)

    def resolve_storage_for_path(self, abs_path: str) -> Tuple[StorageRoot, str]:
        """Resolve an absolute path to (storage_root, relative_path).

        Resolution picks the *longest matching* registered root prefix.
        If no root matches, the result is the Unmanaged storage with a relative path
        that is just the normalized absolute path.
        """
        unmanaged = self.ensure_unmanaged_storage()

        p = self._norm_abs(abs_path)

        # Candidate roots excluding unmanaged (root_path is NULL)
        rows = self._conn.execute(
            "SELECT id, name, display_name, root_path, status FROM storage WHERE root_path IS NOT NULL;"
        ).fetchall()

        best: Optional[StorageRoot] = None
        best_root_path: Optional[str] = None

        for r in rows:
            root_path = str(r[3])
            if self._is_under_root(p, root_path):
                if best_root_path is None or len(root_path) > len(best_root_path):
                    best = StorageRoot(
                        id=int(r[0]),
                        name=str(r[1]),
                        display_name=None if r[2] is None else str(r[2]),
                        root_path=root_path,
                        status=str(r[4]),
                    )
                    best_root_path = root_path

        if best is None or best_root_path is None:
            # Outside any registered root: treat as unmanaged.
            return unmanaged, p

        rel = os.path.relpath(p, best_root_path)
        rel = rel.replace("\\", "/")  # normalize separators for DB storage
        return best, rel

    # ---------------------------
    # Internal helpers
    # ---------------------------

    @staticmethod
    def _norm_abs(path: str) -> str:
        # Absolute + normalized + case-normalized (important on Windows)
        p = os.path.abspath(path)
        p = os.path.normpath(p)
        p = os.path.normcase(p)
        # Drop trailing separator, except for drive roots like C:\
        if len(p) > 3:
            p = p.rstrip("/\\")
        return p

    @staticmethod
    def _is_under_root(abs_path: str, root_path: str) -> bool:
        ap = os.path.normcase(os.path.normpath(abs_path))
        rp = os.path.normcase(os.path.normpath(root_path))
        if ap == rp:
            return True
        # Ensure prefix match on directory boundary
        rp_with_sep = rp if rp.endswith(os.sep) else rp + os.sep
        return ap.startswith(rp_with_sep)
