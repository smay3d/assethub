# src/assethub/core/detection/rules_loader.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json

import importlib.resources as pkg_resources

from assethub import resources


@dataclass(frozen=True)
class DetectionRuleset:
    """Normalized detection rules for proposal preview.

    Notes:
        - This ruleset is intentionally small and deterministic for v0.
        - `.tx` and `.rat` are always excluded (case-insensitive).
    """

    excluded_exts: frozenset[str]
    image_sequence_separators: tuple[str, ...]
    image_sequence_min_digits: int
    texture_set_separators: tuple[str, ...]
    texture_set_channel_tokens: tuple[str, ...]
    texture_set_min_files: int
    generic_group_by_stem: bool


def resolve_rules_root(*, data_root: str, rules_root: str) -> Path:
    """Resolve the effective rules directory.

    If `rules_root` is empty, uses `<data_root>/rules`.
    """
    if rules_root:
        return Path(rules_root)
    if data_root:
        return Path(data_root) / "rules"
    return Path("rules")


def _load_default_rules_json() -> Dict[str, Any]:
    with pkg_resources.files(resources).joinpath("detection_rules_default.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def _safe_get(d: Dict[str, Any], key: str, default: Any) -> Any:
    v = d.get(key, default)
    return default if v is None else v


def load_detection_ruleset(*, data_root: str, rules_root: str = "") -> DetectionRuleset:
    """Load detection ruleset from user config or bundled defaults.

    Load order:
        1) `{rules_root}/detection_rules.json` (rules_root may resolve from data_root)
        2) bundled defaults in `assethub.resources`

    If user JSON is missing/invalid, we fall back to defaults.
    Missing keys are filled from defaults.
    """
    defaults = _load_default_rules_json()

    rr = resolve_rules_root(data_root=data_root, rules_root=rules_root)
    user_path = rr / "detection_rules.json"

    user: Dict[str, Any] = {}
    if user_path.exists():
        try:
            user = json.loads(user_path.read_text(encoding="utf-8"))
            if not isinstance(user, dict):
                user = {}
        except Exception:
            user = {}

    cfg: Dict[str, Any] = {**defaults, **user}

    # Fill nested objects from defaults where missing.
    for section in ("image_sequence", "texture_set", "generic"):
        base = defaults.get(section, {})
        u = user.get(section, {}) if isinstance(user.get(section, {}), dict) else {}
        merged = {**base, **u}
        cfg[section] = merged

    excluded = set(str(x).lower().lstrip(".") for x in _safe_get(cfg, "excluded_exts", []))
    excluded.update({"tx", "rat"})

    img = cfg["image_sequence"]
    tex = cfg["texture_set"]
    gen = cfg["generic"]

    img_seps = tuple(str(s) for s in _safe_get(img, "separators", [".", "_", "-"]) if str(s))
    img_min = int(_safe_get(img, "min_digits", 3))

    tex_seps = tuple(str(s) for s in _safe_get(tex, "separators", ["_", "-"]) if str(s))
    tokens = tuple(str(t).lower() for t in _safe_get(tex, "channel_tokens", []) if str(t))
    min_files = int(_safe_get(tex, "min_files", 2))

    group_by_stem = bool(_safe_get(gen, "group_by_stem", True))

    return DetectionRuleset(
        excluded_exts=frozenset(excluded),
        image_sequence_separators=img_seps,
        image_sequence_min_digits=img_min,
        texture_set_separators=tex_seps,
        texture_set_channel_tokens=tokens,
        texture_set_min_files=min_files,
        generic_group_by_stem=group_by_stem,
    )
