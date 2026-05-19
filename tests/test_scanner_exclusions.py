# tests/test_scanner_exclusions.py
from __future__ import annotations

import sqlite3
from pathlib import Path

from assethub.core.db.schema import initialize_schema
from assethub.core.db.scan_exclusions import add_exclusion
from assethub.core.scanner.scanner import Scanner
from assethub.core.storage.roots import StorageManager


def _mk_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.sqlite3")
    initialize_schema(conn)
    return conn


def _mk_root(conn: sqlite3.Connection, path: Path) -> int:
    sm = StorageManager(conn)
    root = sm.register_root(str(path))
    return int(root.id)


def _indexed_paths(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT relative_path FROM file;").fetchall()
    return {str(r[0]) for r in rows}


def test_excluded_extension_not_indexed(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    (root_dir / "texture.png").write_text("data")
    (root_dir / "cache.log").write_text("data")

    sid = _mk_root(conn, root_dir)
    add_exclusion(conn, sid, "log")

    scanner = Scanner(conn, StorageManager(conn))
    scanner.scan_all()

    paths = _indexed_paths(conn)
    assert "texture.png" in paths
    assert "cache.log" not in paths


def test_non_excluded_extension_is_indexed(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    (root_dir / "model.fbx").write_text("data")

    sid = _mk_root(conn, root_dir)
    add_exclusion(conn, sid, "log")  # only log excluded

    scanner = Scanner(conn, StorageManager(conn))
    scanner.scan_all()

    assert "model.fbx" in _indexed_paths(conn)


def test_exclusions_are_per_root(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)

    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "file.log").write_text("data")
    (root_b / "file.log").write_text("data")

    sid_a = _mk_root(conn, root_a)
    sid_b = _mk_root(conn, root_b)
    add_exclusion(conn, sid_a, "log")  # only root_a excludes log

    scanner = Scanner(conn, StorageManager(conn))
    scanner.scan_all()

    # root_b's file.log should be indexed (same relative_path, different storage_id)
    rows = conn.execute(
        "SELECT storage_id FROM file WHERE relative_path='file.log';"
    ).fetchall()
    assert len(rows) == 1, "expected exactly one file.log row (root_b only)"
    assert rows[0][0] == sid_b, "surviving file.log must belong to root_b, not root_a"


def test_already_indexed_files_remain_after_exclusion_added(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    (root_dir / "junk.log").write_text("data")

    sid = _mk_root(conn, root_dir)
    scanner = Scanner(conn, StorageManager(conn))

    # First scan: no exclusions — file gets indexed
    scanner.scan_all()
    assert "junk.log" in _indexed_paths(conn)

    # Add exclusion, re-scan — file must remain in DB (Option A: no automatic cleanup)
    add_exclusion(conn, sid, "log")
    scanner.scan_all()
    assert "junk.log" in _indexed_paths(conn)


def test_no_exclusions_indexes_all_files(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    (root_dir / "a.png").write_text("data")
    (root_dir / "b.fbx").write_text("data")
    (root_dir / "c.log").write_text("data")

    _mk_root(conn, root_dir)
    scanner = Scanner(conn, StorageManager(conn))
    scanner.scan_all()

    paths = _indexed_paths(conn)
    assert paths == {"a.png", "b.fbx", "c.log"}
