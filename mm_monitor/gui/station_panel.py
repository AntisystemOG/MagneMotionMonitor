"""Station Status — grid showing the state of every station in the system."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from ..plc_reader import SystemSnapshot
from ..system_data import station_name, STATION_NAMES, STATION_STATES, MAX_STATIONS
from ._tableutil import set_cell

_COLS = ["Station #", "Name", "State", "Pallet ID", "Occupied", "Process Done", "Hold"]


class StationPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSortingEnabled(False)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout.addWidget(self._table)

    def update(self, snap: SystemSnapshot):
        self._table.setUpdatesEnabled(False)
        try:
            self._update(snap)
        finally:
            self._table.setUpdatesEnabled(True)

    def _update(self, snap: SystemSnapshot):
        # Only show stations that exist in STATION_NAMES or have data
        station_ids = sorted(STATION_NAMES.keys())
        self._table.setRowCount(len(station_ids))

        for row, st_id in enumerate(station_ids):
            data = snap.stations[st_id] if st_id < len(snap.stations) else None

            state_val = data.get("state") if data else None
            active_veh = data.get("active_vehicle_id") if data else None
            occupied   = data.get("occupied") if data else None
            proc_done  = data.get("process_complete") if data else None
            hold_flag  = data.get("station_hold_flag") if data else None

            # Determine state info
            if state_val is not None and state_val in STATION_STATES:
                state_lbl, state_color = STATION_STATES[state_val]
            elif state_val is not None:
                state_lbl, state_color = f"{state_val}", "#888888"
            else:
                state_lbl, state_color = "—", "#444466"

            bg = "#ffffff"
            if hold_flag:
                bg = "#ffd6d6"   # light red — held
            elif state_val == 2:  # PROCESSING
                bg = "#ead5f5"   # light purple — processing
            elif active_veh:
                bg = "#d4edda"   # light green — occupied

            def cell(c: int, text: str, color: str = "#1a1a2e"):
                set_cell(self._table, row, c, text, color=color, bg=bg)

            cell(0, str(st_id), "#555577")
            cell(1, station_name(st_id), "#1a1a2e")
            cell(2, state_lbl, state_color)
            cell(3, str(active_veh) if active_veh else "—",
                 "#b35a00" if active_veh else "#888888")
            cell(4, "YES" if occupied else "no", "#1a6e34" if occupied else "#888888")
            cell(5, "DONE" if proc_done else "—", "#1a6e34" if proc_done else "#888888")
            cell(6, "HOLD" if hold_flag else "—", "#c0392b" if hold_flag else "#888888")
