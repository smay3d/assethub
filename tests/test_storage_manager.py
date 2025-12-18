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
