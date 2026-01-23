"""DB helpers for Tags and asset<->tag membership.

Stage 9.1 introduces semantic asset tags (name + color) with bulk assignment.
These helpers are Qt-free and designed to be small and testable.

Conventions:
- Tag uniqueness is enforced by tag.name (UNIQUE).
- Colors are stored as hex strings: '#RRGGBB'.
- Membership uses the join table asset_tag(asset_id, tag_id).
"""

from __future__ import annotations

import re
import sqlite3
from typing import Dict, List

from assethub.core.model.tag import Tag


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_tag_name(name: str) -> str:
    n = str(name or "").strip()
    if not n:
        raise ValueError("tag name must be non-empty")
    return n


def _validate_color(color: str) -> str:
    c = str(color or "").strip()
    if not _HEX_COLOR_RE.match(c):
        raise ValueError("color must be a hex string like '#RRGGBB'")
    return c.lower()


def list_tags(conn: sqlite3.Connection) -> List[Tag]:
    """Return all tags ordered by name."""
    rows = conn.execute(
        """
        SELECT id, name, color
        FROM tag
        ORDER BY lower(name), id;
        """
    ).fetchall()
    return [Tag(id=int(r[0]), name=str(r[1]), color=str(r[2])) for r in rows]


def create_tag(conn: sqlite3.Connection, *, name: str, color: str, commit: bool = True) -> Tag:
    """Create a tag and return it.

    Raises:
        ValueError: on empty name or invalid color.
    """
    n = _validate_tag_name(name)
    c = _validate_color(color)

    conn.execute("INSERT INTO tag(name, color) VALUES (?, ?);", (n, c))
    if commit:
        conn.commit()

    row = conn.execute(
        "SELECT id, name, color FROM tag WHERE name=? ORDER BY id DESC LIMIT 1;",
        (n,),
    ).fetchone()
    if row is None:
        raise RuntimeError("create_tag failed to create or locate tag")
    return Tag(id=int(row[0]), name=str(row[1]), color=str(row[2]))


def rename_tag(conn: sqlite3.Connection, *, tag_id: int, new_name: str, commit: bool = True) -> None:
    tid = int(tag_id)
    if tid <= 0:
        raise ValueError("tag_id must be a positive integer")
    n = _validate_tag_name(new_name)
    conn.execute("UPDATE tag SET name=? WHERE id=?;", (n, tid))
    if commit:
        conn.commit()


def set_tag_color(conn: sqlite3.Connection, *, tag_id: int, color: str, commit: bool = True) -> None:
    tid = int(tag_id)
    if tid <= 0:
        raise ValueError("tag_id must be a positive integer")
    c = _validate_color(color)
    conn.execute("UPDATE tag SET color=? WHERE id=?;", (c, tid))
    if commit:
        conn.commit()


def delete_tag(conn: sqlite3.Connection, *, tag_id: int, commit: bool = True) -> None:
    tid = int(tag_id)
    if tid <= 0:
        raise ValueError("tag_id must be a positive integer")
    conn.execute("DELETE FROM tag WHERE id=?;", (tid,))
    if commit:
        conn.commit()


def list_tags_for_asset_ids(conn: sqlite3.Connection, asset_ids: List[int]) -> Dict[int, List[Tag]]:
    """Return mapping of asset_id -> list[Tag] for the provided assets."""
    ids = [int(x) for x in (asset_ids or []) if int(x) > 0]
    if not ids:
        return {}

    placeholders = ",".join(["?"] * len(ids))
    rows = conn.execute(
        f"""
        SELECT at.asset_id, t.id, t.name, t.color
        FROM asset_tag at
        JOIN tag t ON t.id = at.tag_id
        WHERE at.asset_id IN ({placeholders})
        ORDER BY at.asset_id, lower(t.name), t.id;
        """,
        tuple(ids),
    ).fetchall()

    out: Dict[int, List[Tag]] = {int(aid): [] for aid in ids}
    for aid, tid, name, color in rows:
        out.setdefault(int(aid), []).append(Tag(id=int(tid), name=str(name), color=str(color)))
    return out


def add_tags_to_assets(
    conn: sqlite3.Connection,
    *,
    asset_ids: List[int],
    tag_ids: List[int],
    commit: bool = True,
) -> int:
    """Add tags to assets (idempotent).

    Returns:
        Best-effort count of newly inserted rows.
    """
    aids = [int(x) for x in (asset_ids or []) if int(x) > 0]
    tids = [int(x) for x in (tag_ids or []) if int(x) > 0]
    if not aids or not tids:
        return 0

    pairs = [(aid, tid) for aid in aids for tid in tids]
    conn.executemany(
        "INSERT OR IGNORE INTO asset_tag(asset_id, tag_id) VALUES (?, ?);",
        pairs,
    )
    # SQLite changes() returns rows changed by the most recent statement.
    inserted = int(conn.execute("SELECT changes();").fetchone()[0])
    if commit:
        conn.commit()
    return inserted


def remove_tags_from_assets(
    conn: sqlite3.Connection,
    *,
    asset_ids: List[int],
    tag_ids: List[int],
    commit: bool = True,
) -> int:
    """Remove tags from assets.

    Returns:
        Best-effort count of deleted rows.
    """
    aids = [int(x) for x in (asset_ids or []) if int(x) > 0]
    tids = [int(x) for x in (tag_ids or []) if int(x) > 0]
    if not aids or not tids:
        return 0

    a_ph = ",".join(["?"] * len(aids))
    t_ph = ",".join(["?"] * len(tids))
    conn.execute(
        f"DELETE FROM asset_tag WHERE asset_id IN ({a_ph}) AND tag_id IN ({t_ph});",
        tuple(aids + tids),
    )
    deleted = int(conn.execute("SELECT changes();").fetchone()[0])
    if commit:
        conn.commit()
    return deleted
