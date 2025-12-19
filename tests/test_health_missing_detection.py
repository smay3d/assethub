from __future__ import annotations

from pathlib import Path


def test_health_checker_marks_missing_files(tmp_path: Path) -> None:
    """Stage 6.4: Health v1 should mark deleted files as MISSING.

    Flow:
      - Create files under a registered root
      - Scan to index them
      - Delete one file
      - Run health check
      - Verify integrity_state updates
    """

    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.storage.roots import StorageManager
    from assethub.core.scanner.scanner import Scanner
    from assethub.core.health.checker import HealthChecker

    db_path = tmp_path / "assethub_test.db"
    root = tmp_path / "root"
    root.mkdir()

    # Create two files
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

        health = HealthChecker(conn, storage)
        health.check_all_files()

        cur = conn.cursor()
        cur.execute(
            "SELECT relative_path, integrity_state FROM file ORDER BY relative_path;"
        )
        rows = cur.fetchall()

        # Normalize rows into dict for comparison
        state_by_rel = {r[0].replace('\\', '/'): r[1] for r in rows}
        assert state_by_rel["keep.txt"] == "OK"
        assert state_by_rel["delete.txt"] == "MISSING"
    finally:
        conn.close()