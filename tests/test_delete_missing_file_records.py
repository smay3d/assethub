from __future__ import annotations

from pathlib import Path

import pytest


def test_delete_missing_file_records_requires_missing(tmp_path: Path) -> None:
    """Stage 7.5.3: DB delete helper should only delete when all are MISSING."""

    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.storage.roots import StorageManager
    from assethub.core.scanner.scanner import Scanner
    from assethub.core.health.checker import HealthChecker
    from assethub.core.db.file_records import delete_missing_file_records

    db_path = tmp_path / "assethub_test.db"
    root = tmp_path / "root"
    root.mkdir()

    ok_path = root / "ok.txt"
    missing_path = root / "missing.txt"
    ok_path.write_text("ok", encoding="utf-8")
    missing_path.write_text("missing", encoding="utf-8")

    conn = get_connection(str(db_path))
    try:
        initialize_schema(conn)

        storage = StorageManager(conn)
        storage.ensure_unmanaged_storage()
        storage.register_root(str(root), name="TestRoot")

        scanner = Scanner(conn, storage)
        scanner.scan_all()

        # Make one file missing
        missing_path.unlink()
        health = HealthChecker(conn, storage)
        health.check_all_files()

        rows = conn.execute("SELECT id, relative_path, integrity_state FROM file ORDER BY id;").fetchall()
        id_by_rel = {str(r[1]).replace('\\', '/'): int(r[0]) for r in rows}
        ok_id = id_by_rel["ok.txt"]
        missing_id = id_by_rel["missing.txt"]

        # Mixed selection should be rejected.
        with pytest.raises(ValueError):
            delete_missing_file_records(conn, [ok_id, missing_id])

        # Missing-only should delete
        deleted = delete_missing_file_records(conn, [missing_id])
        assert deleted == 1
        remaining = conn.execute("SELECT COUNT(*) FROM file;").fetchone()[0]
        assert int(remaining) == 1
    finally:
        conn.close()
