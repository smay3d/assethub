"""DB helpers for version membership operations.

Stage 8 introduces asset-level versioning where each file row may be assigned to
at most one version via `file.version_id`.

This module provides transactional, Qt-free operations to modify membership and
record a per-action history entry in `version_change_log`.
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

    to_attach: List[int] = []
    skipped_owned = 0
    skipped_already = 0
    moved_from: List[Dict[str, Any]] = []
    notes: List[str] = []

    for fid in ids:
        row = files.get(fid)
        if row is None:
            continue
        cur_vid, _integrity, _size = row
        if cur_vid == vid:
            skipped_already += 1
            continue
        if cur_vid is not None and enforce_unowned:
            skipped_owned += 1
            continue
        if cur_vid is not None and cur_vid != vid:
            moved_from.append({"file_id": fid, "from_version_id": int(cur_vid)})
        to_attach.append(fid)

    log_id = 0
    summary = ""

    def _apply() -> None:
        nonlocal log_id, summary
        if to_attach:
            conn.execute(
                f"UPDATE file SET version_id=?, updated_at=CURRENT_TIMESTAMP WHERE id IN ({_ph(len(to_attach))});",
                (vid, *to_attach),
            )
            _touch_versions(conn, [vid])
            if moved_from:
                _touch_versions(conn, [int(m["from_version_id"]) for m in moved_from])

        payload: Dict[str, Any] = {
            "added_file_ids": to_attach,
            "missing_file_rows": missing,
            "skipped_already_attached": skipped_already,
            "skipped_owned": skipped_owned,
        }
        if moved_from:
            payload["moved_from"] = moved_from
            notes.append("Some files were reassigned from other versions.")
        if notes:
            payload["notes"] = notes
        if payload_extra:
            payload.update(payload_extra)

        moved_n = len(moved_from)
        suffix_bits: List[str] = []
        if skipped_owned:
            suffix_bits.append(f"skipped {skipped_owned} owned")
        if skipped_already:
            suffix_bits.append(f"skipped {skipped_already} already")
        if moved_n:
            suffix_bits.append(f"moved {moved_n}")

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
    """Detach files by clearing file.version_id.

    If only_from_version_id is provided, detach only where the file is currently
    assigned to that version.
    """

    ids = _norm_ids(file_ids)
    if not ids:
        raise ValueError("file_ids must be non-empty")

    only_vid = None if only_from_version_id is None else int(only_from_version_id)
    if only_vid is not None and only_vid <= 0:
        raise ValueError("only_from_version_id must be a positive integer")

    files = _fetch_files(conn, ids)
    missing = len(ids) - len(files)

    to_detach: List[int] = []
    skipped = 0
    removed_by_version: Dict[int, List[int]] = {}

    for fid in ids:
        row = files.get(fid)
        if row is None:
            continue
        cur_vid, _integrity, _size = row
        if cur_vid is None:
            skipped += 1
            continue
        if only_vid is not None and cur_vid != only_vid:
            skipped += 1
            continue
        to_detach.append(fid)
        removed_by_version.setdefault(int(cur_vid), []).append(fid)

    log_ids: List[int] = []
    with conn:
        if to_detach:
            conn.execute(
                f"UPDATE file SET version_id=NULL, updated_at=CURRENT_TIMESTAMP WHERE id IN ({_ph(len(to_detach))});",
                tuple(to_detach),
            )
            _touch_versions(conn, list(removed_by_version.keys()))

        suffix = ""
        if skipped:
            suffix = f" ({skipped} were not attached)"
        summary = f"Detached {len(to_detach)} files{suffix}"

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
        detached=len(to_detach),
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

    # Enforce unowned for the new file if requested.
    if enforce_unowned and new_vid is not None and int(new_vid) != vid:
        raise ValueError("new_file_id is already owned by another version")

    removed_old = False
    added_new = False
    moved_from: Optional[int] = None

    with conn:
        if old_vid == vid:
            conn.execute(
                "UPDATE file SET version_id=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?;",
                (old_id,),
            )
            removed_old = True
        else:
            notes.append("old file was not attached to target version")

        if new_vid is not None and int(new_vid) != vid:
            moved_from = int(new_vid)

        if new_vid != vid:
            conn.execute(
                "UPDATE file SET version_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?;",
                (vid, new_id),
            )
            added_new = True

        _touch_versions(conn, [vid])
        if moved_from is not None:
            _touch_versions(conn, [moved_from])

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
        if moved_from is not None:
            payload["moved_from_version_id"] = moved_from

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
    """Create a new version and reassign selected membership.

    NOTE: Because `file.version_id` is a single-valued foreign key, files cannot
    belong to multiple versions simultaneously. This operation *moves* selected
    file rows from the source version to the new version.
    """

    src = int(source_version_id)
    if src <= 0:
        raise ValueError("source_version_id must be a positive integer")

    vrow = _get_version_row(conn, src)
    if vrow is None:
        raise ValueError(f"source_version_id {src} does not exist")
    _src_id, asset_id, scheme = vrow

    repl_ids = _norm_ids(replacement_file_ids or [])

    # Determine which file rows to move from source.
    where_missing = "" if include_missing else " AND integrity_state != 'MISSING'"
    rows = conn.execute(
        f"SELECT id FROM file WHERE version_id=?{where_missing} ORDER BY id;",
        (src,),
    ).fetchall()
    move_ids = [int(r[0]) for r in rows]

    # Validate replacement ownership if enforcing unowned.
    if repl_ids:
        frows = _fetch_files(conn, repl_ids)
        missing_repl = [i for i in repl_ids if i not in frows]
        if missing_repl:
            raise ValueError("replacement_file_ids contain missing file rows")
        if enforce_unowned:
            for fid in repl_ids:
                cur_vid, _integrity, _size = frows[fid]
                if cur_vid is not None:
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

        # Move membership from source to new.
        if move_ids:
            conn.execute(
                f"UPDATE file SET version_id=?, updated_at=CURRENT_TIMESTAMP WHERE id IN ({_ph(len(move_ids))});",
                (new_vid, *move_ids),
            )

        added_repl: List[int] = []
        moved_from_other: List[Dict[str, Any]] = []
        if repl_ids:
            # Attach replacements to new; allow reassignment unless enforce_unowned.
            current = _fetch_files(conn, repl_ids)
            to_attach: List[int] = []
            skipped_owned = 0
            for fid in repl_ids:
                cur_vid, _integrity, _size = current[fid]
                if cur_vid == new_vid:
                    continue
                if cur_vid is not None and enforce_unowned:
                    skipped_owned += 1
                    continue
                if cur_vid is not None and int(cur_vid) != new_vid:
                    moved_from_other.append({"file_id": fid, "from_version_id": int(cur_vid)})
                to_attach.append(fid)
            if to_attach:
                conn.execute(
                    f"UPDATE file SET version_id=?, updated_at=CURRENT_TIMESTAMP WHERE id IN ({_ph(len(to_attach))});",
                    (new_vid, *to_attach),
                )
                added_repl = list(to_attach)
            if moved_from_other:
                _touch_versions(conn, [int(m["from_version_id"]) for m in moved_from_other])
            if skipped_owned:
                # Represent skipped owned as a note in payload.
                pass

        # Touch only the new version (per plan).
        _touch_versions(conn, [new_vid])

        payload: Dict[str, Any] = {
            "source_version_id": src,
            "moved_file_ids": move_ids,
            "added_file_ids": added_repl,
            "include_missing": bool(include_missing),
        }
        notes: List[str] = [
            "Fork moves file membership because file.version_id is single-valued.",
        ]
        if moved_from_other:
            payload["moved_from"] = moved_from_other
        if notes:
            payload["notes"] = notes

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
