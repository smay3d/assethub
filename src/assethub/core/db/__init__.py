# src/assethub/core/db/__init__.py
"""
Database access layer for AssetHub.
"""

from .connection import get_connection  # noqa: F401

# Stage 8.2: version membership operations (Qt-free helpers)
from .version_membership import (  # noqa: F401
    attach_files_to_version,
    detach_files,
    fork_version,
    repair_version_membership,
    write_version_change_log,
)
