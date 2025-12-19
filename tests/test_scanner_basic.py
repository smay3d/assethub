from __future__ import annotations

from pathlib import Path


def test_scanner_indexes_files_under_registered_roots(tmp_path: Path) -> None:
    """Stage 6.3: Scanner v1 should index files (only) under registered storage roots.

    This test intentionally does *not* create assets/versions/tags. It only asserts
    that file rows are created with correct storage + relative paths.
    """

    # Local imports to avoid importing Qt in test collection.
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.storage.roots import StorageManager
    from assethub.core.scanner.scanner import Scanner

    db_path = tmp_path / "assethub_test.db"
    root = tmp_path / "root"
    root.mkdir()

    # Create a couple files (and a nested file) under the root.
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    (root / "b.bin").write_bytes(b"\x00\x01\x02")
    nested = root / "nested"
    nested.mkdir()
    (nested / "c.txt").write_text("charlie", encoding="utf-8")

    conn = get_connection(str(db_path))
    try:
        initialize_schema(conn)

        storage = StorageManager(conn)
        storage.ensure_unmanaged_storage()
        storage.register_root(str(root), name="TestRoot")

        scanner = Scanner(conn, storage)
        scanner.scan_all()

        cur = conn.cursor()
        # Ensure we indexed exactly the 3 files created.
        cur.execute("SELECT COUNT(*) FROM file")
        (count,) = cur.fetchone()
        assert count == 3

        # Ensure the relative paths were stored correctly (platform independent).
        cur.execute("SELECT relative_path FROM file ORDER BY relative_path")
        rels = [row[0] for row in cur.fetchall()]
        assert rels == ["a.txt", "b.bin", "nested/c.txt"]
    finally:
        conn.close()
