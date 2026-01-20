# src/assethub/core/detection/engine.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Dict, List, Tuple
import re
import sqlite3

from .rules_loader import DetectionRuleset


@dataclass(frozen=True)
class DetectionProposal:
    type: str
    key: str
    suggested_name: str
    file_ids: list[int]
    reason: str


@dataclass(frozen=True)
class DetectionSummary:
    total_considered: int
    skipped_owned: int
    skipped_excluded: int


@dataclass(frozen=True)
class DetectionResult:
    proposals: list[DetectionProposal]
    summary: DetectionSummary


def _norm_rel(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("/")


def _split_dir_name(rel: str) -> Tuple[str, str]:
    p = PurePosixPath(rel)
    d = str(p.parent) if str(p.parent) != "." else ""
    return d, p.name


def _ext_lower(name: str) -> str:
    m = re.search(r"(\.[^./\\]+)$", name)
    if not m:
        return ""
    return m.group(1)[1:].lower()


def _compile_image_seq_regex(seps: Tuple[str, ...], min_digits: int) -> re.Pattern[str]:
    esc = "".join(re.escape(s) for s in seps)
    # Greedy base to capture last separator before digits.
    return re.compile(rf"^(?P<base>.+)(?P<sep>[{esc}])(?P<digits>\d{{{min_digits},}})(?P<ext>\.[^./\\]+)$")


def _compile_texture_regex(seps: Tuple[str, ...], tokens: Tuple[str, ...]) -> re.Pattern[str]:
    esc = "".join(re.escape(s) for s in seps)
    toks = "|".join(re.escape(t) for t in tokens)
    return re.compile(rf"^(?P<base>.+)(?P<sep>[{esc}])(?P<chan>{toks})(?P<ext>\.[^./\\]+)$", re.IGNORECASE)


def detect_proposals_for_storage(
    conn: sqlite3.Connection, *, storage_id: int, rules: DetectionRuleset
) -> DetectionResult:
    """Preview-only detection of asset proposals for a storage root.

    Important:
        This function performs **no DB writes**.
    """
    sid = int(storage_id)
    if sid <= 0:
        raise ValueError("storage_id must be positive")

    rows = conn.execute(
        "SELECT id, relative_path, version_id, integrity_state FROM file WHERE storage_id=? ORDER BY id ASC;",
        (sid,),
    ).fetchall()

    total_considered = 0
    skipped_owned = 0
    skipped_excluded = 0

    img_re = _compile_image_seq_regex(rules.image_sequence_separators, rules.image_sequence_min_digits)
    tex_re = _compile_texture_regex(rules.texture_set_separators, rules.texture_set_channel_tokens)

    used_file_ids: set[int] = set()

    img_groups: Dict[str, Dict[str, object]] = {}
    tex_groups: Dict[str, List[int]] = {}
    generic_groups: Dict[str, List[int]] = {}

    # Pass 1: classify each row deterministically.
    for file_id, rel_raw, version_id, integrity_state in rows:
        total_considered += 1
        if version_id is not None:
            skipped_owned += 1
            continue

        rel = _norm_rel(rel_raw)
        d, name = _split_dir_name(rel)
        ext = _ext_lower(name)
        if ext in rules.excluded_exts:
            skipped_excluded += 1
            continue

        # image_sequence
        m = img_re.match(name)
        if m:
            base = str(m.group("base"))
            sep = str(m.group("sep"))
            digits = str(m.group("digits"))
            ext_with_dot = str(m.group("ext"))
            key = f"{d}/{base}{ext_with_dot}" if d else f"{base}{ext_with_dot}"
            grp = img_groups.setdefault(key, {"base": base, "ext": ext_with_dot, "sep": sep, "digits": digits, "file_ids": []})
            grp["file_ids"].append(int(file_id))
            used_file_ids.add(int(file_id))
            continue

        # texture_set
        m2 = tex_re.match(name)
        if m2:
            base = str(m2.group("base"))
            key = f"{d}/{base}" if d else base
            tex_groups.setdefault(key, []).append(int(file_id))
            used_file_ids.add(int(file_id))
            continue

        # generic (fallback)
        stem = re.sub(r"\.[^./\\]+$", "", name)
        key = f"{d}/{stem}" if d else stem
        generic_groups.setdefault(key, []).append(int(file_id))
        used_file_ids.add(int(file_id))

    proposals: List[DetectionProposal] = []

    # Emit image sequences
    for key, grp in img_groups.items():
        file_ids = sorted(grp["file_ids"])  # type: ignore[arg-type]
        base = str(grp["base"])
        reason = f"image_sequence: sep='{grp['sep']}' digits={len(str(grp['digits']))}"
        proposals.append(
            DetectionProposal(
                type="image_sequence",
                key=key,
                suggested_name=base,
                file_ids=file_ids,
                reason=reason,
            )
        )

    # Emit texture sets (only groups >= min_files)
    for key, file_ids in tex_groups.items():
        if len(file_ids) < rules.texture_set_min_files:
            # If it doesn't qualify, move its members into generic groups deterministically.
            for fid in file_ids:
                # reconstruct generic key from the file row
                rel_raw = next(r[1] for r in rows if int(r[0]) == fid)
                rel = _norm_rel(rel_raw)
                d, name = _split_dir_name(rel)
                stem = re.sub(r"\.[^./\\]+$", "", name)
                gkey = f"{d}/{stem}" if d else stem
                generic_groups.setdefault(gkey, []).append(fid)
            continue
        base = key.split("/")[-1]
        proposals.append(
            DetectionProposal(
                type="texture_set",
                key=key,
                suggested_name=base,
                file_ids=sorted(file_ids),
                reason="texture_set: channel tokens",
            )
        )

    # Emit generic
    for key, file_ids in generic_groups.items():
        stem = key.split("/")[-1]
        proposals.append(
            DetectionProposal(
                type="generic",
                key=key,
                suggested_name=stem,
                file_ids=sorted(file_ids),
                reason="generic: grouped by stem",
            )
        )

    # Sort proposals deterministically.
    proposals.sort(key=lambda p: (p.type, p.key))
    # Ensure file_ids sorted
    proposals = [
        DetectionProposal(p.type, p.key, p.suggested_name, sorted(p.file_ids), p.reason) for p in proposals
    ]

    summary = DetectionSummary(
        total_considered=total_considered,
        skipped_owned=skipped_owned,
        skipped_excluded=skipped_excluded,
    )
    return DetectionResult(proposals=proposals, summary=summary)
