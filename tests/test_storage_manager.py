# tests/test_storage_manager.py

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from assethub.core.db.schema import initialize_schema
from assethub.core.storage.roots import StorageManager


def test_unmanaged_storage_is_singleton(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "db.sqlite3")
    initialize_schema(conn)

    sm = StorageManager(conn)
    u1 = sm.ensure_unmanaged_storage()
    u2 = sm.ensure_unmanaged_storage()

    assert u1.id == u2.id
    assert u1.root_path is None
    assert u1.name == "Unmanaged"
    assert u1.status == "UNMANAGED"

    # Force a duplicate unmanaged row (NULL root_path allows this)
    conn.execute("INSERT INTO storage(name, root_path, status) VALUES ('Oops', NULL, 'OK');")
    conn.commit()

    u3 = sm.ensure_unmanaged_storage()
    # Should collapse back to a single unmanaged row with the original id
    assert u3.id == u1.id

    rows = conn.execute("SELECT COUNT(*) FROM storage WHERE root_path IS NULL;").fetchone()
    assert rows is not None
    assert rows[0] == 1


def test_register_root_and_resolve(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "db.sqlite3")
    initialize_schema(conn)

    sm = StorageManager(conn)
    sm.ensure_unmanaged_storage()

    root_a = tmp_path / "RootA"
    root_b = root_a / "NestedB"
    root_a.mkdir()
    root_b.mkdir(parents=True, exist_ok=True)

    f1 = root_a / "file1.txt"
    f2 = root_b / "file2.txt"
    f1.write_text("a")
    f2.write_text("b")

    ra = sm.register_root(str(root_a), name="A")
    rb = sm.register_root(str(root_b), name="B")

    # Path under nested root should match the longest root prefix (B)
    stor, rel = sm.resolve_storage_for_path(str(f2))
    assert stor.id == rb.id
    assert rel.replace('\\', '/').endswith("file2.txt")

    # Path under root_a but not under nested root should map to A
    stor2, rel2 = sm.resolve_storage_for_path(str(f1))
    assert stor2.id == ra.id
    assert rel2.replace('\\', '/').endswith("file1.txt")

    # Outside any registered root -> unmanaged
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    stor3, rel3 = sm.resolve_storage_for_path(str(outside))
    assert stor3.root_path is None
    assert "outside" in rel3


def test_remove_root_from_tracking_cascade(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "db.sqlite3")
    initialize_schema(conn)

    sm = StorageManager(conn)
    unmanaged = sm.ensure_unmanaged_storage()

    root = tmp_path / "RootX"
    root.mkdir()
    r = sm.register_root(str(root), name="RootX")

    # Seed tracked file rows.
    conn.executemany(
        "INSERT INTO file(storage_id, relative_path, integrity_state) VALUES (?, ?, 'OK');",
        [
            (int(r.id), "a.txt"),
            (int(r.id), "b.txt"),
            (int(r.id), "sub/c.txt"),
        ],
    )
    conn.commit()

    assert sm.count_files_for_storage(int(r.id)) == 3

    removed = sm.remove_root_from_tracking(int(r.id))
    assert removed == 3

    # Storage row removed.
    row = conn.execute("SELECT COUNT(*) FROM storage WHERE id = ?;", (int(r.id),)).fetchone()
    assert row is not None
    assert int(row[0]) == 0

    # File rows removed.
    row2 = conn.execute("SELECT COUNT(*) FROM file WHERE storage_id = ?;", (int(r.id),)).fetchone()
    assert row2 is not None
    assert int(row2[0]) == 0

    # Unmanaged remains intact.
    row3 = conn.execute("SELECT COUNT(*) FROM storage WHERE id = ?;", (int(unmanaged.id),)).fetchone()
    assert row3 is not None
    assert int(row3[0]) == 1


def test_remove_root_from_tracking_disallows_unmanaged(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "db.sqlite3")
    initialize_schema(conn)

    sm = StorageManager(conn)
    unmanaged = sm.ensure_unmanaged_storage()

    try:
        sm.remove_root_from_tracking(int(unmanaged.id))
        assert False, "Expected ValueError"
    except ValueError:
        pass
