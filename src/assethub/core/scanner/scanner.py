# src/assethub/core/scanner/scanner.py

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Callable, List, Optional

from assethub.core.db.scan_exclusions import get_exclusions
from assethub.core.storage.roots import StorageManager, StorageRoot
from assethub.core.utils.app_log import AppLog
from assethub.core.utils.checksum import sha256_file


@dataclass(frozen=True)
class ScanResult:
    discovered_paths: List[str]
    files_indexed: int
    files_checksummed: int = 0
    files_without_checksum: int = 0
    canceled: bool = False


class Scanner:
    """Walk storage roots, discover files, and update the database index.

    Stage 6.3: Scanner v1 performs **files-only indexing**.
    - It only indexes physical files into the `file` table.
    - It does *not* create assets, versions, or tags.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        storage_manager: StorageManager,
        *,
        log: Optional[AppLog] = None,
    ) -> None:
        self._conn = conn
        self._storage = storage_manager
        self._log = log

    def scan_all(self, *, cancel_check: Optional[Callable[[], bool]] = None) -> ScanResult:
        """Scan all registered storage roots and index files.

        Returns:
            ScanResult with discovered absolute paths and count of indexed files.
        """
        roots = self._scan_roots()
        discovered: List[str] = []
        indexed = 0
        files_checksummed = 0

        # Load exclusion sets for all roots before walking.
        exclusions: dict[int, frozenset[str]] = {
            root.id: get_exclusions(self._conn, root.id)
            for root in roots
        }

        def _should_cancel() -> bool:
            if cancel_check is None:
                return False
            try:
                return bool(cancel_check())
            except Exception:
                # Never allow cancel callback failures to crash a scan.
                return False

        for root in roots:
            if root.root_path is None:
                continue

            if _should_cancel():
                self._conn.commit()
                return ScanResult(
                    discovered_paths=discovered,
                    files_indexed=indexed,
                    files_checksummed=files_checksummed,
                    files_without_checksum=self._count_without_checksum(),
                    canceled=True,
                )

            for dirpath, _dirnames, filenames in os.walk(root.root_path):
                if _should_cancel():
                    self._conn.commit()
                    return ScanResult(
                        discovered_paths=discovered,
                        files_indexed=indexed,
                        files_checksummed=files_checksummed,
                        files_without_checksum=self._count_without_checksum(),
                        canceled=True,
                    )
                for fname in filenames:
                    if _should_cancel():
                        self._conn.commit()
                        return ScanResult(
                            discovered_paths=discovered,
                            files_indexed=indexed,
                            files_checksummed=files_checksummed,
                            files_without_checksum=self._count_without_checksum(),
                            canceled=True,
                        )
                    # Skip files whose extension is excluded for this root.
                    ext = os.path.splitext(fname)[1].lstrip(".").lower()
                    if ext and ext in exclusions.get(root.id, frozenset()):
                        continue

                    abs_path = os.path.join(dirpath, fname)

                    # Best-effort: skip if file vanished mid-walk.
                    try:
                        st = os.stat(abs_path)
                    except FileNotFoundError:
                        continue

                    rel = os.path.relpath(abs_path, root.root_path)
                    rel = rel.replace("\\", "/")

                    disk_size = int(st.st_size)
                    disk_mtime = float(st.st_mtime)

                    # Decide whether to (re)compute the checksum.
                    old_row = self._conn.execute(
                        "SELECT size_bytes, mtime_unix, checksum "
                        "FROM file WHERE storage_id=? AND relative_path=?",
                        (root.id, rel),
                    ).fetchone()

                    need_checksum = (
                        old_row is None
                        or old_row[0] != disk_size
                        or old_row[1] != disk_mtime
                        or old_row[2] is None  # NULL -> never checksummed
                    )

                    new_checksum: Optional[str] = None
                    if need_checksum:
                        try:
                            new_checksum = sha256_file(abs_path)
                            files_checksummed += 1
                        except OSError:
                            if self._log is not None:
                                self._log.warn(
                                    f"Checksum skipped (unreadable): {abs_path}"
                                )
                            need_checksum = False

                    self._upsert_file(
                        storage_id=root.id,
                        relative_path=rel,
                        size_bytes=disk_size,
                        mtime_unix=disk_mtime,
                        checksum=new_checksum,
                        update_checksum=need_checksum,
                    )
                    discovered.append(abs_path)
                    indexed += 1

        self._conn.commit()
        return ScanResult(
            discovered_paths=discovered,
            files_indexed=indexed,
            files_checksummed=files_checksummed,
            files_without_checksum=self._count_without_checksum(),
            canceled=False,
        )

    # ---------------------------
    # Internals
    # ---------------------------

    def _scan_roots(self) -> List[StorageRoot]:
        """Roots eligible for scanning.

        Excludes Unmanaged (root_path is NULL). Skips roots marked non-OK.
        """
        roots = [r for r in self._storage.list_roots() if r.root_path is not None]
        roots = [r for r in roots if str(r.status).upper() == "OK"]
        return roots

    def _count_without_checksum(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM file WHERE checksum IS NULL;").fetchone()
        return int(row[0]) if row else 0

    def _upsert_file(
        self,
        *,
        storage_id: int,
        relative_path: str,
        size_bytes: int,
        mtime_unix: float,
        checksum: Optional[str],
        update_checksum: bool,
    ) -> None:
        """Upsert a file record.

        When ``update_checksum`` is True the provided ``checksum`` value
        (which may be None if hashing failed) is written to the DB.
        When False the existing checksum column value is left untouched.
        """
        if update_checksum:
            self._conn.execute(
                """
                INSERT INTO file(
                    version_id, storage_id, relative_path,
                    integrity_state, size_bytes, mtime_unix, checksum
                ) VALUES (NULL, ?, ?, 'OK', ?, ?, ?)
                ON CONFLICT(storage_id, relative_path) DO UPDATE SET
                    integrity_state = 'OK',
                    size_bytes      = excluded.size_bytes,
                    mtime_unix      = excluded.mtime_unix,
                    checksum        = excluded.checksum;
                """,
                (storage_id, relative_path, size_bytes, mtime_unix, checksum),
            )
        else:
            self._conn.execute(
                """
                INSERT INTO file(
                    version_id, storage_id, relative_path,
                    integrity_state, size_bytes, mtime_unix
                ) VALUES (NULL, ?, ?, 'OK', ?, ?)
                ON CONFLICT(storage_id, relative_path) DO UPDATE SET
                    integrity_state = 'OK',
                    size_bytes      = excluded.size_bytes,
                    mtime_unix      = excluded.mtime_unix;
                """,
                (storage_id, relative_path, size_bytes, mtime_unix),
            )
