"""Helpers for version-up side effects triggered by manual bindings.

Stage 9.3.3 semantics (locked):
  - Manual binding is asset-level authority.
  - Any binding/unbinding that changes an asset's authoritative membership
    should create a new *non-discarded* version snapshot by default.

We keep this logic Qt-free so it can be tested directly.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from assethub.core.db.versions import create_version
from assethub.core.db.version_membership import (
    fork_version,
    remove_files_from_version,
    ensure_bound_files_in_version,
    write_version_change_log,
)


def get_latest_non_discarded_version_id(conn: sqlite3.Connection, *, asset_id: int) -> Optional[int]:
    """Return the latest non-discarded version id for an asset, or None."""
    aid = int(asset_id)
    if aid <= 0:
        raise ValueError("asset_id must be positive")
    row = conn.execute(
        """
        SELECT v.id
        FROM version v
        WHERE v.asset_id=? AND COALESCE(v.is_discarded,0)=0
        ORDER BY v.sort_key DESC, v.id DESC
        LIMIT 1;
        """,
        (aid,),
    ).fetchone()
    return None if row is None else int(row[0])


def _repoint_primary_version_pointers(conn: sqlite3.Connection, *, file_ids: Sequence[int], removed_from_version_id: int) -> None:
    """Best-effort repair for file.version_id after removing membership.

    We maintain file.version_id as a convenience pointer to the latest
    non-discarded version a file participates in.

    If we just removed a file from `removed_from_version_id` and the pointer
    referenced that version, pick the next best remaining membership.
    """
    vid = int(removed_from_version_id)
    ids = sorted({int(x) for x in file_ids if int(x) > 0})
    if not ids:
        return

    for fid in ids:
        row = conn.execute("SELECT version_id FROM file WHERE id=?;", (int(fid),)).fetchone()
        cur = None if row is None or row[0] is None else int(row[0])
        if cur is None or cur != vid:
            continue

        repl = conn.execute(
            """
            SELECT v.id
            FROM version_file vf
            JOIN version v ON v.id=vf.version_id
            WHERE vf.file_id=? AND COALESCE(v.is_discarded,0)=0
            ORDER BY v.sort_key DESC, v.id DESC
            LIMIT 1;
            """,
            (int(fid),),
        ).fetchone()
        new_ptr = None if repl is None else int(repl[0])
        conn.execute(
            "UPDATE file SET version_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?;",
            (new_ptr, int(fid)),
        )


@dataclass(frozen=True)
class BindingVersionUpResult:
    asset_id: int
    new_version_id: int
    summary: str


def version_up_for_binding_change(
    conn: sqlite3.Connection,
    *,
    asset_id: int,
    removed_file_ids: Optional[Iterable[int]] = None,
    note: Optional[str] = None,
) -> BindingVersionUpResult:
    """Create a new version snapshot for an asset after binding changes.

    Args:
        conn: SQLite connection.
        asset_id: Target asset.
        removed_file_ids: If provided, these file_ids are removed from the new
            snapshot after cloning. This supports rebinding/unbinding semantics.
        note: Optional note to include in the audit log.

    Returns:
        BindingVersionUpResult with the new version id.
    """
    aid = int(asset_id)
    if aid <= 0:
        raise ValueError("asset_id must be positive")

    rm_ids: List[int] = sorted({int(x) for x in (removed_file_ids or []) if int(x) > 0})
    latest = get_latest_non_discarded_version_id(conn, asset_id=aid)

    with conn:
        if latest is None:
            # No existing versions: create a fresh v01 and ensure current bound files exist.
            v = create_version(conn, asset_id=aid, commit=False)
            new_vid = int(v.id)
            ensure_bound_files_in_version(conn, asset_id=aid, version_id=new_vid)
            summary = f"Binding change: created initial version {v.label} for asset_id={aid}"
        else:
            fr = fork_version(conn, source_version_id=int(latest), include_missing=True)
            new_vid = int(fr.new_version_id)
            summary = fr.summary

        if rm_ids:
            remove_files_from_version(conn, version_id=int(new_vid), file_ids=rm_ids)
            _repoint_primary_version_pointers(conn, file_ids=rm_ids, removed_from_version_id=int(new_vid))
            # After removals, re-assert that currently bound files are present.
            ensure_bound_files_in_version(conn, asset_id=aid, version_id=int(new_vid))
            summary = summary + f"; removed {len(rm_ids)} file(s) due to binding change"

        if note:
            summary = summary + f" ({str(note).strip()})"

        # Emit an explicit audit entry so binding-induced version ups are explainable.
        try:
            write_version_change_log(
                conn,
                version_id=int(new_vid),
                action_type="binding_version_up",
                summary=summary,
                payload={
                    "asset_id": aid,
                    "removed_file_ids": rm_ids,
                    "source_version_id": int(latest) if latest is not None else None,
                },
            )
        except Exception:
            # Never block the main operation.
            pass

    return BindingVersionUpResult(asset_id=aid, new_version_id=int(new_vid), summary=str(summary))
