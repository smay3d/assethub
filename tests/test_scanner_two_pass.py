from __future__ import annotations

import os
import time
from pathlib import Path


def _make_env(tmp_path: Path):
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.storage.roots import StorageManager

    conn = get_connection(str(tmp_path / "test.db"))
    initialize_schema(conn)
    sm = StorageManager(conn)
    sm.ensure_unmanaged_storage()
    root = tmp_path / "root"
    root.mkdir()
    sm.register_root(str(root), name="TestRoot")
    return conn, sm, str(root)


def _make_scanner(conn, sm):
    from assethub.core.scanner.scanner import Scanner
    return Scanner(conn, sm)


def test_scan_files_only_leaves_checksums_null(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "a.txt").write_bytes(b"hello")
    scanner = _make_scanner(conn, sm)

    result = scanner.scan_files_only()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='a.txt'").fetchone()
    assert row is not None
    assert row[0] is None
    assert result.files_indexed == 1
    assert result.files_checksummed == 0


def test_scan_files_only_preserves_existing_checksum(tmp_path: Path) -> None:
    """Unchanged file keeps its existing checksum after scan_files_only."""
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "b.txt").write_bytes(b"stable content")
    scanner = _make_scanner(conn, sm)

    scanner.scan_all()  # populate with a real checksum

    # Poison the checksum — scan_files_only must leave it alone for unchanged files.
    conn.execute("UPDATE file SET checksum='poisoned' WHERE relative_path='b.txt'")
    conn.commit()

    scanner.scan_files_only()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='b.txt'").fetchone()
    assert row[0] == "poisoned", "scan_files_only overwrote a valid checksum for an unchanged file"


def test_scan_files_only_nulls_stale_checksum(tmp_path: Path) -> None:
    """Changed file (different mtime) has its checksum NULLed by scan_files_only."""
    conn, sm, root = _make_env(tmp_path)
    f = Path(root) / "c.txt"
    f.write_bytes(b"version 1")
    scanner = _make_scanner(conn, sm)

    scanner.scan_all()  # get a real checksum first

    original = conn.execute("SELECT checksum FROM file WHERE relative_path='c.txt'").fetchone()[0]
    assert original is not None

    # Modify the file so size and mtime change.
    time.sleep(0.05)
    f.write_bytes(b"version 2 - different content")
    os.utime(str(f), None)

    scanner.scan_files_only()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='c.txt'").fetchone()
    assert row[0] is None, "scan_files_only did not NULL the stale checksum after file changed"
