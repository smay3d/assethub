import sqlite3

from assethub.core.db.schema import initialize_schema
from assethub.core.db.assets import create_asset
from assethub.core.db.versions import create_version
from assethub.core.db.version_membership import attach_files_to_version
from assethub.core.db.file_bindings import bind_files_to_asset, unbind_files
from assethub.core.db.binding_versioning import (
    get_latest_non_discarded_version_id,
    version_up_for_binding_change,
)


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


def _members(conn: sqlite3.Connection, *, version_id: int) -> set[int]:
    rows = conn.execute(
        "SELECT file_id FROM version_file WHERE version_id=? ORDER BY file_id ASC;",
        (int(version_id),),
    ).fetchall()
    return {int(r[0]) for r in rows}


def test_binding_change_versions_up_and_carries_forward(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")
    a = create_asset(conn, storage_id=sid, type="generic", key="A", name="Asset A", commit=False)

    f_in = _insert_file(conn, storage_id=sid, rel="foo/in_v01.txt")
    f_bound = _insert_file(conn, storage_id=sid, rel="foo/bound.txt")

    v1 = create_version(conn, asset_id=int(a.id), sort_key_override=1, commit=False)
    attach_files_to_version(conn, version_id=int(v1.id), file_ids=[f_in])
    conn.commit()

    # Bind then version-up. The new snapshot should include the bound file.
    with conn:
        bind_files_to_asset(conn, asset_id=int(a.id), file_ids=[f_bound], commit=False)
        res = version_up_for_binding_change(conn, asset_id=int(a.id), note="test bind")

    latest = get_latest_non_discarded_version_id(conn, asset_id=int(a.id))
    assert latest == int(res.new_version_id)
    assert _members(conn, version_id=int(res.new_version_id)) == {f_in, f_bound}


def test_unbind_versions_up_and_removes_from_latest_snapshot(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")
    a = create_asset(conn, storage_id=sid, type="generic", key="A", name="Asset A", commit=False)

    f_in = _insert_file(conn, storage_id=sid, rel="foo/in_v01.txt")
    f_bound = _insert_file(conn, storage_id=sid, rel="foo/bound.txt")

    v1 = create_version(conn, asset_id=int(a.id), sort_key_override=1, commit=False)
    attach_files_to_version(conn, version_id=int(v1.id), file_ids=[f_in])
    bind_files_to_asset(conn, asset_id=int(a.id), file_ids=[f_bound], commit=False)
    conn.commit()

    # First binding version-up (asset has f_bound in latest).
    with conn:
        res1 = version_up_for_binding_change(conn, asset_id=int(a.id), note="setup")

    assert f_bound in _members(conn, version_id=int(res1.new_version_id))

    # Unbind then version-up with removal. Latest should drop the file.
    with conn:
        unbind_files(conn, file_ids=[f_bound], commit=False)
        res2 = version_up_for_binding_change(conn, asset_id=int(a.id), removed_file_ids=[f_bound], note="test unbind")

    assert f_bound not in _members(conn, version_id=int(res2.new_version_id))
    assert f_in in _members(conn, version_id=int(res2.new_version_id))


def test_rebind_versions_up_old_and_new_assets(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")
    a = create_asset(conn, storage_id=sid, type="generic", key="A", name="Asset A", commit=False)
    b = create_asset(conn, storage_id=sid, type="generic", key="B", name="Asset B", commit=False)

    f = _insert_file(conn, storage_id=sid, rel="foo/shared.txt")

    # Seed assets with an initial version (empty membership is fine).
    create_version(conn, asset_id=int(a.id), sort_key_override=1, commit=False)
    create_version(conn, asset_id=int(b.id), sort_key_override=1, commit=False)
    conn.commit()

    # Bind to A then version up.
    with conn:
        bind_files_to_asset(conn, asset_id=int(a.id), file_ids=[f], allow_rebind=True, commit=False)
        ra = version_up_for_binding_change(conn, asset_id=int(a.id), note="bind to A")
    assert f in _members(conn, version_id=int(ra.new_version_id))

    # Rebind to B; old A should drop, new B should gain.
    with conn:
        bind_files_to_asset(conn, asset_id=int(b.id), file_ids=[f], allow_rebind=True, commit=False)
        rb_old = version_up_for_binding_change(conn, asset_id=int(a.id), removed_file_ids=[f], note="rebind away")
        rb_new = version_up_for_binding_change(conn, asset_id=int(b.id), note="rebind to B")

    assert f not in _members(conn, version_id=int(rb_old.new_version_id))
    assert f in _members(conn, version_id=int(rb_new.new_version_id))