import json
import sqlite3

from assethub.core.db.assets import create_asset
from assethub.core.db.schema import initialize_schema
from assethub.core.db.version_membership import (
    attach_files_to_version,
    detach_files,
    fork_version,
    repair_version_membership,
)
from assethub.core.db.versions import create_version


def _insert_storage(conn: sqlite3.Connection, name: str, root_path: str) -> int:
    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, ?);",
        (name, root_path, "OK"),
    )
    return int(conn.execute("SELECT id FROM storage WHERE name=?;", (name,)).fetchone()[0])


def _insert_file(
    conn: sqlite3.Connection,
    *,
    storage_id: int,
    relative_path: str,
    version_id: int | None = None,
    integrity_state: str = "OK",
    size_bytes: int | None = None,
) -> int:
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, version_id, integrity_state, size_bytes, mtime_unix) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        (int(storage_id), relative_path, version_id, integrity_state, size_bytes, 1000.0),
    )
    fid = int(conn.execute("SELECT last_insert_rowid();").fetchone()[0])
    if version_id is not None:
        conn.execute(
            "INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (?, ?);",
            (int(version_id), int(fid)),
        )
    return fid


def test_attach_honors_enforce_unowned(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, "RootA", "/tmp/root_a")
    asset = create_asset(conn, storage_id=sid, type="generic", key="K", name="My Asset")
    v1 = create_version(conn, asset_id=asset.id)
    v2 = create_version(conn, asset_id=asset.id)

    f_unowned = _insert_file(conn, storage_id=sid, relative_path="a.txt", version_id=None)
    f_owned = _insert_file(conn, storage_id=sid, relative_path="b.txt", version_id=v1.id)
    f_already = _insert_file(conn, storage_id=sid, relative_path="c.txt", version_id=v2.id)
    conn.commit()

    res = attach_files_to_version(
        conn,
        version_id=v2.id,
        file_ids=[f_unowned, f_owned, f_already],
        enforce_unowned=True,
    )

    assert res.attached == 1
    assert res.skipped_owned == 1
    assert res.skipped_already_attached == 1

    row = conn.execute("SELECT version_id FROM file WHERE id=?;", (f_unowned,)).fetchone()
    assert int(row[0]) == v2.id
    row = conn.execute("SELECT version_id FROM file WHERE id=?;", (f_owned,)).fetchone()
    assert int(row[0]) == v1.id

    log = conn.execute(
        "SELECT action_type, payload_json FROM version_change_log WHERE id=?;",
        (res.log_id,),
    ).fetchone()
    assert log is not None
    assert log[0] == "attach"
    payload = json.loads(log[1])
    assert payload["added_file_ids"] == [f_unowned]
    assert payload["skipped_owned"] == 1


def test_detach_clears_membership_and_logs(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, "RootA", "/tmp/root_a")
    asset = create_asset(conn, storage_id=sid, type="generic", key="K", name="My Asset")
    v1 = create_version(conn, asset_id=asset.id)

    f_attached = _insert_file(conn, storage_id=sid, relative_path="a.txt", version_id=v1.id)
    f_unowned = _insert_file(conn, storage_id=sid, relative_path="b.txt", version_id=None)
    conn.commit()

    res = detach_files(conn, file_ids=[f_attached, f_unowned])
    assert res.detached == 1
    assert res.skipped_not_attached == 1
    assert len(res.log_ids) == 1

    row = conn.execute("SELECT version_id FROM file WHERE id=?;", (f_attached,)).fetchone()
    assert row[0] is None

    log = conn.execute(
        "SELECT action_type, payload_json FROM version_change_log WHERE id=?;",
        (res.log_ids[0],),
    ).fetchone()
    assert log is not None
    assert log[0] == "detach"
    payload = json.loads(log[1])
    assert payload["removed_file_ids"] == [f_attached]


def test_repair_swaps_membership_and_logs(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, "RootA", "/tmp/root_a")
    asset = create_asset(conn, storage_id=sid, type="generic", key="K", name="My Asset")
    v1 = create_version(conn, asset_id=asset.id)

    f_old = _insert_file(
        conn,
        storage_id=sid,
        relative_path="old.txt",
        version_id=v1.id,
        integrity_state="MISSING",
        size_bytes=123,
    )
    f_new = _insert_file(
        conn,
        storage_id=sid,
        relative_path="new.txt",
        version_id=None,
        integrity_state="OK",
        size_bytes=456,
    )
    conn.commit()

    res = repair_version_membership(conn, version_id=v1.id, old_file_id=f_old, new_file_id=f_new)
    assert res.removed_old is True
    assert res.added_new is True

    row = conn.execute("SELECT version_id FROM file WHERE id=?;", (f_old,)).fetchone()
    assert row[0] is None
    row = conn.execute("SELECT version_id FROM file WHERE id=?;", (f_new,)).fetchone()
    assert int(row[0]) == v1.id

    log = conn.execute(
        "SELECT action_type, payload_json FROM version_change_log WHERE id=?;",
        (res.log_id,),
    ).fetchone()
    assert log is not None
    assert log[0] == "repair"
    payload = json.loads(log[1])
    assert payload["replaced"][0]["old"] == f_old
    assert payload["replaced"][0]["new"] == f_new


def test_fork_creates_new_version_moves_membership_and_logs(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, "RootA", "/tmp/root_a")
    asset = create_asset(conn, storage_id=sid, type="generic", key="K", name="My Asset")
    v1 = create_version(conn, asset_id=asset.id)

    f_ok = _insert_file(conn, storage_id=sid, relative_path="ok.txt", version_id=v1.id, integrity_state="OK")
    f_missing = _insert_file(
        conn,
        storage_id=sid,
        relative_path="miss.txt",
        version_id=v1.id,
        integrity_state="MISSING",
    )
    f_repl = _insert_file(conn, storage_id=sid, relative_path="repl.txt", version_id=None, integrity_state="OK")
    conn.commit()

    res = fork_version(conn, source_version_id=v1.id, replacement_file_ids=[f_repl])
    assert res.new_version_id != v1.id
    assert f_ok in res.moved_file_ids
    assert f_repl in res.added_replacement_ids

    # OK file moved to the new version; missing stays with source.
    row = conn.execute("SELECT version_id FROM file WHERE id=?;", (f_ok,)).fetchone()
    assert int(row[0]) == res.new_version_id
    row = conn.execute("SELECT version_id FROM file WHERE id=?;", (f_missing,)).fetchone()
    assert int(row[0]) == v1.id

    # New version sort_key should be 2.
    row = conn.execute("SELECT sort_key FROM version WHERE id=?;", (res.new_version_id,)).fetchone()
    assert int(row[0]) == 2

    log = conn.execute(
        "SELECT action_type, payload_json FROM version_change_log WHERE id=?;",
        (res.log_id,),
    ).fetchone()
    assert log is not None
    assert log[0] == "fork"
    payload = json.loads(log[1])
    assert payload["source_version_id"] == v1.id
    assert f_ok in payload["moved_file_ids"]
    assert f_repl in payload["added_file_ids"]
