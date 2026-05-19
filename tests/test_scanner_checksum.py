from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest


def _make_env(tmp_path: Path):
    """Return (conn, storage_manager, root_path) for a fresh test environment."""
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


def test_new_file_gets_checksum(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "a.txt").write_bytes(b"hello world")

    scanner = _make_scanner(conn, sm)
    result = scanner.scan_all()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='a.txt'").fetchone()
    assert row is not None
    assert row[0] is not None
    assert len(row[0]) == 64  # SHA-256 hex digest length
    assert result.files_checksummed == 1
    assert result.files_without_checksum == 0


def test_unchanged_file_checksum_preserved(tmp_path: Path) -> None:
    """Unchanged file (same size + mtime) must NOT recompute checksum.

    Poison the stored checksum after first scan. If the second scan
    recomputes, the poison disappears — meaning the cache is broken.
    """
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "b.txt").write_bytes(b"stable content")

    scanner = _make_scanner(conn, sm)
    scanner.scan_all()

    # Poison the checksum in the DB.
    conn.execute("UPDATE file SET checksum='poisoned_value' WHERE relative_path='b.txt'")
    conn.commit()

    # Second scan — file is unchanged, poison must survive.
    result = scanner.scan_all()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='b.txt'").fetchone()
    assert row[0] == "poisoned_value", "Checksum was recomputed for an unchanged file"
    assert result.files_checksummed == 0


def test_changed_file_recomputes_checksum(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    f = Path(root) / "c.txt"
    f.write_bytes(b"version 1")

    scanner = _make_scanner(conn, sm)
    scanner.scan_all()

    original = conn.execute("SELECT checksum FROM file WHERE relative_path='c.txt'").fetchone()[0]

    # Overwrite file content and bump mtime.
    time.sleep(0.05)
    f.write_bytes(b"version 2 - different content")
    os.utime(str(f), None)

    result = scanner.scan_all()

    new_checksum = conn.execute("SELECT checksum FROM file WHERE relative_path='c.txt'").fetchone()[0]
    assert new_checksum != original, "Checksum was not updated after file changed"
    assert result.files_checksummed == 1


def test_null_checksum_file_gets_checksummed_on_next_scan(tmp_path: Path) -> None:
    """A file with checksum=NULL but unchanged size/mtime must be checksummed.

    This covers the database-upgrade case: existing records from before v9
    have NULL checksums but valid size/mtime.
    """
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "d.txt").write_bytes(b"needs checksum")

    scanner = _make_scanner(conn, sm)
    scanner.scan_all()

    # Simulate a pre-v9 record by clearing the checksum.
    conn.execute("UPDATE file SET checksum=NULL WHERE relative_path='d.txt'")
    conn.commit()

    result = scanner.scan_all()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='d.txt'").fetchone()
    assert row[0] is not None, "NULL checksum was not filled in on subsequent scan"
    assert result.files_checksummed == 1
    assert result.files_without_checksum == 0


def test_scan_result_without_checksum_count(tmp_path: Path) -> None:
    """files_without_checksum reflects all NULL-checksum file records after scan."""
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "e.txt").write_bytes(b"data")

    scanner = _make_scanner(conn, sm)
    result = scanner.scan_all()

    assert result.files_without_checksum == 0

    # Force a NULL checksum then check the count.
    conn.execute("UPDATE file SET checksum=NULL WHERE relative_path='e.txt'")
    conn.commit()

    # Re-scan: NULL → fills in checksum.
    result2 = scanner.scan_all()
    assert result2.files_without_checksum == 0
    assert result2.files_checksummed == 1


def test_multiple_files_all_get_checksums(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    for i in range(5):
        (Path(root) / f"file{i}.txt").write_bytes(f"content {i}".encode())

    scanner = _make_scanner(conn, sm)
    result = scanner.scan_all()

    assert result.files_checksummed == 5
    assert result.files_without_checksum == 0
    null_count = conn.execute("SELECT COUNT(*) FROM file WHERE checksum IS NULL").fetchone()[0]
    assert null_count == 0
