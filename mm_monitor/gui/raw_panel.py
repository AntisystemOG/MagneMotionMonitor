"""Raw MMI tag browser — shows every discovered MMI_* tag and its current value."""
from __future__ import annotations
from typing import Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt
from ._tableutil import set_cell


class RawTagsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_rows: list[tuple[str, str, str]] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Filter:"))
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("tag name substring…")
        self._filter.setMaximumWidth(300)
        self._filter.textChanged.connect(self._apply_filter)
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color: #666688;")
        bar.addWidget(self._filter)
        bar.addSpacing(12)
        bar.addWidget(self._count_lbl)
        bar.addStretch()
        layout.addLayout(bar)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Tag Name", "Type", "Value"])
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self._table)

    def update_tags(self, tags: dict[str, tuple[str, Any]]):
        """tags: { tag_name: (type_str, value) }"""
        self._all_rows = sorted(
            [(name, typ, "" if val is None else str(val)) for name, (typ, val) in tags.items()],
            key=lambda r: r[0],
        )
        self._apply_filter(self._filter.text())

    def _apply_filter(self, text: str):
        lower = text.lower()
        visible = [r for r in self._all_rows if not lower or lower in r[0].lower()]
        self._table.setUpdatesEnabled(False)
        try:
            self._table.setRowCount(len(visible))
            for row, (name, typ, val) in enumerate(visible):
                set_cell(self._table, row, 0, name, align=Qt.AlignLeft | Qt.AlignVCenter)
                set_cell(self._table, row, 1, typ)
                set_cell(self._table, row, 2, val, align=Qt.AlignLeft | Qt.AlignVCenter)
        finally:
            self._table.setUpdatesEnabled(True)
        n = len(visible)
        t = len(self._all_rows)
        self._count_lbl.setText(f"{n} / {t} tags" if lower else f"{t} tags")
