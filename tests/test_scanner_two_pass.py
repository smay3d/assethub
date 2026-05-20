from __future__ import annotations

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

    # Modify the file — the larger content guarantees a size change.
    f.write_bytes(b"version 2 - different content")

    scanner.scan_files_only()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='c.txt'").fetchone()
    assert row[0] is None, "scan_files_only did not NULL the stale checksum after file changed"


def test_scan_files_only_cancel_stops_early(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    for i in range(5):
        (Path(root) / f"file{i}.txt").write_bytes(f"content {i}".encode())
    scanner = _make_scanner(conn, sm)

    result = scanner.scan_files_only(cancel_check=lambda: True)

    assert result.canceled
    assert result.files_indexed == 0


def test_compute_missing_checksums_hashes_null_files(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    (Path(root) / "a.txt").write_bytes(b"some content")
    scanner = _make_scanner(conn, sm)

    scanner.scan_files_only()  # leaves checksum NULL

    result = scanner.compute_missing_checksums()

    row = conn.execute("SELECT checksum FROM file WHERE relative_path='a.txt'").fetchone()
    assert row[0] is not None
    assert len(row[0]) == 64  # SHA-256 hex digest length
    assert result.files_checksummed == 1
    assert result.files_failed == 0
    assert not result.canceled


def test_compute_missing_checksums_processes_beyond_batch_size(tmp_path: Path) -> None:
    """All files are checksummed even when count exceeds the internal batch size (50)."""
    conn, sm, root = _make_env(tmp_path)
    for i in range(55):
        (Path(root) / f"file{i}.txt").write_bytes(f"content {i}".encode())
    scanner = _make_scanner(conn, sm)

    scanner.scan_files_only()
    result = scanner.compute_missing_checksums()

    null_count = conn.execute("SELECT COUNT(*) FROM file WHERE checksum IS NULL").fetchone()[0]
    assert null_count == 0
    assert result.files_checksummed == 55


def test_compute_missing_checksums_cancel_stops_early(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    for i in range(5):
        (Path(root) / f"file{i}.txt").write_bytes(f"content {i}".encode())
    scanner = _make_scanner(conn, sm)
    scanner.scan_files_only()

    # cancel_check returns True immediately — no files should be processed.
    result = scanner.compute_missing_checksums(cancel_check=lambda: True)

    assert result.canceled
    assert result.files_checksummed == 0
    null_count = conn.execute("SELECT COUNT(*) FROM file WHERE checksum IS NULL").fetchone()[0]
    assert null_count == 5


def test_compute_missing_checksums_skips_unreadable_files(tmp_path: Path) -> None:
    conn, sm, root = _make_env(tmp_path)
    f = Path(root) / "gone.txt"
    f.write_bytes(b"temporary")
    scanner = _make_scanner(conn, sm)
    scanner.scan_files_only()

    # Delete after indexing — sha256_file will raise FileNotFoundError (subclass of OSError).
    f.unlink()

    result = scanner.compute_missing_checksums()

    assert result.files_failed == 1
    assert result.files_checksummed == 0
    row = conn.execute("SELECT checksum FROM file WHERE relative_path='gone.txt'").fetchone()
    assert row[0] is None  # checksum stays NULL on failure


def test_two_pass_equivalent_to_scan_all(tmp_path: Path) -> None:
    """scan_files_only() + compute_missing_checksums() produces the same checksums as scan_all()."""
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema
    from assethub.core.storage.roots import StorageManager
    from assethub.core.scanner.scanner import Scanner

    contents = [b"alpha", b"beta", b"gamma"]

    def make_env(base: Path):
        conn = get_connection(str(base / "test.db"))
        initialize_schema(conn)
        sm = StorageManager(conn)
        sm.ensure_unmanaged_storage()
        root = base / "root"
        root.mkdir()
        sm.register_root(str(root), name="TestRoot")
        for i, c in enumerate(contents):
            (root / f"file{i}.txt").write_bytes(c)
        return conn, sm

    # Two-pass
    tp_base = tmp_path / "tp"
    tp_base.mkdir()
    conn1, sm1 = make_env(tp_base)
    s1 = Scanner(conn1, sm1)
    s1.scan_files_only()
    s1.compute_missing_checksums()

    # Single-pass
    sp_base = tmp_path / "sp"
    sp_base.mkdir()
    conn2, sm2 = make_env(sp_base)
    s2 = Scanner(conn2, sm2)
    s2.scan_all()

    rows1 = conn1.execute(
        "SELECT relative_path, checksum FROM file WHERE checksum IS NOT NULL ORDER BY relative_path"
    ).fetchall()
    rows2 = conn2.execute(
        "SELECT relative_path, checksum FROM file WHERE checksum IS NOT NULL ORDER BY relative_path"
    ).fetchall()

    assert rows1 == rows2
