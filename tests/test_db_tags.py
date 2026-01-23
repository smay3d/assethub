# tests/test_db_tags.py

from __future__ import annotations

import sqlite3

import pytest

from assethub.core.db.schema import initialize_schema
from assethub.core.db.tags import (
    add_tags_to_assets,
    create_tag,
    delete_tag,
    list_tags,
    list_tags_for_asset_ids,
    rename_tag,
    remove_tags_from_assets,
    set_tag_color,
)


def test_tag_crud_and_membership(tmp_path) -> None:
    db_path = tmp_path / "assethub_test.sqlite3"
    conn = sqlite3.connect(db_path)
    initialize_schema(conn)

    t1 = create_tag(conn, name="Final", color="#ff0000")
    t2 = create_tag(conn, name="WIP", color="#00ff00")
    assert t1.id > 0 and t2.id > 0

    tags = list_tags(conn)
    assert [t.name for t in tags] == ["Final", "WIP"]

    rename_tag(conn, tag_id=t2.id, new_name="Progress")
    set_tag_color(conn, tag_id=t2.id, color="#0000ff")

    tags2 = {t.id: t for t in list_tags(conn)}
    assert tags2[t2.id].name == "Progress"
    assert tags2[t2.id].color == "#0000ff"

    # Storage row required for asset foreign key.
    conn.execute(
        "INSERT INTO storage(name, display_name, root_path, status) VALUES (?, ?, ?, ?);",
        ("Unmanaged", None, None, "OK"),
    )
    storage_id = int(conn.execute("SELECT id FROM storage WHERE name='Unmanaged' LIMIT 1;").fetchone()[0])

    # Seed a minimal asset row for membership tests.
    conn.execute(
        "INSERT INTO asset(storage_id, type, key, name) VALUES (?, 'generic', 'a', 'A');",
        (storage_id,),
    )
    conn.execute(
        "INSERT INTO asset(storage_id, type, key, name) VALUES (?, 'generic', 'b', 'B');",
        (storage_id,),
    )
    a1 = int(conn.execute("SELECT id FROM asset WHERE key='a';").fetchone()[0])
    a2 = int(conn.execute("SELECT id FROM asset WHERE key='b';").fetchone()[0])
    conn.commit()

    inserted = add_tags_to_assets(conn, asset_ids=[a1, a2], tag_ids=[t1.id, t2.id])
    assert inserted >= 1

    m = list_tags_for_asset_ids(conn, [a1, a2])
    assert {t.name for t in m[a1]} == {"Final", "Progress"}
    assert {t.name for t in m[a2]} == {"Final", "Progress"}

    removed = remove_tags_from_assets(conn, asset_ids=[a1], tag_ids=[t1.id])
    assert removed >= 1
    m2 = list_tags_for_asset_ids(conn, [a1, a2])
    assert {t.name for t in m2[a1]} == {"Progress"}
    assert {t.name for t in m2[a2]} == {"Final", "Progress"}

    # Deleting a tag should cascade membership.
    delete_tag(conn, tag_id=t1.id)
    m3 = list_tags_for_asset_ids(conn, [a2])
    assert {t.name for t in m3[a2]} == {"Progress"}


def test_tag_color_validation(tmp_path) -> None:
    db_path = tmp_path / "assethub_test.sqlite3"
    conn = sqlite3.connect(db_path)
    initialize_schema(conn)

    with pytest.raises(ValueError):
        create_tag(conn, name="Bad", color="red")
