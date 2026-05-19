"""UI-level constants shared across views and tests.

These values are intentionally Qt-free so they can be imported from unit tests
and non-GUI modules without triggering PySide6 initialization.
"""

from __future__ import annotations

# Library
LIBRARY_CAP_ROWS: int = 10_000

# File table default columns (headers)
DEFAULT_VISIBLE_FILE_COLUMNS: tuple[str, ...] = (
    "Storage",
    "Bound",
    "Bound Asset",
    "Owned by Versions",
    "Filename",
    "Relative Path",
    "Size",
    "Modified",
    "Integrity",
    "Tags",
)

# Previews
SUPPORTED_PREVIEW_FORMATS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
PREVIEW_MAX_PIXEL_AREA: int = 921_600
