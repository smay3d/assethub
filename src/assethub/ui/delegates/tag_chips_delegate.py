"""Tag chip delegate for compact, readable tag visualization.

Stage 9.1.1: Fix overlapping/glitchy rendering and render each tag as a
single-line chip (color + name) with no wrapping.
"""

from __future__ import annotations

from typing import List, Tuple

from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QColor, QPainter, QFontMetrics
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem


TAG_PAYLOAD_ROLE = Qt.ItemDataRole.UserRole + 10  # list[tuple(name, color)]


def _parse_payload(value) -> List[Tuple[str, str]]:
    """Coerce the model payload to list[(name, color)]."""
    out: List[Tuple[str, str]] = []
    if not value:
        return out

    if isinstance(value, (list, tuple)):
        for it in value:
            if isinstance(it, (tuple, list)) and len(it) >= 2:
                out.append((str(it[0]), str(it[1])))
            elif isinstance(it, dict):
                out.append((str(it.get("name", "")), str(it.get("color", ""))))
    return [(n, c) for (n, c) in out if str(n).strip()]


class TagChipsDelegate(QStyledItemDelegate):
    """Draw tag chips: small colored dot + tag name, single-line, no wrap."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pad_x = 6
        self._pad_y = 2
        self._gap = 6
        self._dot_d = 8
        self._dot_gap = 6
        self._chip_radius = 6
        self._max_chips = 6  # render up to N chips, then +X

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        painter.save()

        # Draw the item background/selection etc, but suppress the default text
        # to prevent double-painting and wrapping artifacts.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        payload = _parse_payload(index.data(TAG_PAYLOAD_ROLE))
        if not payload:
            painter.restore()
            return

        rect = opt.rect.adjusted(4, 0, -4, 0)
        fm = QFontMetrics(opt.font)

        x = rect.x()
        y = rect.y()
        h = rect.height()

        # Ensure single-line layout (no wrapping).
        cy = y + (h // 2)

        # Determine how many chips to draw.
        chips = payload[: self._max_chips]
        extra = max(0, len(payload) - len(chips))

        def _draw_chip(label: str, color_hex: str) -> int:
            nonlocal x
            label = str(label)
            qc = QColor(str(color_hex))
            if not qc.isValid():
                qc = QColor("#808080")

            text_w = fm.horizontalAdvance(label)
            chip_h = max(16, h - 6)
            dot_w = self._dot_d + self._dot_gap
            chip_w = self._pad_x + dot_w + text_w + self._pad_x

            # Stop if no room (keep a small right margin).
            if x + chip_w > rect.right() - 6:
                return 0

            chip_rect = QRect(x, cy - (chip_h // 2), chip_w, chip_h)

            # Subtle outline using the tag color; transparent fill to keep low weight.
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(qc)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(chip_rect, self._chip_radius, self._chip_radius)

            # Dot
            dot_rect = QRect(
                chip_rect.x() + self._pad_x,
                cy - (self._dot_d // 2),
                self._dot_d,
                self._dot_d,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qc)
            painter.drawEllipse(dot_rect)

            # Text
            painter.setPen(opt.palette.text().color())
            text_x = dot_rect.right() + self._dot_gap
            text_rect = QRect(text_x, chip_rect.y(), chip_rect.right() - text_x - self._pad_x, chip_rect.height())
            painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), label)

            x = chip_rect.right() + self._gap
            return chip_w

        # Draw chips in order.
        for name, color in chips:
            if not _draw_chip(name, color):
                break

        # If we couldn't render all tags, render a compact "+N" chip.
        if extra > 0:
            _draw_chip(f"+{extra}", "#808080")

        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return super().sizeHint(option, index)
