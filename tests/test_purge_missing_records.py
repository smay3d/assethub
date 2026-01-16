from __future__ import annotations

import sqlite3


def test_purge_all_missing_file_records(tmp_path) -> None:
    """Stage 7.5.4: bulk cleanup should delete only MISSING rows."""

    from assethub.core.db.schema import initialize_schema
    from assethub.core.storage.roots import StorageManager
    from assethub.core.db.file_records import purge_all_missing_file_records

    conn = sqlite3.connect(tmp_path / "db.sqlite3")
    try:
        initialize_schema(conn)
        sm = StorageManager(conn)
        unmanaged = sm.ensure_unmanaged_storage()

        # Seed a mix of OK and MISSING file records.
        conn.execute(
            "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (?, ?, ?);",
            (int(unmanaged.id), "ok_a.txt", "OK"),
        )
        conn.execute(
            "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (?, ?, ?);",
            (int(unmanaged.id), "missing_a.txt", "MISSING"),
        )
        conn.execute(
            "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (?, ?, ?);",
            (int(unmanaged.id), "missing_b.txt", "MISSING"),
        )
        conn.commit()

        deleted = purge_all_missing_file_records(conn)
        assert deleted == 2

        # Ensure only the OK row remains.
        rows = conn.execute("SELECT relative_path, integrity_state FROM file ORDER BY relative_path;").fetchall()
        assert rows == [("ok_a.txt", "OK")]
    finally:
        conn.close()
