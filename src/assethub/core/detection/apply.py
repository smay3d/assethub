"""Apply detection proposals (Stage 8.4).

The Stage 8.3 detection engine produces *proposal-only* groupings. Stage 8.4
introduces the first write path to materialize those proposals into:

- asset rows (storage-scoped identity: storage_id + type + key)
- a first version per asset (default label v01)
- file.version_id assignments (membership)
- version_change_log entries describing the apply action

This module is Qt-free and designed for unit testing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
import os
from typing import Any, Dict, List, Sequence, Optional, Tuple

from assethub.core.db.assets import create_asset
from assethub.core.db.versions import create_version, get_version_by_asset_sort_key
from assethub.core.db.version_membership import attach_files_to_version, write_version_change_log
from assethub.core.detection.version_parse import parse_version_num, strip_version_token


def _latest_active_version(conn: sqlite3.Connection, *, asset_id: int) -> Optional[Tuple[int, int]]:
    """Return (version_id, sort_key) for the latest non-discarded version, if any."""
    row = conn.execute(
        """
        SELECT id, sort_key
        FROM version
        WHERE asset_id=? AND is_discarded=0
        ORDER BY sort_key DESC
        LIMIT 1;
        """,
        (int(asset_id),),
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), int(row[1])


def _role_key_from_relpath(rel: str) -> str:
    """A deterministic 'role key' for replacement comparisons.

    For version-up merges we want to carry forward prior version files except those
    that are being replaced by newly detected files. A practical heuristic is to
    compare basenames with the version token removed.
    """
    base = os.path.basename(str(rel or ""))
    stem = os.path.splitext(base)[0]
    return strip_version_token(stem)


@dataclass(frozen=True)
class ApplyItem:
    type: str
    key: str
    name: str
    file_ids: List[int]
    desired_sort_key: Optional[int] = None


@dataclass(frozen=True)
class VersionConflict:
    """A detection proposal contains multiple distinct version numbers."""

    item: ApplyItem
    version_to_file_ids: Dict[Optional[int], List[int]]


@dataclass(frozen=True)
class ApplyResult:
    created_assets: int
    created_versions: int
    attached_files: int
    skipped_owned: int
    skipped_missing_rows: int
    summaries: List[str]


def _norm_ids(ids: Sequence[int]) -> List[int]:
    out: List[int] = []
    seen: set[int] = set()
    for v in ids:
        try:
            i = int(v)
        except Exception:
            continue
        if i <= 0 or i in seen:
            continue
        seen.add(i)
        out.append(i)
    return out


def plan_apply_items(
    conn: sqlite3.Connection,
    *,
    items: Sequence[ApplyItem],
) -> Tuple[List[ApplyItem], List[VersionConflict]]:
    """Split ApplyItems by parsed version number and detect mismatches.

    Returns:
        planned_items: ApplyItems where each item maps to *one* version number
            (or None for unversioned).
        conflicts: items whose members contain multiple distinct parsed version numbers.
    """

    planned: List[ApplyItem] = []
    conflicts: List[VersionConflict] = []

    for it in items:
        fids = _norm_ids(it.file_ids)
        if not fids:
            continue

        # Fetch relative paths for parsing.
        ph = ",".join(["?"] * len(fids))
        rows = conn.execute(
            f"SELECT id, relative_path FROM file WHERE id IN ({ph});",
            tuple(fids),
        ).fetchall()
        path_by_id = {int(r[0]): str(r[1] or "") for r in rows}

        ver_to_ids: Dict[Optional[int], List[int]] = {}
        for fid in fids:
            rel = path_by_id.get(int(fid), "")
            base = os.path.basename(str(rel))
            vnum = parse_version_num(base)
            ver_to_ids.setdefault(vnum, []).append(int(fid))

        if len(ver_to_ids.keys()) <= 1:
            only_key = next(iter(ver_to_ids.keys()))
            planned.append(
                ApplyItem(
                    type=str(it.type),
                    key=str(it.key),
                    name=str(it.name),
                    file_ids=list(ver_to_ids.get(only_key, [])),
                    desired_sort_key=only_key,
                )
            )
            continue

        # Conflict: multiple distinct versions in one proposed asset.
        conflicts.append(VersionConflict(item=it, version_to_file_ids=ver_to_ids))

    return planned, conflicts


def expand_conflict_resolution(
    conflict: VersionConflict,
    *,
    mode: str,
    forced_version: Optional[int] = None,
) -> List[ApplyItem]:
    """Expand a single VersionConflict into ApplyItems.

    Args:
        conflict: The conflict to resolve.
        mode: 'split' or 'force'.
        forced_version: Required when mode=='force'. Use None to force unversioned.
    """

    m = str(mode).strip().lower()
    if m not in {"split", "force"}:
        raise ValueError("mode must be 'split' or 'force'")

    base = conflict.item
    if m == "split":
        out: List[ApplyItem] = []
        # Deterministic: numeric versions in ascending order, then None.
        keys = sorted([k for k in conflict.version_to_file_ids.keys() if k is not None])
        if None in conflict.version_to_file_ids:
            keys.append(None)
        for k in keys:
            out.append(
                ApplyItem(
                    type=str(base.type),
                    key=str(base.key),
                    name=str(base.name),
                    file_ids=list(conflict.version_to_file_ids.get(k, [])),
                    desired_sort_key=k,
                )
            )
        return out

    # force
    if forced_version is not None and int(forced_version) <= 0:
        raise ValueError("forced_version must be positive or None")
    all_ids: List[int] = []
    for ids in conflict.version_to_file_ids.values():
        all_ids.extend([int(x) for x in ids])
    all_ids = _norm_ids(all_ids)
    return [
        ApplyItem(
            type=str(base.type),
            key=str(base.key),
            name=str(base.name),
            file_ids=all_ids,
            desired_sort_key=(None if forced_version is None else int(forced_version)),
        )
    ]


def apply_detection_proposals(
    conn: sqlite3.Connection,
    *,
    storage_id: int,
    items: Sequence[ApplyItem],
) -> ApplyResult:
    """Apply detection proposals in a single transaction.

    Rules:
        - Each ApplyItem creates/fetches a storage-scoped Asset.
        - A new Version is created per item (default v01 on first version).
        - Files are attached with enforce_unowned=True.
        - A `version_change_log` row is written with action_type='detect_apply'.
        - If any referenced file_id does not exist, the operation fails and the
          entire transaction is rolled back.

    Notes:
        - Items with 0 file_ids are skipped (not an error).
    """

    sid = int(storage_id)
    if sid <= 0:
        raise ValueError("storage_id must be a positive integer")

    created_assets = 0
    created_versions = 0
    attached_files = 0
    skipped_owned = 0
    skipped_missing = 0
    summaries: List[str] = []

    # Build a set of existing asset identities so we can count "created".
    existing_asset_keys = {
        (int(r[0]), str(r[1]), str(r[2]))
        for r in conn.execute(
            "SELECT storage_id, type, key FROM asset WHERE storage_id=?;",
            (sid,),
        ).fetchall()
    }

    with conn:
        for item in items:
            t = str(item.type).strip()
            k = str(item.key).strip()
            n = str(item.name).strip()
            fids = _norm_ids(item.file_ids)
            if not t or not k or not n:
                raise ValueError("ApplyItem has empty fields")
            if not fids:
                continue

            asset = create_asset(
                conn,
                storage_id=sid,
                type=t,
                key=k,
                name=n,
                commit=False,
            )

            ident = (int(asset.storage_id), str(asset.type), str(asset.key))
            existed_before = ident in existing_asset_keys
            if not existed_before:
                created_assets += 1
                existing_asset_keys.add(ident)

            desired = item.desired_sort_key
            version = None

            # Stage 9.2.4: Composite assets version-up by cloning the latest non-discarded
            # version and overriding only the roles present in the incoming set.
            if existed_before and t in {"texture_set", "image_sequence"}:
                # Determine the latest non-discarded version (base).
                row = conn.execute(
                    """
                    SELECT id, sort_key
                    FROM version
                    WHERE asset_id=? AND is_discarded=0
                    ORDER BY sort_key DESC
                    LIMIT 1;
                    """,
                    (int(asset.id),),
                ).fetchone()
                base_vid = int(row[0]) if row is not None else 0
                base_sort = int(row[1]) if row is not None else 0

                # Create the new asset version monotonically.
                next_sort = int(base_sort) + 1 if base_sort > 0 else 1
                version = create_version(
                    conn,
                    asset_id=int(asset.id),
                    sort_key_override=int(next_sort),
                    commit=False,
                )
                created_versions += 1

                # Build a base snapshot selection: latest available file per role
                # across all active (non-discarded) versions of the asset. This
                # preserves robustness for legacy/incomplete histories.
                rows_latest = conn.execute(
                    """
                    SELECT f.id, f.relative_path, v.sort_key
                    FROM version_file vf
                    JOIN version v ON v.id=vf.version_id
                    JOIN file f ON f.id=vf.file_id
                    WHERE v.asset_id=? AND v.is_discarded=0
                    ORDER BY v.sort_key DESC, f.id DESC;
                    """,
                    (int(asset.id),),
                ).fetchall()

                base_by_role: Dict[str, int] = {}
                for fid0, rel0, _sk0 in rows_latest:
                    role0 = _role_key_from_relpath(str(rel0 or ""))
                    if role0 not in base_by_role:
                        base_by_role[role0] = int(fid0)

                base_file_ids = list(base_by_role.values())
                if base_file_ids:
                    conn.executemany(
                        "INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (?, ?);",
                        [(int(version.id), int(fid0)) for fid0 in base_file_ids],
                    )

                # Current role map (starts from base snapshot selection).
                cur_by_role: Dict[str, int] = dict(base_by_role)

                # Incoming role map.
                ph_in = ",".join(["?"] * len(fids))
                in_rows = conn.execute(
                    f"SELECT id, relative_path FROM file WHERE id IN ({ph_in});",
                    tuple(fids),
                ).fetchall()
                in_by_role: Dict[str, int] = {}
                for fid0, rel0 in in_rows:
                    role0 = _role_key_from_relpath(str(rel0 or ""))
                    in_by_role[role0] = int(fid0)

                # Strict: all incoming file rows must exist.
                if len(in_rows) != len(fids):
                    missing_n = len(fids) - len(in_rows)
                    skipped_missing += int(missing_n)
                    raise ValueError(
                        f"Detection apply failed: {missing_n} incoming file row(s) missing during composite version-up for version_id={int(version.id)}"
                    )

                # Count how many incoming files were truly unowned before we attach.
                owned_lookup = conn.execute(
                    f"SELECT file_id FROM version_file WHERE file_id IN ({ph_in});",
                    tuple(fids),
                ).fetchall()
                owned_set = {int(r[0]) for r in owned_lookup}
                attached_unowned_ids = [int(fid0) for fid0 in fids if int(fid0) not in owned_set]
                attached_files += int(len(attached_unowned_ids))

                removed_ids: List[int] = []
                replaced: List[Dict[str, Any]] = []

                # Override roles in the new version: remove old role member (if any), add incoming.
                for role, new_fid in sorted(in_by_role.items()):
                    old_fid = cur_by_role.get(role)
                    if old_fid is not None and int(old_fid) != int(new_fid):
                        conn.execute(
                            "DELETE FROM version_file WHERE version_id=? AND file_id=?;",
                            (int(version.id), int(old_fid)),
                        )
                        removed_ids.append(int(old_fid))
                        replaced.append({"role": role, "old_file_id": int(old_fid), "new_file_id": int(new_fid)})
                    conn.execute(
                        "INSERT OR IGNORE INTO version_file(version_id, file_id) VALUES (?, ?);",
                        (int(version.id), int(new_fid)),
                    )

                # Update convenience pointer for all files participating in the new snapshot.
                final_ids = sorted(({*base_file_ids, *[int(x) for x in fids]}) - set(removed_ids))
                if final_ids:
                    ph_all = ",".join(["?"] * len(final_ids))
                    conn.execute(
                        f"""
                        UPDATE file
                        SET version_id=?, updated_at=CURRENT_TIMESTAMP
                        WHERE id IN ({ph_all})
                          AND (
                            version_id IS NULL OR
                            COALESCE((SELECT sort_key FROM version WHERE id=file.version_id), -1) < ?
                          );
                        """,
                        (int(version.id), *tuple(final_ids), int(next_sort)),
                    )

                # Touch versions involved.
                touched = [int(version.id)]
                if base_vid > 0:
                    touched.append(int(base_vid))
                conn.execute(
                    f"UPDATE version SET updated_at=CURRENT_TIMESTAMP WHERE id IN ({','.join(['?']*len(touched))});",
                    tuple(touched),
                )

                payload: Dict[str, Any] = {
                    "source": "detection",
                    "storage_id": sid,
                    "asset_id": int(asset.id),
                    "asset_type": t,
                    "asset_key": k,
                    "asset_name": n,
                    "version_id": int(version.id),
                    "source_version_id": int(base_vid),
                    "added_file_ids": attached_unowned_ids,
                    "removed_file_ids": removed_ids,
                    "replaced": replaced,
                }

                summary = (
                    f"Detect apply: asset '{n}' ({t}) → {version.label}; "
                    f"base {('none' if base_vid==0 else 'v'+str(base_sort).zfill(2))}; "
                    f"attached {len(attached_unowned_ids)} new files"
                )

                write_version_change_log(
                    conn,
                    version_id=int(version.id),
                    action_type="version_up_merge",
                    summary=summary,
                    payload=payload,
                )

                summaries.append(summary)
                continue

            # Default path: create/find the desired version or auto-increment.
            if version is None:
                if desired is not None:
                    existing = get_version_by_asset_sort_key(conn, asset_id=int(asset.id), sort_key=int(desired))
                    if existing is not None:
                        version = existing
                    else:
                        version = create_version(
                            conn,
                            asset_id=int(asset.id),
                            sort_key_override=int(desired),
                            commit=False,
                        )
                        created_versions += 1
                else:
                    version = create_version(conn, asset_id=int(asset.id), commit=False)
                    created_versions += 1

            attach = attach_files_to_version(
                conn,
                version_id=int(version.id),
                file_ids=fids,
                enforce_unowned=True,
                use_transaction=False,
                write_log=False,
            )

            # Strict: if any file rows are missing, abort (rollback entire apply).
            if attach.missing_file_rows:
                skipped_missing += int(attach.missing_file_rows)
                raise ValueError(
                    f"Detection apply failed: {attach.missing_file_rows} file row(s) were missing for version_id={int(version.id)}"
                )

            attached_files += int(attach.attached)
            skipped_owned += int(attach.skipped_owned)

            payload: Dict[str, Any] = {
                "source": "detection",
                "storage_id": sid,
                "asset_id": int(asset.id),
                "asset_type": t,
                "asset_key": k,
                "asset_name": n,
                "version_id": int(version.id),
                "added_file_ids": _norm_ids(fids) if attach.attached else [],
                "skipped_owned": int(attach.skipped_owned),
            }

            # Best-effort: record only the actually attached file ids (not all candidates).
            # attach_files_to_version returns those in its payload normally; we don't have
            # direct access when write_log=False, so re-query for members of this version.
            rows = conn.execute(
                "SELECT id FROM file WHERE version_id=? ORDER BY id ASC;",
                (int(version.id),),
            ).fetchall()
            payload["added_file_ids"] = [int(r[0]) for r in rows]

            summary = (
                f"Detect apply: asset '{n}' ({t}) → {version.label}; "
                f"attached {int(attach.attached)} files"
            )
            if attach.skipped_owned:
                summary += f" (skipped {int(attach.skipped_owned)} owned)"

            write_version_change_log(
                conn,
                version_id=int(version.id),
                action_type="detect_apply",
                summary=summary,
                payload=payload,
            )

            summaries.append(summary)

    return ApplyResult(
        created_assets=created_assets,
        created_versions=created_versions,
        attached_files=attached_files,
        skipped_owned=skipped_owned,
        skipped_missing_rows=skipped_missing,
        summaries=summaries,
    )
