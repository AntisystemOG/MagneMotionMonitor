"""Helper for updating QTableWidget cells IN PLACE.

Recreating QTableWidgetItem objects every poll (new item + setItem) churns Qt at the
C++ level and has hard-crashed this machine before. This helper reuses the existing
item, only creating one the first time a cell is populated.
"""
from __future__ import annotations
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt


def set_cell(table: QTableWidget, row: int, col: int, text,
             color: str | None = None, bg: str | None = None,
             align=Qt.AlignCenter) -> QTableWidgetItem:
    it = table.item(row, col)
    if it is None:
        it = QTableWidgetItem()
        table.setItem(row, col, it)
    it.setText("" if text is None else str(text))
    it.setTextAlignment(align)
    if color is not None:
        it.setForeground(QColor(color))
    if bg is not None:
        it.setBackground(QColor(bg))
    return it
