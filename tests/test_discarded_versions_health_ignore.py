import sqlite3


from assethub.core.db.connection import get_connection
from assethub.core.db.schema import initialize_schema
from assethub.core.db.assets import create_asset
from assethub.core.db.versions import create_version, set_version_discarded
from assethub.core.db.version_membership import attach_files_to_version
from assethub.core.db.file_records import fetch_missing_file_ids, purge_all_missing_file_records
from assethub.core.db.asset_library import list_assets


def test_discarded_versions_are_ignored_in_missing_lists(tmp_path) -> None:
    db_path = tmp_path / "assethub.sqlite3"
    conn = get_connection(str(db_path))
    initialize_schema(conn)

    # Minimal storage + one missing file under an asset version.
    conn.execute(
        "INSERT INTO storage(id, name, root_path, status) VALUES (1, 'RootA', '/tmp/rootA', 'OK');"
    )
    conn.execute(
        "INSERT INTO file(id, storage_id, relative_path, integrity_state, size_bytes, mtime_unix) "
        "VALUES (10, 1, 'tex/asset_albedo_v03.png', 'MISSING', 1, 1.0);"
    )

    a = create_asset(conn, storage_id=1, type="generic", key="asset", name="Asset")
    v = create_version(conn, asset_id=a.id, sort_key_override=3, commit=False)
    attach_files_to_version(conn, version_id=v.id, file_ids=[10])

    # Baseline: missing file appears.
    assert fetch_missing_file_ids(conn) == [10]

    # Discard the version: missing is ignored + purge does not delete the record.
    set_version_discarded(conn, version_id=v.id, is_discarded=True)

    assert fetch_missing_file_ids(conn) == []
    assert purge_all_missing_file_records(conn) == 0

    # Asset library should also ignore discarded-version missing counts.
    rows = list_assets(conn)
    assert len(rows) == 1
    assert rows[0].missing_count == 0
