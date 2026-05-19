"""SHA-256 checksum utilities.

sha256_file() is called by the Scanner during incremental indexing to compute
and store per-file checksums in the database.
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
