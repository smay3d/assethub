"""DB helpers for version membership operations.

Schema v6 introduces `version_file` which allows a file to belong to multiple
versions (true snapshots). We keep `file.version_id` as a *convenience pointer*
to a "primary" version for legacy UI views, but **membership truth** is stored
in `version_file`.

This module provides transactional, Qt-free operations to modify membership and
record per-action history entries in `version_change_log`.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


def _ph(n: int) -> str:
    """Return a comma-separated placeholder list for SQLite IN clauses."""
    if n <= 0:
        raise ValueError("placeholder count must be positive")
    return ",".join(["?"] * n)


def _norm_ids(ids: Iterable[int]) -> List[int]:
    """Normalize to a unique, ordered list of positive ints."""
    out: List[int] = []
    seen: Set[int] = set()
    for v in ids:
        i = int(v)
        if i <= 0:
            continue
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
    return out


def _json_compact(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _get_version_row(conn: sqlite3.Connection, version_id: int) -> Optional[Tuple[int, int, str]]:
    row = conn.execute(
        "SELECT id, asset_id, scheme FROM version WHERE id=? LIMIT 1;",
        (int(version_id),),
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), int(row[1]), str(row[2])


def _label_for_scheme(sort_key: int, scheme: str) -> str:
    """Generate a label given a scheme.

    v0 supports only the default scheme 'vNN'. Unknown schemes fall back to vNN.
    """
    sk = int(sort_key)
    s = str(scheme).strip() or "vNN"
    if s != "vNN":
        s = "vNN"
    return f"v{sk:02d}"


def write_version_change_log(
    conn: sqlite3.Connection,
    *,
    version_id: int,
    action_type: str,
    summary: str,
    payload: Dict[str, Any],
) -> int:
    """Insert a row into version_change_log and return its id."""
    vid = int(version_id)
    if vid <= 0:
        raise ValueError("version_id must be a positive integer")
    at = str(action_type).strip()
    if not at:
        raise ValueError("action_type must be non-empty")
    s = str(summary).strip()
    if not s:
        raise ValueError("summary must be non-empty")

    pj = _json_compact(payload)
    conn.execute(
        """
        INSERT INTO version_change_log(version_id, action_type, summary, payload_json)
        VALUES (?, ?, ?, ?);
        """,
        (vid, at, s, pj),
    )
    row = conn.execute("SELECT last_insert_rowid();").fetchone()
    return int(row[0])


def _touch_versions(conn: sqlite3.Connection, version_ids: Sequence[int]) -> None:
    vids = _norm_ids(version_ids)
    if not vids:
        return
    conn.execute(
        f"UPDATE version SET updated_at=CURRENT_TIMESTAMP WHERE id IN ({_ph(len(vids))});",
        tuple(vids),
    )


def _fetch_files(
    conn: sqlite3.Connection, file_ids: Sequence[int]
) -> Dict[int, Tuple[Optional[int], str, Optional[int]]]:
    """Return mapping file_id -> (version_id, integrity_state, size_bytes)."""
    ids = _norm_ids(file_ids)
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT id, version_id, integrity_state, size_bytes FROM file WHERE id IN ({_ph(len(ids))});",
        tuple(ids),
    ).fetchall()
    out: Dict[int, Tuple[Optional[int], str, Optional[int]]] = {}
    for r in rows:
        fid = int(r[0])
        vid = None if r[1] is None else int(r[1])
        integrity = str(r[2])
        size = None if r[3] is None else int(r[3])
        out[fid] = (vid, integrity, size)
    return out


def _fetch_memberships(conn: sqlite3.Connection, file_ids: Sequence[int]) -> Dict[int, Set[int]]:
    """Return mapping file_id -> set(version_id) using version_file."""
    ids = _norm_ids(file_ids)
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT file_id, version_id FROM version_file WHERE file_id IN ({_ph(len(ids))});",
        tuple(ids),
    ).fetchall()
    out: Dict[int, Set[int]] = {int(fid): set() for fid in ids}
    for r in rows:
        fid = int(r[0])
        vid = int(r[1])
        out.setdefault(fid, set()).add(vid)
    # prune empties for callers that want "no memberships" to be missing
    return {k: v for k, v in out.items() if v}


def get_file_ids_for_version(conn: sqlite3.Connection, version_id: int) -> List[int]:
    """Return file_ids that are members of a version (via version_file)."""
    vid = int(version_id)
    if vid <= 0:
        raise ValueError("version_id must be positive")
    rows = conn.execute(
        "SELECT file_id FROM version_file WHERE version_id=? ORDER BY file_id ASC;",
        (vid,),
    ).fetchall()
    return [int(r[0]) for r in rows]


def add_files_to_version(
    conn: sqlite3.Connection,
    *,
    version_id: int,
    file_ids: Sequence[int],
    ignore_duplicates: bool = True,
) -> int:
    """Add membership rows to version_file. Returns number of attempted inserts."""
    vid = int(version_id)
    ids = _norm_ids(file_ids)
    if vid <= 0:
        raise ValueError("version_id must be positive")
    if not ids:
        return 0
    sql = "INSERT INTO version_file(version_id, file_id) VALUES (?, ?);"
    if ignore_duplicates:
        sql = "INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (?, ?);"
    conn.executemany(sql, [(vid, int(fid)) for fid in ids])
    return len(ids)


def remove_files_from_version(conn: sqlite3.Connection, *, version_id: int, file_ids: Sequence[int]) -> int:
    """Remove membership rows from version_file. Returns number of affected file_ids."""
    vid = int(version_id)
    ids = _norm_ids(file_ids)
    if vid <= 0:
        raise ValueError("version_id must be positive")
    if not ids:
        return 0
    conn.execute(
        f"DELETE FROM version_file WHERE version_id=? AND file_id IN ({_ph(len(ids))});",
        (vid, *ids),
    )
    return len(ids)


def clone_version_membership(conn: sqlite3.Connection, *, src_version_id: int, dst_version_id: int) -> int:
    """Clone all membership from src to dst using INSERT OR IGNORE."""
    src = int(src_version_id)
    dst = int(dst_version_id)
    if src <= 0 or dst <= 0:
        raise ValueError("src_version_id and dst_version_id must be positive")
    conn.execute(
        """
        INSERT OR IGNORE INTO version_file(version_id, file_id)
        SELECT ?, file_id
        FROM version_file
        WHERE version_id=?;
        """,
        (dst, src),
    )
    # rowcount is not reliable for executescript/insert-select; return best-effort.
    return 0


@dataclass(frozen=True)
class AttachResult:
    attached: int
    skipped_owned: int
    skipped_already_attached: int
    missing_file_rows: int
    summary: str
    log_id: int


def attach_files_to_version(
    conn: sqlite3.Connection,
    *,
    version_id: int,
    file_ids: Sequence[int],
    enforce_unowned: bool = False,
    use_transaction: bool = True,
    write_log: bool = True,
    action_type: str = "attach",
    payload_extra: Optional[Dict[str, Any]] = None,
) -> AttachResult:
    """Attach files to a version.

    If enforce_unowned=True, only unowned (version_id IS NULL) files are attached.
    Otherwise, files owned by other versions will be reassigned to the target.
    """

    vid = int(version_id)
    ids = _norm_ids(file_ids)
    if vid <= 0:
        raise ValueError("version_id must be a positive integer")
    if not ids:
        raise ValueError("file_ids must be non-empty")

    if _get_version_row(conn, vid) is None:
        raise ValueError(f"version_id {vid} does not exist")

    files = _fetch_files(conn, ids)
    missing = len(ids) - len(files)

    memberships = _fetch_memberships(conn, ids)

    to_attach: List[int] = []
    skipped_owned = 0
    skipped_already = 0
    notes: List[str] = []

    for fid in ids:
        if fid not in files:
            continue

        cur_members = memberships.get(int(fid), set())
        if vid in cur_members:
            skipped_already += 1
            continue

        # Enforce "unowned" means: no membership in *any* version.
        if enforce_unowned and cur_members:
            skipped_owned += 1
            continue

        to_attach.append(int(fid))

    log_id = 0
    summary = ""

    def _apply() -> None:
        nonlocal log_id, summary
        if to_attach:
            # Membership truth.
            conn.executemany(
                "INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (?, ?);",
                [(vid, int(fid)) for fid in to_attach],
            )

            # Convenience pointer: promote file.version_id to this version if it's NULL
            # or points to an older sort_key.
            row_sk = conn.execute("SELECT sort_key FROM version WHERE id=? LIMIT 1;", (vid,)).fetchone()
            target_sk = int(row_sk[0]) if row_sk else 0
            if target_sk > 0:
                conn.execute(
                    f"""
                    UPDATE file
                    SET version_id=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id IN ({_ph(len(to_attach))})
                      AND (
                        version_id IS NULL OR
                        COALESCE((SELECT sort_key FROM version WHERE id=file.version_id), -1) < ?
                      );
                    """,
                    (vid, *to_attach, int(target_sk)),
                )

            _touch_versions(conn, [vid])

        payload: Dict[str, Any] = {
            "added_file_ids": to_attach,
            "missing_file_rows": missing,
            "skipped_already_attached": skipped_already,
            "skipped_owned": skipped_owned,
        }
        if notes:
            payload["notes"] = notes
        if payload_extra:
            payload.update(payload_extra)

        suffix_bits: List[str] = []
        if skipped_owned:
            suffix_bits.append(f"skipped {skipped_owned} owned")
        if skipped_already:
            suffix_bits.append(f"skipped {skipped_already} already")

        suffix = ""
        if suffix_bits:
            suffix = " (" + ", ".join(suffix_bits) + ")"
        summary = f"Attached {len(to_attach)} files → version {vid}{suffix}"

        if write_log:
            at = str(action_type).strip() or "attach"
            log_id = write_version_change_log(
                conn,
                version_id=vid,
                action_type=at,
                summary=summary,
                payload=payload,
            )

    if use_transaction:
        with conn:
            _apply()
    else:
        _apply()

    return AttachResult(
        attached=len(to_attach),
        skipped_owned=skipped_owned,
        skipped_already_attached=skipped_already,
        missing_file_rows=missing,
        summary=summary,
        log_id=log_id,
    )


@dataclass(frozen=True)
class DetachResult:
    detached: int
    skipped_not_attached: int
    missing_file_rows: int
    summary: str
    log_ids: List[int]


def detach_files(
    conn: sqlite3.Connection,
    *,
    file_ids: Sequence[int],
    only_from_version_id: Optional[int] = None,
) -> DetachResult:
    """Detach files from version membership.

    Detaches by deleting rows in `version_file`.

    Notes:
        - If only_from_version_id is provided, we detach only that membership.
        - Otherwise, we detach from the file's current *primary* version (file.version_id).
        - file.version_id is updated to a best-effort remaining membership (latest sort_key)
          or NULL if no memberships remain.
    """

    ids = _norm_ids(file_ids)
    if not ids:
        raise ValueError("file_ids must be non-empty")

    only_vid = None if only_from_version_id is None else int(only_from_version_id)
    if only_vid is not None and only_vid <= 0:
        raise ValueError("only_from_version_id must be a positive integer")

    files = _fetch_files(conn, ids)
    missing = len(ids) - len(files)

    # Decide detach targets per file.
    to_detach_pairs: List[Tuple[int, int]] = []  # (file_id, version_id)
    skipped = 0
    removed_by_version: Dict[int, List[int]] = {}

    for fid in ids:
        row = files.get(fid)
        if row is None:
            continue
        cur_vid, _integrity, _size = row
        if only_vid is not None:
            if cur_vid is None or int(cur_vid) != int(only_vid):
                skipped += 1
                continue
            to_detach_pairs.append((int(fid), int(only_vid)))
            removed_by_version.setdefault(int(only_vid), []).append(int(fid))
        else:
            if cur_vid is None:
                skipped += 1
                continue
            to_detach_pairs.append((int(fid), int(cur_vid)))
            removed_by_version.setdefault(int(cur_vid), []).append(int(fid))

    log_ids: List[int] = []
    with conn:
        if to_detach_pairs:
            # Remove membership rows.
            conn.executemany(
                "DELETE FROM version_file WHERE version_id=? AND file_id=?;",
                [(int(v), int(f)) for f, v in to_detach_pairs],
            )

            # Update convenience pointer for files whose primary points to the removed version.
            affected_files = sorted({int(f) for f, _v in to_detach_pairs})
            for fid in affected_files:
                cur_ptr = conn.execute("SELECT version_id FROM file WHERE id=?;", (int(fid),)).fetchone()
                cur_ptr_vid = None if not cur_ptr or cur_ptr[0] is None else int(cur_ptr[0])
                if cur_ptr_vid is None:
                    continue

                # If we removed the membership that the pointer referenced, choose a replacement.
                removed_versions_for_file = {int(v) for f, v in to_detach_pairs if int(f) == int(fid)}
                if cur_ptr_vid not in removed_versions_for_file:
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

            _touch_versions(conn, list(removed_by_version.keys()))

        suffix = ""
        if skipped:
            suffix = f" ({skipped} were not attached)"
        summary = f"Detached {len(to_detach_pairs)} files{suffix}"

        # One log row per impacted version.
        for v_id, removed_ids in sorted(removed_by_version.items()):
            payload = {
                "removed_file_ids": removed_ids,
                "missing_file_rows": missing,
                "skipped_not_attached": skipped,
            }
            log_ids.append(
                write_version_change_log(
                    conn,
                    version_id=int(v_id),
                    action_type="detach",
                    summary=summary,
                    payload=payload,
                )
            )

    return DetachResult(
        detached=len(to_detach_pairs),
        skipped_not_attached=skipped,
        missing_file_rows=missing,
        summary=summary,
        log_ids=log_ids,
    )


@dataclass(frozen=True)
class RepairResult:
    removed_old: bool
    added_new: bool
    summary: str
    log_id: int


def repair_version_membership(
    conn: sqlite3.Connection,
    *,
    version_id: int,
    old_file_id: int,
    new_file_id: int,
    enforce_unowned: bool = False,
) -> RepairResult:
    """Replace one file in a version with another."""

    vid = int(version_id)
    old_id = int(old_file_id)
    new_id = int(new_file_id)
    if vid <= 0:
        raise ValueError("version_id must be a positive integer")
    if old_id <= 0 or new_id <= 0:
        raise ValueError("file ids must be positive integers")
    if old_id == new_id:
        raise ValueError("old_file_id and new_file_id must differ")

    if _get_version_row(conn, vid) is None:
        raise ValueError(f"version_id {vid} does not exist")

    files = _fetch_files(conn, [old_id, new_id])
    if old_id not in files:
        raise ValueError(f"old_file_id {old_id} does not exist")
    if new_id not in files:
        raise ValueError(f"new_file_id {new_id} does not exist")

    old_vid, old_integrity, old_size = files[old_id]
    new_vid, _new_integrity, new_size = files[new_id]

    notes: List[str] = []
    if str(old_integrity) != "MISSING":
        notes.append(f"old record integrity_state={old_integrity}")
    if old_size is not None and new_size is not None and int(old_size) != int(new_size):
        notes.append(f"size mismatch old={old_size} new={new_size}")
    elif old_size is None or new_size is None:
        notes.append("size data missing")

    # Enforce unowned for the new file if requested (no memberships in any version).
    if enforce_unowned:
        mem = _fetch_memberships(conn, [new_id]).get(new_id, set())
        if mem and (vid not in mem):
            raise ValueError("new_file_id is already owned by another version")

    removed_old = False
    added_new = False

    with conn:
        # Remove the old membership from this version.
        existed_old = conn.execute(
            "SELECT 1 FROM version_file WHERE version_id=? AND file_id=? LIMIT 1;",
            (vid, old_id),
        ).fetchone()
        if existed_old is not None:
            conn.execute("DELETE FROM version_file WHERE version_id=? AND file_id=?;", (vid, old_id))
            removed_old = True
        else:
            notes.append("old file was not attached to target version")

        # Add the new membership.
        existed_new = conn.execute(
            "SELECT 1 FROM version_file WHERE version_id=? AND file_id=? LIMIT 1;",
            (vid, new_id),
        ).fetchone()
        if existed_new is None:
            conn.execute("INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (?, ?);", (vid, new_id))
            added_new = True

        # Convenience pointer updates.
        row_sk = conn.execute("SELECT sort_key FROM version WHERE id=? LIMIT 1;", (vid,)).fetchone()
        target_sk = int(row_sk[0]) if row_sk else 0
        if target_sk > 0:
            conn.execute(
                """
                UPDATE file
                SET version_id=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                  AND (
                    version_id IS NULL OR
                    COALESCE((SELECT sort_key FROM version WHERE id=file.version_id), -1) < ?
                  );
                """,
                (vid, new_id, int(target_sk)),
            )

        # If the old file pointer referenced this version and we removed it, pick a replacement.
        cur_ptr = conn.execute("SELECT version_id FROM file WHERE id=?;", (old_id,)).fetchone()
        cur_ptr_vid = None if not cur_ptr or cur_ptr[0] is None else int(cur_ptr[0])
        if removed_old and cur_ptr_vid == vid:
            repl = conn.execute(
                """
                SELECT v.id
                FROM version_file vf
                JOIN version v ON v.id=vf.version_id
                WHERE vf.file_id=? AND COALESCE(v.is_discarded,0)=0
                ORDER BY v.sort_key DESC, v.id DESC
                LIMIT 1;
                """,
                (old_id,),
            ).fetchone()
            new_ptr = None if repl is None else int(repl[0])
            conn.execute(
                "UPDATE file SET version_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?;",
                (new_ptr, old_id),
            )

        _touch_versions(conn, [vid])

        payload: Dict[str, Any] = {
            "added_file_ids": [new_id] if added_new else [],
            "removed_file_ids": [old_id] if removed_old else [],
            "replaced": [
                {
                    "old": old_id,
                    "new": new_id,
                    "notes": notes,
                }
            ],
        }
        note_str = "; ".join(notes) if notes else ""
        extra = f" ({note_str})" if note_str else ""
        summary = f"Repaired version {vid}: replaced file {old_id} → {new_id}{extra}"

        log_id = write_version_change_log(
            conn,
            version_id=vid,
            action_type="repair",
            summary=summary,
            payload=payload,
        )

    return RepairResult(removed_old=removed_old, added_new=added_new, summary=summary, log_id=log_id)


@dataclass(frozen=True)
class ForkResult:
    new_version_id: int
    moved_file_ids: List[int]
    added_replacement_ids: List[int]
    summary: str
    log_id: int


def fork_version(
    conn: sqlite3.Connection,
    *,
    source_version_id: int,
    label: Optional[str] = None,
    include_missing: bool = False,
    replacement_file_ids: Optional[Sequence[int]] = None,
    enforce_unowned: bool = False,
) -> ForkResult:
    """Create a new version based on a source version.

    In schema v6 this *clones* membership (true snapshots): the source version
    keeps its members, and the new version starts with a copy of the selected
    members.

    `file.version_id` is maintained as a best-effort pointer to the latest
    non-discarded version a file participates in.
    """

    src = int(source_version_id)
    if src <= 0:
        raise ValueError("source_version_id must be a positive integer")

    vrow = _get_version_row(conn, src)
    if vrow is None:
        raise ValueError(f"source_version_id {src} does not exist")
    _src_id, asset_id, scheme = vrow

    repl_ids = _norm_ids(replacement_file_ids or [])

    # Determine which file rows to clone from source.
    where_missing = "" if include_missing else " AND f.integrity_state != 'MISSING'"
    rows = conn.execute(
        f"""
        SELECT f.id
        FROM version_file vf
        JOIN file f ON f.id=vf.file_id
        WHERE vf.version_id=?{where_missing}
        ORDER BY f.id;
        """,
        (src,),
    ).fetchall()
    move_ids = [int(r[0]) for r in rows]

    # Validate replacement rows.
    if repl_ids:
        frows = _fetch_files(conn, repl_ids)
        missing_repl = [i for i in repl_ids if i not in frows]
        if missing_repl:
            raise ValueError("replacement_file_ids contain missing file rows")
        if enforce_unowned:
            mem = _fetch_memberships(conn, repl_ids)
            for fid in repl_ids:
                if mem.get(int(fid)):
                    raise ValueError("replacement_file_ids must be unowned when enforce_unowned=True")

    with conn:
        # Create the new version.
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_key), 0) FROM version WHERE asset_id=?;",
            (asset_id,),
        ).fetchone()
        next_sort = int(row[0] if row and row[0] is not None else 0) + 1
        lbl = str(label).strip() if label is not None else ""
        if not lbl:
            lbl = _label_for_scheme(next_sort, scheme)

        conn.execute(
            """
            INSERT INTO version(asset_id, label, sort_key, scheme)
            VALUES (?, ?, ?, ?);
            """,
            (asset_id, lbl, int(next_sort), str(scheme).strip() or "vNN"),
        )
        new_vid = int(conn.execute("SELECT last_insert_rowid();").fetchone()[0])

        # Clone membership from source to new.
        if move_ids:
            add_files_to_version(conn, version_id=new_vid, file_ids=move_ids, ignore_duplicates=True)

        added_repl: List[int] = []
        if repl_ids:
            # Attach replacements to new (membership table). Ownership enforcement handled above.
            add_files_to_version(conn, version_id=new_vid, file_ids=repl_ids, ignore_duplicates=True)
            added_repl = list(repl_ids)

        # Update convenience pointer for any files newly participating in the forked version.
        all_ids = _norm_ids([*move_ids, *added_repl])
        if all_ids:
            row_sk = conn.execute("SELECT sort_key FROM version WHERE id=? LIMIT 1;", (new_vid,)).fetchone()
            target_sk = int(row_sk[0]) if row_sk else 0
            if target_sk > 0:
                conn.execute(
                    f"""
                    UPDATE file
                    SET version_id=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id IN ({_ph(len(all_ids))})
                      AND (
                        version_id IS NULL OR
                        COALESCE((SELECT sort_key FROM version WHERE id=file.version_id), -1) < ?
                      );
                    """,
                    (new_vid, *all_ids, int(target_sk)),
                )

        _touch_versions(conn, [new_vid])

        payload: Dict[str, Any] = {
            "source_version_id": src,
            "moved_file_ids": move_ids,
            "added_file_ids": added_repl,
            "include_missing": bool(include_missing),
            "notes": ["Fork clones membership via version_file."],
        }

        summary = (
            f"Forked version {src} → new version {new_vid} "
            f"(copied {len(move_ids)}, added {len(added_repl)} replacement)"
        )

        log_id = write_version_change_log(
            conn,
            version_id=new_vid,
            action_type="fork",
            summary=summary,
            payload=payload,
        )

    return ForkResult(
        new_version_id=new_vid,
        moved_file_ids=move_ids,
        added_replacement_ids=added_repl,
        summary=summary,
        log_id=log_id,
    )
