# tests/test_db_assets_versions.py

from __future__ import annotations

import sqlite3

from assethub.core.db.assets import create_asset, get_asset, list_assets_for_storage
from assethub.core.db.versions import (
    create_version,
    get_version,
    list_versions_for_asset,
    resolve_file_to_asset_version,
)
from assethub.core.db.schema import initialize_schema


def test_asset_create_or_fetch_by_identity(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    # Create a storage root.
    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, ?);",
        ("RootA", "/tmp/root_a", "OK"),
    )
    sid = int(conn.execute("SELECT id FROM storage WHERE name='RootA';").fetchone()[0])

    a1 = create_asset(conn, storage_id=sid, type="generic", key="K", name="My Asset")
    a2 = create_asset(conn, storage_id=sid, type="generic", key="K", name="My Asset (ignored)")

    assert a1.id == a2.id
    assert a1.storage_id == sid
    assert a1.type == "generic"
    assert a1.key == "K"

    fetched = get_asset(conn, a1.id)
    assert fetched is not None
    assert fetched.id == a1.id

    items = list_assets_for_storage(conn, sid)
    assert len(items) == 1
    assert items[0].id == a1.id


def test_version_create_increments_sort_key(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, ?);",
        ("RootA", "/tmp/root_a", "OK"),
    )
    sid = int(conn.execute("SELECT id FROM storage WHERE name='RootA';").fetchone()[0])

    asset = create_asset(conn, storage_id=sid, type="generic", key="K", name="My Asset")

    v1 = create_version(conn, asset_id=asset.id)
    v2 = create_version(conn, asset_id=asset.id)

    assert v1.sort_key == 1
    assert v1.label == "v01"
    assert v2.sort_key == 2
    assert v2.label == "v02"

    fetched = get_version(conn, v1.id)
    assert fetched is not None
    assert fetched.id == v1.id

    items = list_versions_for_asset(conn, asset.id)
    assert [v.sort_key for v in items] == [1, 2]


def test_resolve_file_to_asset_version(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, ?);",
        ("RootA", "/tmp/root_a", "OK"),
    )
    sid = int(conn.execute("SELECT id FROM storage WHERE name='RootA';").fetchone()[0])

    asset = create_asset(conn, storage_id=sid, type="generic", key="K", name="My Asset")
    ver = create_version(conn, asset_id=asset.id)

    # File without a version resolves to None.
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (?, ?, ?);",
        (sid, "a.txt", "OK"),
    )
    file_id_no_ver = int(conn.execute("SELECT id FROM file WHERE relative_path='a.txt';").fetchone()[0])
    assert resolve_file_to_asset_version(conn, file_id_no_ver) is None

    # File with version resolves.
    conn.execute(
        "INSERT INTO file(storage_id, relative_path, integrity_state, version_id) VALUES (?, ?, ?, ?);",
        (sid, "b.txt", "OK", ver.id),
    )
    file_id = int(conn.execute("SELECT id FROM file WHERE relative_path='b.txt';").fetchone()[0])

    resolved = resolve_file_to_asset_version(conn, file_id)
    assert resolved is not None
    a, v = resolved
    assert a.id == asset.id
    assert v.id == ver.id
