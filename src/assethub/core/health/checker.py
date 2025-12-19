"""Health / integrity checks.

Stage 6.4 implements a minimal "missing detection" pass.

This module intentionally stays small and conservative:
  - It does not attempt recovery/relinking.
  - It does not compute checksums.
  - It only updates `file.integrity_state` based on whether the expected
    file path exists on disk.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from assethub.core.storage.roots import StorageManager, StorageRoot


@dataclass(frozen=True)
class HealthResult:
    file_id: int
    new_state: str


class HealthChecker:
    """Perform integrity checks on indexed files.

    Stage 6.4: only "missing detection" is implemented.
    """

    STATE_OK = "OK"
    STATE_MISSING = "MISSING"
    STATE_UNRESOLVED = "UNRESOLVED"  # e.g., Unmanaged storage (no resolvable root)

    def __init__(self, conn: sqlite3.Connection, storage_manager: StorageManager) -> None:
        self._conn = conn
        self._storage = storage_manager

    def check_all_files(self) -> List[HealthResult]:
        """Check all indexed files and update their integrity_state.

        Returns a list of per-file results describing the new state.
        """
        storage_by_id: Dict[int, StorageRoot] = {s.id: s for s in self._storage.list_roots()}

        rows = self._conn.execute(
            "SELECT id, storage_id, relative_path FROM file ORDER BY id;"
        ).fetchall()

        results: List[HealthResult] = []
        updates: List[Tuple[str, int]] = []

        for file_id, storage_id, rel in rows:
            file_id_i = int(file_id)
            storage_id_i = int(storage_id)
            rel_s = str(rel)

            storage = storage_by_id.get(storage_id_i)
            if storage is None or storage.root_path is None:
                # Cannot resolve to a concrete on-disk location (e.g. Unmanaged).
                new_state = self.STATE_UNRESOLVED
            else:
                abs_path = self._build_abs_path(storage.root_path, rel_s)
                new_state = self.STATE_OK if os.path.exists(abs_path) else self.STATE_MISSING

            results.append(HealthResult(file_id=file_id_i, new_state=new_state))
            updates.append((new_state, file_id_i))

        # Apply updates in one batch.
        self._conn.executemany(
            "UPDATE file SET integrity_state = ? WHERE id = ?;",
            updates,
        )
        self._conn.commit()

        return results

    @staticmethod
    def _build_abs_path(root_path: str, relative_path: str) -> str:
        # DB stores forward slashes. Convert to OS separator for join.
        rel_os = relative_path.replace("/", os.sep)
        return os.path.normpath(os.path.join(root_path, rel_os))
