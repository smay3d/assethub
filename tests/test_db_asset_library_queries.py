from __future__ import annotations

import sqlite3
from pathlib import Path

from assethub.core.db.schema import initialize_schema
from assethub.core.db.asset_library import list_assets_for_storage, list_files_for_version, list_versions


def _mk_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)
    return conn


def test_list_assets_for_storage_counts_and_latest_label(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)

    # Storage root
    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, ?);",
        ("RootA", "/tmp/root_a", "OK"),
    )
    sid = int(conn.execute("SELECT id FROM storage WHERE name='RootA';").fetchone()[0])

    # Two assets with two versions each.
    conn.execute(
        "INSERT INTO asset(id, storage_id, type, key, name) VALUES (1, ?, 'generic', 'K1', 'Alpha');",
        (sid,),
    )
    conn.execute(
        "INSERT INTO asset(id, storage_id, type, key, name) VALUES (2, ?, 'generic', 'K2', 'Beta');",
        (sid,),
    )

    # Versions (sort_key 1,2) per asset
    conn.execute(
        "INSERT INTO version(id, asset_id, label, sort_key, scheme) VALUES (10, 1, 'v01', 1, 'vNN');"
    )
    conn.execute(
        "INSERT INTO version(id, asset_id, label, sort_key, scheme) VALUES (11, 1, 'v02', 2, 'vNN');"
    )
    conn.execute(
        "INSERT INTO version(id, asset_id, label, sort_key, scheme) VALUES (20, 2, 'v01', 1, 'vNN');"
    )
    conn.execute(
        "INSERT INTO version(id, asset_id, label, sort_key, scheme) VALUES (21, 2, 'v02', 2, 'vNN');"
    )

    # Files: asset 1 has 3 files (1 missing), asset 2 has 1 file (0 missing)
    conn.execute(
        "INSERT INTO file(id, version_id, storage_id, relative_path, integrity_state) VALUES (1, 10, ?, 'a/one.png', 'OK');",
        (sid,),
    )
    conn.execute("INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (10, 1);")
    conn.execute(
        "INSERT INTO file(id, version_id, storage_id, relative_path, integrity_state) VALUES (2, 11, ?, 'a/two.png', 'MISSING');",
        (sid,),
    )
    conn.execute("INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (11, 2);")
    conn.execute(
        "INSERT INTO file(id, version_id, storage_id, relative_path, integrity_state) VALUES (3, 11, ?, 'a/three.png', 'OK');",
        (sid,),
    )
    conn.execute("INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (11, 3);")
    conn.execute(
        "INSERT INTO file(id, version_id, storage_id, relative_path, integrity_state) VALUES (4, 21, ?, 'b/one.png', 'OK');",
        (sid,),
    )
    conn.execute("INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (21, 4);")
    conn.commit()

    rows = list_assets_for_storage(conn, sid)
    assert [r.name for r in rows] == ["Alpha", "Beta"]

    alpha = rows[0]
    assert alpha.version_count == 2
    assert alpha.latest_version_label == "v02"
    assert alpha.file_count == 3
    assert alpha.missing_count == 1

    beta = rows[1]
    assert beta.version_count == 2
    assert beta.latest_version_label == "v02"
    assert beta.file_count == 1
    assert beta.missing_count == 0


def test_list_versions_and_files_deterministic(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path)

    conn.execute(
        "INSERT INTO storage(name, root_path, status) VALUES (?, ?, ?);",
        ("RootA", "/tmp/root_a", "OK"),
    )
    sid = int(conn.execute("SELECT id FROM storage WHERE name='RootA';").fetchone()[0])

    conn.execute(
        "INSERT INTO asset(id, storage_id, type, key, name) VALUES (1, ?, 'generic', 'K1', 'Alpha');",
        (sid,),
    )
    conn.execute(
        "INSERT INTO version(id, asset_id, label, sort_key, scheme) VALUES (11, 1, 'v02', 2, 'vNN');"
    )
    conn.execute(
        "INSERT INTO version(id, asset_id, label, sort_key, scheme) VALUES (10, 1, 'v01', 1, 'vNN');"
    )

    conn.execute(
        "INSERT INTO file(id, version_id, storage_id, relative_path, integrity_state) VALUES (2, 10, ?, 'z.png', 'OK');",
        (sid,),
    )
    conn.execute("INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (10, 2);")
    conn.execute(
        "INSERT INTO file(id, version_id, storage_id, relative_path, integrity_state) VALUES (1, 10, ?, 'a.png', 'OK');",
        (sid,),
    )
    conn.execute("INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (10, 1);")
    conn.commit()

    vers = list_versions(conn, asset_id=1)
    assert [v.label for v in vers] == ["v01", "v02"]  # ordered by sort_key

    files = list_files_for_version(conn, version_id=10)
    assert [f["relative_path"] for f in files] == ["a.png", "z.png"]
