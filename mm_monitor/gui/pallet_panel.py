"""Pallet Tracker — live table of all active pallets and their locations."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from ..plc_reader import SystemSnapshot
from ..system_data import (
    station_name, STATION_NAMES, VEHICLE_MGR_STATES, MAX_VEHICLES,
)
from ._tableutil import set_cell

# Stations where a pallet is "home" or cleaning
_HOME_STATIONS = {33, 34}
_MOLD_STATIONS = set(range(1, 13))
_PROCESS_STATIONS = set(range(13, 30))

_COLS = ["Pallet #", "MGR State", "At Station", "Station Name",
         "→ Station", "→ Name", "Path ID", "Position (m)", "Velocity (m/s)"]


def _row_color(arrived_st: int, mgr_state: int) -> str:
    if arrived_st in _HOME_STATIONS:
        return "#d4edda"   # light green — at home
    if arrived_st in _MOLD_STATIONS:
        return "#ead5f5"   # light purple — at mold
    if arrived_st in _PROCESS_STATIONS:
        return "#cce5ff"   # light blue — processing
    return "#ffffff"


class PalletPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Summary bar
        bar = QHBoxLayout()
        self._lbl_active  = QLabel("Active: 0")
        self._lbl_homing  = QLabel("Homing: 0")
        self._lbl_molds   = QLabel("At Molds: 0")
        self._lbl_process = QLabel("Processing: 0")
        self._lbl_home    = QLabel("At Home: 0")
        for lbl in [self._lbl_active, self._lbl_homing, self._lbl_molds,
                    self._lbl_process, self._lbl_home]:
            lbl.setStyleSheet("color: #333355; font-size: 10pt;")
            bar.addWidget(lbl)
            bar.addSpacing(16)
        bar.addStretch()
        layout.addLayout(bar)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #b0b3d0;")
        layout.addWidget(sep)

        # Main table
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setAlternatingRowColors(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        # Live sorting on a table repopulated every poll is the documented hard-crash
        # pattern on this machine — keep it OFF; rows are shown in pallet-ID order.
        self._table.setSortingEnabled(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # Pallet #
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # MGR State
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)   # At Station
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)            # Station Name
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)   # → Station
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)            # → Name
        hdr.setSectionResizeMode(6, QHeaderView.ResizeToContents)   # Path ID
        hdr.setSectionResizeMode(7, QHeaderView.ResizeToContents)   # Position
        hdr.setSectionResizeMode(8, QHeaderView.ResizeToContents)   # Velocity
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
        rows = []
        for i in range(1, MAX_VEHICLES + 1):
            vs = snap.vehicle_status[i]
            mg = snap.vehicle_mgr[i] if i < len(snap.vehicle_mgr) else None
            if vs is None or mg is None:
                continue
            path_id = vs.get("Path_ID") or 0
            if not path_id:
                continue  # not tracked

            arrived = mg.get("arrived_station_id") or 0
            dest    = mg.get("dest_station_id")    or 0
            state   = mg.get("state")              or 0
            pos     = vs.get("Position")           or 0.0
            vel     = vs.get("Velocity")           or 0.0

            rows.append((i, state, arrived, dest, path_id, pos, vel))

        self._table.setRowCount(len(rows))

        at_home = at_molds = at_process = 0
        for row_idx, (pal_id, mgr_state, arrived, dest, path_id, pos, vel) in enumerate(rows):
            bg = _row_color(arrived, mgr_state)
            mgr_lbl = VEHICLE_MGR_STATES.get(mgr_state, f"{mgr_state}")

            if arrived in _HOME_STATIONS:
                at_home += 1
            elif arrived in _MOLD_STATIONS:
                at_molds += 1
            elif arrived in _PROCESS_STATIONS:
                at_process += 1

            cells = [
                str(pal_id),
                mgr_lbl,
                str(arrived) if arrived else "—",
                station_name(arrived),
                str(dest) if dest else "—",
                station_name(dest),
                str(path_id),
                f"{pos:.3f}",
                f"{vel:.3f}",
            ]
            for col, val in enumerate(cells):
                set_cell(self._table, row_idx, col, val, bg=bg)

        total = len(rows)
        self._lbl_active.setText(f"Active: {total}")
        self._lbl_home.setText(f"At Home: {at_home}")
        self._lbl_molds.setText(f"At Molds: {at_molds}")
        self._lbl_process.setText(f"Processing: {at_process}")
        self._lbl_homing.setText(f"Homing: {snap.homing_count}")
