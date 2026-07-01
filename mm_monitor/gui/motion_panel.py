"""Motion panel — live cart speed, following error, and propulsion power status.

Note on "power": the MagneMotion HLC does not publish per-cart electrical power
or motor current to this PLC, so true wattage is not available. The most useful
motion-health signals that ARE available are surfaced here:
  - Velocity (live speed) per cart, from MMI_vehicle_status.Velocity
  - Following error = Commanded_Position - Position (large = cart struggling)
  - Global velocity / acceleration limits (MM_Global_Velocity / MM_Global_Acc)
  - Propulsion power relay feedback (safety EDM bit), if readable
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from ..plc_reader import SystemSnapshot
from ..system_data import station_name, MAX_VEHICLES
from ._tableutil import set_cell

_COLS = ["Cart", "Path", "Speed (m/s)", "Speed", "Actual Pos (m)",
         "Cmd Pos (m)", "Follow Err (m)", "Heading To"]

_MOVING_THRESH = 0.01   # m/s above which a cart is considered moving
_FOLLOW_WARN   = 0.05   # m following error → amber
_FOLLOW_FAULT  = 0.15   # m following error → red


def _stat(title: str) -> tuple[QWidget, QLabel]:
    box = QGroupBox(title)
    box.setMinimumWidth(0)
    box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    v = QVBoxLayout(box)
    val = QLabel("—")
    val.setStyleSheet("font-size:16pt;font-weight:bold;color:#e0e0e0;")
    val.setAlignment(Qt.AlignCenter)
    v.addWidget(val)
    return box, val


class MotionPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # ── top summary row ───────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(10)
        b1, self._lbl_vel = _stat("Global Vel")
        b2, self._lbl_acc = _stat("Global Acc")
        b3, self._lbl_moving = _stat("Moving")
        b4, self._lbl_maxspd = _stat("Fastest")
        b5, self._lbl_power = _stat("Power Relay")
        for b in (b1, b2, b3, b4, b5):
            top.addWidget(b)
        outer.addLayout(top)

        note = QLabel("Per-cart electrical power / motor current is not published by the "
                      "MagneMotion HLC — speed and following-error are the available motion-health signals.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8888aa;font-size:9pt;")
        outer.addWidget(note)

        # ── cart motion table ─────────────────────────────────────────────────
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        hdr = self._table.horizontalHeader()
        for c in range(len(_COLS)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)   # speed bar
        hdr.setSectionResizeMode(7, QHeaderView.Stretch)   # heading to
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        outer.addWidget(self._table, 1)

    def update(self, snap: SystemSnapshot):
        self._table.setUpdatesEnabled(False)
        try:
            self._lbl_vel.setText(f"{snap.global_vel:.2f} m/s")
            self._lbl_acc.setText(f"{snap.global_acc:.2f} m/s²")

            if snap.propulsion_power is None:
                self._lbl_power.setText("N/A")
                self._lbl_power.setStyleSheet("font-size:16pt;font-weight:bold;color:#777799;")
            elif snap.propulsion_power:
                self._lbl_power.setText("OK")
                self._lbl_power.setStyleSheet("font-size:16pt;font-weight:bold;color:#27ae60;")
            else:
                self._lbl_power.setText("OFF")
                self._lbl_power.setStyleSheet("font-size:16pt;font-weight:bold;color:#e74c3c;")

            # gather active carts
            carts = []
            for i in range(1, MAX_VEHICLES + 1):
                vs = snap.vehicle_status[i]
                if not vs or not (vs.get("Path_ID") or 0):
                    continue
                vel = float(vs.get("Velocity") or 0.0)
                pos = float(vs.get("Position") or 0.0)
                cmd = float(vs.get("Commanded_Position") or 0.0)
                carts.append((i, vs.get("Path_ID") or 0, vel, pos, cmd,
                              vs.get("Dest_Station_ID") or 0))

            moving = sum(1 for c in carts if abs(c[2]) > _MOVING_THRESH)
            fastest = max((abs(c[2]) for c in carts), default=0.0)
            self._lbl_moving.setText(f"{moving} / {len(carts)}")
            self._lbl_maxspd.setText(f"{fastest:.2f} m/s")

            vmax = max(snap.global_vel, fastest, 0.1)
            self._table.setRowCount(len(carts))

            for row, (cid, path_id, vel, pos, cmd, dest) in enumerate(carts):
                follow_err = cmd - pos
                aerr = abs(follow_err)
                err_color = ("#e74c3c" if aerr >= _FOLLOW_FAULT else
                             "#f39c12" if aerr >= _FOLLOW_WARN else "#27ae60")
                spd_color = "#2980b9" if abs(vel) > _MOVING_THRESH else "#555555"

                set_cell(self._table, row, 0, cid, "#f39c12")
                set_cell(self._table, row, 1, path_id, "#aaaacc")
                set_cell(self._table, row, 2, f"{vel:.3f}", spd_color)

                # text bar (no per-poll widget creation — avoids Qt widget churn)
                frac = min(abs(vel) / vmax, 1.0) if vmax > 0 else 0.0
                filled = int(round(frac * 14))
                set_cell(self._table, row, 3, "█" * filled + "·" * (14 - filled),
                         spd_color, align=Qt.AlignLeft | Qt.AlignVCenter)

                set_cell(self._table, row, 4, f"{pos:.3f}")
                set_cell(self._table, row, 5, f"{cmd:.3f}")
                set_cell(self._table, row, 6, f"{follow_err:+.3f}", err_color)
                set_cell(self._table, row, 7, station_name(dest) if dest else "—",
                         "#cccccc" if dest else "#555555")
        finally:
            self._table.setUpdatesEnabled(True)
