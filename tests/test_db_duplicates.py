from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _db(tmp_path: Path, name: str = "test.db") -> sqlite3.Connection:
    from assethub.core.db.connection import get_connection
    from assethub.core.db.schema import initialize_schema

    conn = get_connection(str(tmp_path / name))
    initialize_schema(conn)
    return conn


def _add_storage(conn: sqlite3.Connection, name: str = "Root", path: str = "/root") -> int:
    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, 'OK')", (name, path)
    )
    conn.commit()
    return int(conn.execute("SELECT id FROM storage WHERE name=?", (name,)).fetchone()[0])


def _add_file(
    conn: sqlite3.Connection,
    storage_id: int,
    rel_path: str,
    checksum: str | None = None,
    size_bytes: int = 1000,
) -> int:
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state, size_bytes, checksum)"
        " VALUES (?, ?, 'OK', ?, ?)",
        (storage_id, rel_path, size_bytes, checksum),
    )
    conn.commit()
    return int(
        conn.execute("SELECT id FROM file WHERE relative_path=?", (rel_path,)).fetchone()[0]
    )


# --- query_duplicate_groups ---

def test_empty_db_returns_no_groups(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    assert query_duplicate_groups(conn) == []


def test_unique_checksums_return_no_groups(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    _add_file(conn, sid, "a.txt", checksum="aaa111")
    _add_file(conn, sid, "b.txt", checksum="bbb222")
    assert query_duplicate_groups(conn) == []


def test_two_files_same_checksum_form_one_group(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    _add_file(conn, sid, "a.txt", checksum="shared_hash", size_bytes=500)
    _add_file(conn, sid, "b.txt", checksum="shared_hash", size_bytes=500)

    groups = query_duplicate_groups(conn)
    assert len(groups) == 1
    g = groups[0]
    assert g.checksum == "shared_hash"
    assert g.file_count == 2
    assert len(g.files) == 2


def test_null_checksums_excluded_from_groups(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    _add_file(conn, sid, "a.txt", checksum=None)
    _add_file(conn, sid, "b.txt", checksum=None)
    assert query_duplicate_groups(conn) == []


def test_groups_sorted_by_file_count_desc(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    # 2-copy group
    _add_file(conn, sid, "a1.txt", checksum="dup2", size_bytes=100)
    _add_file(conn, sid, "a2.txt", checksum="dup2", size_bytes=100)
    # 3-copy group
    _add_file(conn, sid, "b1.txt", checksum="dup3", size_bytes=200)
    _add_file(conn, sid, "b2.txt", checksum="dup3", size_bytes=200)
    _add_file(conn, sid, "b3.txt", checksum="dup3", size_bytes=200)

    groups = query_duplicate_groups(conn)
    assert len(groups) == 2
    assert groups[0].file_count == 3  # dup3 first
    assert groups[1].file_count == 2  # dup2 second


def test_groups_with_equal_count_sorted_by_size_desc(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    _add_file(conn, sid, "small1.txt", checksum="small", size_bytes=100)
    _add_file(conn, sid, "small2.txt", checksum="small", size_bytes=100)
    _add_file(conn, sid, "big1.txt", checksum="big", size_bytes=9000)
    _add_file(conn, sid, "big2.txt", checksum="big", size_bytes=9000)

    groups = query_duplicate_groups(conn)
    assert groups[0].files[0].size_bytes == 9000  # big group first


def test_duplicate_file_has_correct_storage_name(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import query_duplicate_groups

    conn = _db(tmp_path)
    sid = _add_storage(conn, name="MyRoot", path="/my/root")
    _add_file(conn, sid, "a.txt", checksum="xyz")
    _add_file(conn, sid, "b.txt", checksum="xyz")

    groups = query_duplicate_groups(conn)
    for f in groups[0].files:
        assert f.storage_name == "MyRoot"


# --- get_duplicate_file_ids ---

def test_get_duplicate_file_ids_returns_only_duplicates(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import get_duplicate_file_ids

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    fid_a = _add_file(conn, sid, "a.txt", checksum="shared")
    fid_b = _add_file(conn, sid, "b.txt", checksum="shared")
    fid_c = _add_file(conn, sid, "c.txt", checksum="unique")

    dup_ids = get_duplicate_file_ids(conn)
    assert isinstance(dup_ids, frozenset)
    assert fid_a in dup_ids
    assert fid_b in dup_ids
    assert fid_c not in dup_ids


def test_get_duplicate_file_ids_empty_db(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import get_duplicate_file_ids

    conn = _db(tmp_path)
    assert get_duplicate_file_ids(conn) == frozenset()


# --- count_checksummed_files ---

def test_count_checksummed_files_mixed(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import count_checksummed_files

    conn = _db(tmp_path)
    sid = _add_storage(conn)
    _add_file(conn, sid, "a.txt", checksum="abc")
    _add_file(conn, sid, "b.txt", checksum=None)
    _add_file(conn, sid, "c.txt", checksum="def")

    checksummed, total = count_checksummed_files(conn)
    assert checksummed == 2
    assert total == 3


def test_count_checksummed_files_empty_db(tmp_path: Path) -> None:
    from assethub.core.db.duplicates import count_checksummed_files

    conn = _db(tmp_path)
    checksummed, total = count_checksummed_files(conn)
    assert checksummed == 0
    assert total == 0
