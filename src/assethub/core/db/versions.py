"""DB helpers for Version rows.

Stage 8 introduces artist-friendly versioning:
- Internal monotonic ordering via `sort_key`.
- User-facing label (default scheme vNN => v01, v02, ...).

This module is Qt-free and safe to import in tests.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional, Tuple

from assethub.core.model.asset import Asset
from assethub.core.model.version import Version


def set_version_user_label(
    conn: sqlite3.Connection, *, version_id: int, user_label: str, commit: bool = True
) -> None:
    """Set the optional user-facing label for a version."""

    vid = int(version_id)
    v = get_version(conn, vid)
    if v is None:
        raise ValueError("version not found")

    ulbl = str(user_label or "").strip()

    # IMPORTANT: keep DB writes + audit log in a single transaction.
    # If we insert into version_change_log without committing, the app can
    # leave an open write transaction and the next scan/health run will hit
    # "database is locked" until restart.
    if commit:
        with conn:
            conn.execute("UPDATE version SET user_label=? WHERE id=?;", (ulbl, vid))
            try:
                from assethub.core.db.version_membership import write_version_change_log

                write_version_change_log(
                    conn,
                    version_id=vid,
                    action_type="version_set_user_label",
                    summary=(
                        f"Set version user label: '{v.label}' → '{ulbl}'"
                        if ulbl
                        else f"Cleared version user label: '{v.label}'"
                    ),
                    payload={"user_label": ulbl},
                )
            except Exception:
                # Logging must never block the core operation.
                pass
    else:
        conn.execute("UPDATE version SET user_label=? WHERE id=?;", (ulbl, vid))


def set_version_discarded(
    conn: sqlite3.Connection, *, version_id: int, is_discarded: bool, commit: bool = True
) -> None:
    """Mark/unmark a version as discarded.

    Discarded versions remain in the DB but are typically hidden in the UI and
    ignored by missing-file reporting.
    """

    vid = int(version_id)
    v = get_version(conn, vid)
    if v is None:
        raise ValueError("version not found")

    flag = 1 if bool(is_discarded) else 0

    if commit:
        with conn:
            conn.execute("UPDATE version SET is_discarded=? WHERE id=?;", (flag, vid))
            try:
                from assethub.core.db.version_membership import write_version_change_log

                write_version_change_log(
                    conn,
                    version_id=vid,
                    action_type="version_set_discarded",
                    summary=(
                        f"Marked version discarded: {v.label}"
                        if flag
                        else f"Restored version: {v.label}"
                    ),
                    payload={"is_discarded": flag},
                )
            except Exception:
                pass
    else:
        conn.execute("UPDATE version SET is_discarded=? WHERE id=?;", (flag, vid))


def set_version_sort_key(
    conn: sqlite3.Connection, *, version_id: int, sort_key: int, commit: bool = True
) -> None:
    """Change a version's sort_key (used as the numeric vNN).

    This updates the vNN label when scheme=='vNN'.
    """

    vid = int(version_id)
    new_sk = int(sort_key)
    if new_sk <= 0:
        raise ValueError("sort_key must be positive")

    v = get_version(conn, vid)
    if v is None:
        raise ValueError("version not found")

    # Prevent collisions within the same asset.
    row = conn.execute(
        "SELECT id FROM version WHERE asset_id=? AND sort_key=? AND id<>? LIMIT 1;",
        (int(v.asset_id), new_sk, vid),
    ).fetchone()
    if row is not None:
        raise ValueError("Another version already uses that version number")

    new_label = v.label
    if str(v.scheme).strip() == "vNN":
        new_label = _label_for_scheme(new_sk, v.scheme)

    if commit:
        with conn:
            conn.execute(
                "UPDATE version SET sort_key=?, label=? WHERE id=?;",
                (new_sk, str(new_label), vid),
            )
            try:
                from assethub.core.db.version_membership import write_version_change_log

                write_version_change_log(
                    conn,
                    version_id=vid,
                    action_type="version_set_sort_key",
                    summary=f"Changed version number: {v.label} ({v.sort_key}) → {new_label} ({new_sk})",
                    payload={"old_sort_key": int(v.sort_key), "new_sort_key": int(new_sk)},
                )
            except Exception:
                pass
    else:
        conn.execute(
            "UPDATE version SET sort_key=?, label=? WHERE id=?;",
            (new_sk, str(new_label), vid),
        )


def _label_for_scheme(sort_key: int, scheme: str) -> str:
    """Generate a label given a scheme.

    v0 supports only the default scheme 'vNN'.
    """
    sk = int(sort_key)
    s = str(scheme).strip() or "vNN"
    if s != "vNN":
        # Future-safe fallback: treat unknown schemes like vNN.
        s = "vNN"
    # Minimum 2-digit padding; grows naturally past 99.
    return f"v{sk:02d}"


def create_version(
    conn: sqlite3.Connection,
    *,
    asset_id: int,
    sort_key_override: Optional[int] = None,
    label: Optional[str] = None,
    user_label: Optional[str] = None,
    scheme: str = "vNN",
    commit: bool = True,
) -> Version:
    """Create a new version for an asset.

    Chooses the next sort_key as (max+1) for the given asset.
    """

    aid = int(asset_id)
    if aid <= 0:
        raise ValueError("asset_id must be a positive integer")

    if sort_key_override is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_key), 0) FROM version WHERE asset_id=?;",
            (aid,),
        ).fetchone()
        next_sort = int(row[0] if row and row[0] is not None else 0) + 1
    else:
        next_sort = int(sort_key_override)
        if next_sort <= 0:
            raise ValueError("sort_key_override must be a positive integer")

    lbl = str(label).strip() if label is not None else ""
    if not lbl:
        lbl = _label_for_scheme(next_sort, scheme)

    ulbl = "" if user_label is None else str(user_label).strip()
    conn.execute(
        """
        INSERT INTO version(asset_id, label, sort_key, scheme, is_discarded, user_label)
        VALUES (?, ?, ?, ?, 0, ?);
        """,
        (aid, lbl, int(next_sort), str(scheme).strip() or "vNN", ulbl),
    )
    if commit:
        conn.commit()

    vid = conn.execute("SELECT last_insert_rowid();").fetchone()[0]
    return get_version(conn, int(vid))  # type: ignore[return-value]


def get_version(conn: sqlite3.Connection, version_id: int) -> Optional[Version]:
    """Fetch a Version by id."""
    row = conn.execute(
        """
        SELECT id, asset_id, label, sort_key, scheme, is_discarded, user_label, created_at, updated_at
        FROM version
        WHERE id=?
        LIMIT 1;
        """,
        (int(version_id),),
    ).fetchone()
    if row is None:
        return None
    return Version(
        id=int(row[0]),
        asset_id=int(row[1]),
        label=str(row[2]),
        sort_key=int(row[3]),
        scheme=str(row[4]),
        is_discarded=int(row[5] or 0),
        user_label=str(row[6] or ""),
        created_at=str(row[7]),
        updated_at=str(row[8]),
    )


def get_version_by_asset_sort_key(conn: sqlite3.Connection, *, asset_id: int, sort_key: int) -> Optional[Version]:
    """Fetch a Version by (asset_id, sort_key)."""
    row = conn.execute(
        """
        SELECT id
        FROM version
        WHERE asset_id=? AND sort_key=?
        LIMIT 1;
        """,
        (int(asset_id), int(sort_key)),
    ).fetchone()
    if row is None:
        return None
    return get_version(conn, int(row[0]))


def list_versions_for_asset(conn: sqlite3.Connection, asset_id: int) -> List[Version]:
    """List versions for an asset, ordered by sort_key."""
    rows = conn.execute(
        """
        SELECT id, asset_id, label, sort_key, scheme, is_discarded, user_label, created_at, updated_at
        FROM version
        WHERE asset_id=?
        ORDER BY sort_key;
        """,
        (int(asset_id),),
    ).fetchall()

    out: List[Version] = []
    for r in rows:
        out.append(
            Version(
                id=int(r[0]),
                asset_id=int(r[1]),
                label=str(r[2]),
                sort_key=int(r[3]),
                scheme=str(r[4]),
                is_discarded=int(r[5] or 0),
                user_label=str(r[6] or ""),
                created_at=str(r[7]),
                updated_at=str(r[8]),
            )
        )
    return out


def resolve_file_to_asset_version(
    conn: sqlite3.Connection, file_id: int
) -> Optional[Tuple[Asset, Version]]:
    """Resolve a file_id to (asset, version) via file.version_id.

    Returns None if the file has no assigned version.
    """

    row = conn.execute(
        """
        SELECT
            a.id, a.storage_id, a.type, a.key, a.name, a.slug, a.created_at, a.updated_at,
            v.id, v.asset_id, v.label, v.sort_key, v.scheme, v.is_discarded, v.user_label, v.created_at, v.updated_at
        FROM file f
        JOIN version v ON v.id = f.version_id
        JOIN asset a ON a.id = v.asset_id
        WHERE f.id=?
        LIMIT 1;
        """,
        (int(file_id),),
    ).fetchone()

    if row is None:
        return None

    asset = Asset(
        id=int(row[0]),
        storage_id=int(row[1]),
        type=str(row[2]),
        key=str(row[3]),
        name=str(row[4]),
        slug=None if row[5] is None else str(row[5]),
        created_at=str(row[6]),
        updated_at=str(row[7]),
    )
    version = Version(
        id=int(row[8]),
        asset_id=int(row[9]),
        label=str(row[10]),
        sort_key=int(row[11]),
        scheme=str(row[12]),
        is_discarded=int(row[13] or 0),
        user_label=str(row[14] or ""),
        created_at=str(row[15]),
        updated_at=str(row[16]),
    )
    return asset, version
