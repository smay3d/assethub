# tests/test_scan_exclusions.py
from __future__ import annotations

import sqlite3
from pathlib import Path

from assethub.core.db.schema import initialize_schema
from assethub.core.db.scan_exclusions import (
    get_exclusions,
    set_exclusions,
    add_exclusion,
    remove_exclusion,
)


def _mk_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.sqlite3")
    initialize_schema(conn)
    return conn


def _insert_root(conn: sqlite3.Connection, name: str = "Root") -> int:
    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, 'OK');",
        (name, f"/tmp/{name}"),
    )
    conn.commit()
    return int(conn.execute("SELECT id FROM storage WHERE name=?;", (name,)).fetchone()[0])


def test_get_exclusions_empty_for_new_root(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    assert get_exclusions(conn, sid) == frozenset()


def test_add_exclusion_and_retrieve(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    assert get_exclusions(conn, sid) == frozenset({"log"})


def test_add_exclusion_normalizes_dot_and_case(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, ".LOG")
    assert get_exclusions(conn, sid) == frozenset({"log"})


def test_add_exclusion_duplicate_is_ignored(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    add_exclusion(conn, sid, "log")  # should not raise
    assert get_exclusions(conn, sid) == frozenset({"log"})


def test_remove_exclusion(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    remove_exclusion(conn, sid, "log")
    assert get_exclusions(conn, sid) == frozenset()


def test_remove_nonexistent_exclusion_is_noop(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    remove_exclusion(conn, sid, "log")  # should not raise


def test_set_exclusions_replaces_full_set(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    add_exclusion(conn, sid, "tmp")
    set_exclusions(conn, sid, ["png", "jpg"])
    assert get_exclusions(conn, sid) == frozenset({"png", "jpg"})


def test_set_exclusions_to_empty_clears_all(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    set_exclusions(conn, sid, [])
    assert get_exclusions(conn, sid) == frozenset()


def test_set_exclusions_normalizes_extensions(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    set_exclusions(conn, sid, [".PNG", "JPG", ".Fbx"])
    assert get_exclusions(conn, sid) == frozenset({"png", "jpg", "fbx"})


def test_exclusions_are_per_root(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid_a = _insert_root(conn, "RootA")
    sid_b = _insert_root(conn, "RootB")
    add_exclusion(conn, sid_a, "log")
    assert get_exclusions(conn, sid_b) == frozenset()


def test_removing_storage_root_cascades_exclusions(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    sid = _insert_root(conn)
    add_exclusion(conn, sid, "log")
    conn.execute("DELETE FROM storage WHERE id=?;", (sid,))
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM storage_scan_exclusion WHERE storage_id=?;", (sid,)
    ).fetchone()[0]
    assert count == 0
