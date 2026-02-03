import sqlite3

from assethub.core.db.schema import initialize_schema
from assethub.core.db.assets import create_asset
from assethub.core.db.file_bindings import (
    bind_files_to_asset,
    get_bound_asset_id,
    list_bound_file_ids_for_asset,
    unbind_files,
)
from assethub.core.db.versions import create_version
from assethub.core.db.version_membership import attach_files_to_version, fork_version


def _insert_storage(conn: sqlite3.Connection, *, name: str, root_path: str) -> int:
    conn.execute(
        "INSERT INTO storage(name, display_name, root_path, status) VALUES (?, ?, ?, ?);",
        (name, name, root_path, "OK"),
    )
    row = conn.execute("SELECT id FROM storage WHERE name=?;", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _insert_file(conn: sqlite3.Connection, *, storage_id: int, rel: str) -> int:
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state, size_bytes, mtime_unix) "
        "VALUES (?, ?, ?, ?, ?);",
        (int(storage_id), rel, "OK", 1, 1.0),
    )
    row = conn.execute(
        "SELECT id FROM file WHERE storage_id=? AND relative_path=?;",
        (int(storage_id), rel),
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_file_binding_roundtrip_and_unbind(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")
    a = create_asset(conn, storage_id=sid, type="generic", key="A", name="Asset A", commit=False)
    f1 = _insert_file(conn, storage_id=sid, rel="foo/a.txt")
    f2 = _insert_file(conn, storage_id=sid, rel="foo/b.txt")
    conn.commit()

    n = bind_files_to_asset(conn, asset_id=int(a.id), file_ids=[f1, f2])
    assert n == 2
    assert get_bound_asset_id(conn, file_id=f1) == int(a.id)
    assert set(list_bound_file_ids_for_asset(conn, asset_id=int(a.id))) == {f1, f2}

    removed = unbind_files(conn, file_ids=[f1])
    assert removed == 1
    assert get_bound_asset_id(conn, file_id=f1) is None
    assert set(list_bound_file_ids_for_asset(conn, asset_id=int(a.id))) == {f2}


def test_bound_files_carry_forward_into_forked_versions(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")
    a = create_asset(conn, storage_id=sid, type="generic", key="A", name="Asset A", commit=False)

    f_in = _insert_file(conn, storage_id=sid, rel="foo/in_v01.txt")
    f_bound = _insert_file(conn, storage_id=sid, rel="foo/bound.txt")
    v1 = create_version(conn, asset_id=int(a.id), sort_key_override=1, commit=False)
    attach_files_to_version(conn, version_id=int(v1.id), file_ids=[f_in])
    bind_files_to_asset(conn, asset_id=int(a.id), file_ids=[f_bound])
    conn.commit()

    res = fork_version(conn, source_version_id=int(v1.id))
    new_vid = int(res.new_version_id)

    # New version includes both cloned members and the bound file.
    mem = {
        int(r[0])
        for r in conn.execute(
            "SELECT file_id FROM version_file WHERE version_id=? ORDER BY file_id ASC;",
            (new_vid,),
        ).fetchall()
    }
    assert f_in in mem
    assert f_bound in mem

    # Source version membership is unchanged.
    mem_src = {
        int(r[0])
        for r in conn.execute(
            "SELECT file_id FROM version_file WHERE version_id=? ORDER BY file_id ASC;",
            (int(v1.id),),
        ).fetchall()
    }
    assert mem_src == {f_in}
