import sqlite3

from assethub.core.db.schema import initialize_schema
from assethub.core.db.assets import create_asset
from assethub.core.detection.engine import detect_proposals_for_storage
from assethub.core.detection.rules_loader import load_detection_ruleset


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


def test_detect_partial_texture_set_proposal_when_asset_exists(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "assethub_test.sqlite3")
    initialize_schema(conn)

    sid = _insert_storage(conn, name="RootA", root_path="/tmp/root_a")

    # Existing texture_set asset keyed by directory/base.
    create_asset(conn, storage_id=sid, type="texture_set", key="tex/Forest", name="Forest", commit=False)

    # Single updated channel file; does not satisfy min_files, but should still
    # be proposed as texture_set because the asset exists.
    _insert_file(conn, storage_id=sid, rel="tex/Forest_normal_v05.tif")
    conn.commit()

    rules = load_detection_ruleset(data_root="", rules_root="")
    res = detect_proposals_for_storage(conn, storage_id=sid, rules=rules)

    # Expect at least one texture_set proposal with the exact key.
    keys = {(p.type, p.key) for p in res.proposals}
    assert ("texture_set", "tex/Forest") in keys
