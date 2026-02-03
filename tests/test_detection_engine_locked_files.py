import sqlite3

from assethub.core.db.schema import initialize_schema
from assethub.core.db.assets import create_asset
from assethub.core.db.file_bindings import bind_files_to_asset
from assethub.core.detection.engine import detect_proposals_for_storage
from assethub.core.detection.rules_loader import load_detection_ruleset, DetectionRuleset


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


def test_locked_files_inform_texture_set_without_being_candidates(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")

    # Create an existing asset so the binding has a valid target.
    a = create_asset(conn, storage_id=sid, type="texture_set", key="tex/Forest", name="Forest", commit=False)

    # Locked normal map contributes to the texture-set grouping signal.
    f_locked = _insert_file(conn, storage_id=sid, rel="tex/Forest_normal_v01.tif")
    bind_files_to_asset(conn, asset_id=int(a.id), file_ids=[f_locked])

    # Two unlocked channel files - below min_files on their own.
    f_a = _insert_file(conn, storage_id=sid, rel="tex/Forest_albedo_v01.tif")
    f_r = _insert_file(conn, storage_id=sid, rel="tex/Forest_roughness_v01.tif")
    conn.commit()

    base = load_detection_ruleset(data_root="")
    # Raise min_files to make the locked contribution decisive.
    rules = DetectionRuleset(
        excluded_exts=base.excluded_exts,
        image_sequence_separators=base.image_sequence_separators,
        image_sequence_min_digits=base.image_sequence_min_digits,
        texture_set_separators=base.texture_set_separators,
        texture_set_channel_tokens=base.texture_set_channel_tokens,
        texture_set_min_files=3,
        generic_group_by_stem=base.generic_group_by_stem,
    )

    res = detect_proposals_for_storage(conn, storage_id=sid, rules=rules)

    tex = [p for p in res.proposals if p.type == "texture_set" and p.key == "tex/Forest"]
    assert len(tex) == 1
    # Proposal includes only unlocked candidates; locked file is excluded.
    assert set(tex[0].file_ids) == {f_a, f_r}
    assert res.summary.skipped_locked == 1
