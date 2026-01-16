from __future__ import annotations

from pathlib import Path


def test_health_checker_targeted_check_only_selected(tmp_path: Path) -> None:
    """Stage 7.5.3: targeted health checks should work on a subset of files."""

    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.storage.roots import StorageManager
    from assethub.core.scanner.scanner import Scanner
    from assethub.core.health.checker import HealthChecker

    db_path = tmp_path / "assethub_test.db"
    root = tmp_path / "root"
    root.mkdir()

    keep_path = root / "keep.txt"
    delete_path = root / "delete.txt"
    keep_path.write_text("keep", encoding="utf-8")
    delete_path.write_text("delete", encoding="utf-8")

    conn = get_connection(str(db_path))
    try:
        initialize_schema(conn)

        storage = StorageManager(conn)
        storage.ensure_unmanaged_storage()
        storage.register_root(str(root), name="TestRoot")

        scanner = Scanner(conn, storage)
        scanner.scan_all()

        # Delete one file after scan
        delete_path.unlink()

        # Find file ids
        rows = conn.execute("SELECT id, relative_path FROM file ORDER BY id;").fetchall()
        id_by_rel = {str(r[1]).replace('\\\\', '/'): int(r[0]) for r in rows}
        keep_id = id_by_rel["keep.txt"]
        delete_id = id_by_rel["delete.txt"]

        health = HealthChecker(conn, storage)
        # Target only the deleted file
        health.check_files([delete_id])
        assert health.last_changed_count == 1

        state_by_id = {int(r[0]): str(r[1]) for r in conn.execute("SELECT id, integrity_state FROM file;").fetchall()}
        assert state_by_id[delete_id] == "MISSING"
        # The kept file should remain OK
        assert state_by_id[keep_id] == "OK"
    finally:
        conn.close()
