"""Checksum utilities.

Stage 7.5.3 adds a UI action to copy a checksum. The DB does not yet store
checksums, so this computes a streaming SHA-256 on demand.

To keep the UI responsive, callers should enforce reasonable caps (count/bytes).
"""

from __future__ import annotations

import hashlib


def sha256_file(path: str, *, chunk_size: int = 1024 * 1024) -> str:
    """Compute sha256 hex digest for a file path.

    Raises:
        OSError: if the file cannot be read.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
