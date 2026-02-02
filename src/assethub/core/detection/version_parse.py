"""Version number parsing helpers.

Stage 9.2 introduces more realistic versioning for CG workflows.

We attempt to parse a version number from a filename (not full path) using
conservative patterns. This is intentionally *best effort* and is used only
to propose version sort keys during ingest / detection.

Supported examples:
  - foo_v02.exr
  - foo.ver2.png
  - foo-version_12.mb
  - foo.v003.1001.exr

Non-goals:
  - semantic versions (1.2.3)
  - dates (2025_01_01)
  - any guarantee of correctness
"""

from __future__ import annotations

import os
import re
from typing import Optional


# Match separators like ., _, -, or whitespace before the token.
_SEP = r"(?:^|[\._\-\s])"
# Token + digits, with optional leading zeros.
_TOKEN = r"(?:v|ver|version)\s*0*(\d+)"
# Require a boundary after digits (end or separator).
_END = r"(?=$|[\._\-\s])"

_RE = re.compile(_SEP + _TOKEN + _END, flags=re.IGNORECASE)


def parse_version_num(filename_or_path: str) -> Optional[int]:
    """Return parsed version number from a filename/path, or None.

    We take the *last* matching token in the stem to better handle multi-token
    names like `asset_v01_final_v03.exr`.
    """

    s = str(filename_or_path or "").strip()
    if not s:
        return None

    base = os.path.basename(s)
    stem, _ = os.path.splitext(base)

    matches = list(_RE.finditer(stem))
    if not matches:
        return None

    m = matches[-1]
    try:
        n = int(m.group(1))
    except Exception:
        return None

    # v0 is rarely meaningful for artist workflows; treat it as absent.
    if n <= 0:
        return None
    return n


def format_vnn(n: int) -> str:
    """Format a numeric version as vNN with at least 2-digit padding."""
    nn = int(n)
    if nn <= 0:
        raise ValueError("n must be positive")
    return f"v{nn:02d}"


def strip_version_token(stem_or_name: str) -> str:
    """Strip a trailing version token from a stem/name.

    Examples:
        foo_v02 -> foo
        foo.ver2 -> foo
        foo-version_12 -> foo

    Notes:
        - Operates on the *stem* (no extension) but is tolerant of full names.
        - Removes only the *last* matching token to avoid being too destructive.
    """

    s = str(stem_or_name or "").strip()
    if not s:
        return ""

    base = os.path.basename(s)
    stem, ext = os.path.splitext(base)
    # If the caller passed a stem, ext will be empty. That's fine.

    matches = list(_RE.finditer(stem))
    if not matches:
        return stem

    m = matches[-1]
    start, end = m.span()
    out = (stem[:start] + stem[end:]).rstrip("._- ")
    return out
