# tests/test_library_file_query.py
"""
Tests for query_library_files — the server-side file query used by the Library tab.

Key invariant: search is applied in SQL, so files beyond the display cap are
reachable when a search term is present.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from assethub.core.db.schema import initialize_schema
from assethub.core.db.file_records import query_library_files


def _mk_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.sqlite3")
    initialize_schema(conn)
    return conn


def _insert_root(conn: sqlite3.Connection, name: str = "Root", path: str = "/tmp/r") -> int:
    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, 'OK');",
        (name, path),
    )
    conn.commit()
    return int(conn.execute("SELECT id FROM storage WHERE name=?;", (name,)).fetchone()[0])


def _insert_file(conn: sqlite3.Connection, storage_id: int, rel_path: str) -> int:
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (?, ?, 'OK');",
        (storage_id, rel_path),
    )
    conn.commit()
    return int(conn.execute("SELECT last_insert_rowid();").fetchone()[0])


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------

def test_empty_db_returns_empty_result(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    result = query_library_files(conn)
    assert result.rows == []
    assert result.total_in_db == 0
    assert result.truncated is False


def test_returns_all_files_when_under_cap(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    _insert_file(conn, sid, "a/one.png")
    _insert_file(conn, sid, "b/two.png")

    result = query_library_files(conn, limit=100)

    assert len(result.rows) == 2
    assert result.total_in_db == 2
    assert result.truncated is False


def test_truncation_at_cap(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    for i in range(5):
        _insert_file(conn, sid, f"dir/file_{i}.png")

    result = query_library_files(conn, limit=3)

    assert len(result.rows) == 3
    assert result.total_in_db == 5
    assert result.truncated is True


# ---------------------------------------------------------------------------
# Search: core invariant — server-side, reaches beyond the cap
# ---------------------------------------------------------------------------

def test_search_finds_file_beyond_cap(tmp_path: Path) -> None:
    """The bug scenario: a file past the row cap is invisible without server-side search."""
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    _insert_file(conn, sid, "a/foo.png")
    _insert_file(conn, sid, "b/bar.png")
    _insert_file(conn, sid, "c/target.zip")   # would be cut off at cap=2

    # Without search, cap=2 hides the .zip
    no_search = query_library_files(conn, limit=2)
    assert no_search.truncated is True
    assert all(r.relative_path != "c/target.zip" for r in no_search.rows)

    # With search, SQL filter runs before LIMIT — .zip is found
    with_search = query_library_files(conn, search_text=".zip", limit=2)
    assert len(with_search.rows) == 1
    assert with_search.rows[0].relative_path == "c/target.zip"
    assert with_search.truncated is False


def test_search_matches_filename_substring(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    _insert_file(conn, sid, "textures/rock_albedo.png")
    _insert_file(conn, sid, "textures/rock_normal.png")
    _insert_file(conn, sid, "meshes/rock_high.fbx")

    result = query_library_files(conn, search_text="albedo")

    assert len(result.rows) == 1
    assert result.rows[0].relative_path == "textures/rock_albedo.png"


def test_search_matches_path_substring(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    _insert_file(conn, sid, "props/barrel/barrel_diff.png")
    _insert_file(conn, sid, "chars/hero/hero_diff.png")

    result = query_library_files(conn, search_text="barrel")

    assert len(result.rows) == 1
    assert "barrel" in result.rows[0].relative_path


def test_search_is_case_insensitive(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    _insert_file(conn, sid, "assets/Hero_Diffuse.PNG")
    _insert_file(conn, sid, "assets/rock.png")

    result = query_library_files(conn, search_text="hero")

    assert len(result.rows) == 1
    assert result.rows[0].relative_path == "assets/Hero_Diffuse.PNG"


def test_search_no_matches_returns_empty(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    _insert_file(conn, sid, "a/foo.png")

    result = query_library_files(conn, search_text="zzz_not_found")

    assert result.rows == []
    assert result.truncated is False


def test_empty_search_text_returns_all(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    _insert_file(conn, sid, "a/one.png")
    _insert_file(conn, sid, "b/two.png")

    result = query_library_files(conn, search_text="", limit=100)

    assert len(result.rows) == 2


# ---------------------------------------------------------------------------
# Row fields
# ---------------------------------------------------------------------------

def test_row_fields_are_populated(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    _insert_file(conn, sid, "textures/albedo.png")

    result = query_library_files(conn)

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.file_id > 0
    assert row.storage_id == sid
    assert row.relative_path == "textures/albedo.png"
    assert row.integrity_state == "OK"
    assert row.bound_asset_id is None
    assert row.owned_version_count == 0


# ---------------------------------------------------------------------------
# query_library_files_by_ids
# ---------------------------------------------------------------------------

def test_query_by_ids_returns_correct_files(tmp_path: Path) -> None:
    """query_library_files_by_ids returns only the requested file IDs."""
    from assethub.core.db.file_records import query_library_files_by_ids

    conn = _mk_db(tmp_path)
    sid = _insert_root(conn)
    fid_a = _insert_file(conn, sid, "a.txt")
    fid_b = _insert_file(conn, sid, "b.txt")
    fid_c = _insert_file(conn, sid, "c.txt")

    result = query_library_files_by_ids(conn, [fid_a, fid_b])
    assert len(result) == 2
    ids = {r.file_id for r in result}
    assert fid_a in ids
    assert fid_b in ids
    assert fid_c not in ids


def test_query_by_ids_empty_list_returns_empty(tmp_path: Path) -> None:
    from assethub.core.db.file_records import query_library_files_by_ids

    conn = _mk_db(tmp_path)
    assert query_library_files_by_ids(conn, []) == []


def test_query_by_ids_returns_library_file_rows(tmp_path: Path) -> None:
    """Result items are LibraryFileRow instances (compatible with FileTableModel)."""
    from assethub.core.db.file_records import query_library_files_by_ids, LibraryFileRow

    conn = _mk_db(tmp_path)
    sid = _insert_root(conn, "S", "/s")
    fid = _insert_file(conn, sid, "x.txt")

    result = query_library_files_by_ids(conn, [fid])
    assert len(result) == 1
    assert isinstance(result[0], LibraryFileRow)
