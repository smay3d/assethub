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
from typing import Any, Dict, List, Sequence

from assethub.core.db.assets import create_asset
from assethub.core.db.versions import create_version
from assethub.core.db.version_membership import attach_files_to_version, write_version_change_log


@dataclass(frozen=True)
class ApplyItem:
    type: str
    key: str
    name: str
    file_ids: List[int]


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
            if ident not in existing_asset_keys:
                created_assets += 1
                existing_asset_keys.add(ident)

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
