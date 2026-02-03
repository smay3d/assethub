import sqlite3

import pytest

from assethub.core.db.schema import initialize_schema
from assethub.core.db.assets import create_asset
from assethub.core.db.versions import create_version
from assethub.core.db.version_membership import attach_files_to_version
from assethub.core.detection.apply import ApplyItem, apply_detection_proposals


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


def test_apply_creates_asset_version_and_attaches(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")
    f1 = _insert_file(conn, storage_id=sid, rel="textures/a.png")
    f2 = _insert_file(conn, storage_id=sid, rel="textures/b.png")
    f3 = _insert_file(conn, storage_id=sid, rel="textures/c.png")
    conn.commit()

    res = apply_detection_proposals(
        conn,
        storage_id=sid,
        items=[ApplyItem(type="generic", key="K1", name="Asset One", file_ids=[f1, f2])],
    )

    assert res.created_assets == 1
    assert res.created_versions == 1
    assert res.attached_files == 2

    row = conn.execute("SELECT id, storage_id, type, key, name FROM asset;").fetchone()
    assert row is not None
    assert int(row[1]) == sid
    assert row[2] == "generic"
    assert row[3] == "K1"
    assert row[4] == "Asset One"

    vrow = conn.execute("SELECT id, asset_id, label FROM version;").fetchone()
    assert vrow is not None
    vid = int(vrow[0])
    assert vrow[2] == "v01"

    # Membership: f1,f2 attached; f3 untouched.
    file_rows = conn.execute(
        "SELECT id, version_id FROM file ORDER BY id ASC;"
    ).fetchall()
    mapping = {int(r[0]): r[1] for r in file_rows}
    assert int(mapping[f1]) == vid
    assert int(mapping[f2]) == vid
    assert mapping[f3] is None

    log = conn.execute(
        "SELECT action_type FROM version_change_log WHERE version_id=?;",
        (vid,),
    ).fetchall()
    assert log and log[0][0] == "detect_apply"


def test_apply_skips_owned_and_rolls_back_on_missing(tmp_path) -> None:
    # Part A: owned files are skipped.
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")
    f1 = _insert_file(conn, storage_id=sid, rel="foo/a.txt")
    f2 = _insert_file(conn, storage_id=sid, rel="foo/b.txt")
    conn.commit()

    # Own f1 by an existing version.
    a0 = create_asset(conn, storage_id=sid, type="generic", key="OLD", name="Old", commit=False)
    v0 = create_version(conn, asset_id=int(a0.id), commit=False)
    attach_files_to_version(conn, version_id=int(v0.id), file_ids=[f1])

    res = apply_detection_proposals(
        conn,
        storage_id=sid,
        items=[ApplyItem(type="generic", key="NEW", name="New", file_ids=[f1, f2])],
    )
    assert res.attached_files == 1
    assert res.skipped_owned == 1

    # f1 remains on old version; f2 attached to new version.
    row_f1 = conn.execute("SELECT version_id FROM file WHERE id=?;", (f1,)).fetchone()
    row_f2 = conn.execute("SELECT version_id FROM file WHERE id=?;", (f2,)).fetchone()
    assert row_f1 is not None and int(row_f1[0]) == int(v0.id)
    assert row_f2 is not None and row_f2[0] is not None and int(row_f2[0]) != int(v0.id)

    # Part B: missing file ids roll back the entire apply.
    conn2 = sqlite3.connect(tmp_path / "assethub_test2.sqlite3")
    initialize_schema(conn2)
    sid2 = _insert_storage(conn2, name="RootB", root_path="/tmp/root_b")
    f_ok = _insert_file(conn2, storage_id=sid2, rel="ok.txt")
    conn2.commit()

    with pytest.raises(ValueError):
        apply_detection_proposals(
            conn2,
            storage_id=sid2,
            items=[
                ApplyItem(type="generic", key="K", name="A", file_ids=[f_ok]),
                ApplyItem(type="generic", key="BAD", name="B", file_ids=[999999]),
            ],
        )

    assert int(conn2.execute("SELECT COUNT(*) FROM asset;").fetchone()[0]) == 0
    assert int(conn2.execute("SELECT COUNT(*) FROM version;").fetchone()[0]) == 0
    assert int(conn2.execute("SELECT COUNT(*) FROM version_change_log;").fetchone()[0]) == 0
    assert conn2.execute("SELECT version_id FROM file WHERE id=?;", (f_ok,)).fetchone()[0] is None


def test_apply_version_up_merge_carries_forward_and_replaces_role(tmp_path) -> None:
    """Stage 9.2 Ext: version-up merge when a newer-version file is detected.

    We approximate "carry forward" by moving prior version membership to the new
    version *except* files whose basename role matches an incoming file (those are
    kept in the source version as history).
    """

    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")

    # Existing texture_set asset with version v04 and 5 members.
    a0 = create_asset(conn, storage_id=sid, type="texture_set", key="tex/Forest", name="Forest", commit=False)
    v4 = create_version(conn, asset_id=int(a0.id), sort_key_override=4, commit=False)

    f_alb = _insert_file(conn, storage_id=sid, rel="tex/Forest_albedo_v02.tif")
    f_ao = _insert_file(conn, storage_id=sid, rel="tex/Forest_ao_v02.tif")
    f_h = _insert_file(conn, storage_id=sid, rel="tex/Forest_height_v03.tif")
    f_r = _insert_file(conn, storage_id=sid, rel="tex/Forest_roughness_v02.tif")
    f_n4 = _insert_file(conn, storage_id=sid, rel="tex/Forest_normal_v04.tif")
    attach_files_to_version(conn, version_id=int(v4.id), file_ids=[f_alb, f_ao, f_h, f_r, f_n4])

    # New incoming normal map; unowned.
    f_n5 = _insert_file(conn, storage_id=sid, rel="tex/Forest_normal_v05.tif")
    conn.commit()

    res = apply_detection_proposals(
        conn,
        storage_id=sid,
        items=[
            ApplyItem(
                type="texture_set",
                key="tex/Forest",
                name="Forest",
                file_ids=[f_n5],
                desired_sort_key=5,
            )
        ],
    )

    assert res.created_assets == 0
    assert res.created_versions == 1
    assert res.attached_files == 1

    # v05 exists and includes all prior members except the replaced normal_v04.
    v5_id = conn.execute(
        "SELECT id FROM version WHERE asset_id=? AND sort_key=5;", (int(a0.id),)
    ).fetchone()[0]
    ids_v5 = {
        int(r[0])
        for r in conn.execute(
            "SELECT id FROM file WHERE version_id=? ORDER BY id ASC;", (int(v5_id),)
        ).fetchall()
    }
    assert f_n5 in ids_v5
    assert f_alb in ids_v5
    assert f_ao in ids_v5
    assert f_h in ids_v5
    assert f_r in ids_v5
    assert f_n4 not in ids_v5

    # Source version keeps the replaced normal_v04 for history.
    ids_v4 = {
        int(r[0])
        for r in conn.execute(
            "SELECT id FROM file WHERE version_id=? ORDER BY id ASC;", (int(v4.id),)
        ).fetchall()
    }
    assert ids_v4 == {f_n4}

    # A log entry is recorded on the new version.
    row = conn.execute(
        "SELECT action_type FROM version_change_log WHERE version_id=? ORDER BY id DESC LIMIT 1;",
        (int(v5_id),),
    ).fetchone()
    assert row is not None and row[0] in ("version_up_merge", "detect_apply")



def test_apply_version_up_merge_bases_on_latest_non_discarded(tmp_path) -> None:
    """Stage 9.2.5+: composite version-up bases strictly on latest non-discarded.

    The latest non-discarded version is the authoritative snapshot base. We do *not*
    reconstruct a synthetic snapshot from older versions.
    """

    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")

    a0 = create_asset(conn, storage_id=sid, type="texture_set", key="tex/Forest", name="Forest", commit=False)

    # v03 contains most files (legacy history).
    v3 = create_version(conn, asset_id=int(a0.id), sort_key_override=3, commit=False)
    f_alb = _insert_file(conn, storage_id=sid, rel="tex/Forest_albedo_v02.tif")
    f_ao = _insert_file(conn, storage_id=sid, rel="tex/Forest_ao_v02.tif")
    f_h = _insert_file(conn, storage_id=sid, rel="tex/Forest_height_v03.tif")
    f_r = _insert_file(conn, storage_id=sid, rel="tex/Forest_roughness_v02.tif")
    attach_files_to_version(conn, version_id=int(v3.id), file_ids=[f_alb, f_ao, f_h, f_r])

    # v04 is the latest non-discarded base but contains only normal_v04.
    v4 = create_version(conn, asset_id=int(a0.id), sort_key_override=4, commit=False)
    f_n4 = _insert_file(conn, storage_id=sid, rel="tex/Forest_normal_v04.tif")
    attach_files_to_version(conn, version_id=int(v4.id), file_ids=[f_n4])

    # Incoming updated normal.
    f_n5 = _insert_file(conn, storage_id=sid, rel="tex/Forest_normal_v05.tif")
    conn.commit()

    res = apply_detection_proposals(
        conn,
        storage_id=sid,
        items=[
            ApplyItem(
                type="texture_set",
                key="tex/Forest",
                name="Forest",
                file_ids=[f_n5],
                desired_sort_key=5,
            )
        ],
    )

    assert res.created_assets == 0
    assert res.created_versions == 1
    assert res.attached_files == 1

    v5_id = conn.execute(
        "SELECT id FROM version WHERE asset_id=? AND sort_key=5;", (int(a0.id),)
    ).fetchone()[0]

    # Base is v04 only, so v05 should carry forward from v04 and then override.
    ids_v5 = {int(r[0]) for r in conn.execute("SELECT id FROM file WHERE version_id=?;", (int(v5_id),)).fetchall()}
    assert ids_v5 == {f_n5}

    # Replaced normal stays in v04.
    ids_v4 = {int(r[0]) for r in conn.execute("SELECT id FROM file WHERE version_id=?;", (int(v4.id),)).fetchall()}
    assert ids_v4 == {f_n4}

    # Older versions remain untouched; `file.version_id` is a convenience pointer.
