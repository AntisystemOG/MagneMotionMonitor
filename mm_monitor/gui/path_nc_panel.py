"""Path & Node Controller health panel."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from ..plc_reader import SystemSnapshot
from ..system_data import NC_STATES, PATH_STATES, MAX_NC, MAX_PATHS, motor_fault_str
from ._tableutil import set_cell


class PathNCPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(10)

        # Global settings bar
        glob_row = QHBoxLayout()
        self._lbl_vel = QLabel("Global Vel: —")
        self._lbl_acc = QLabel("Global Acc: —")
        self._lbl_hb  = QLabel("HLC Heartbeat: —")
        for lbl in [self._lbl_vel, self._lbl_acc, self._lbl_hb]:
            lbl.setStyleSheet("color: #aaaacc; font-size: 10pt; padding: 0 12px;")
            glob_row.addWidget(lbl)
        glob_row.addStretch()
        outer.addLayout(glob_row)

        h = QHBoxLayout()
        h.setSpacing(10)

        # ── Path status ────────────────────────────────────────────────────────
        path_group = QGroupBox("Path Status")
        path_v = QVBoxLayout(path_group)
        self._path_table = QTableWidget(MAX_PATHS, 4)
        self._path_table.setHorizontalHeaderLabels(["Path #", "State", "Vehicles", "Details"])
        self._path_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._path_table.setAlternatingRowColors(True)
        hdr = self._path_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        self._path_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._path_table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        path_v.addWidget(self._path_table)
        h.addWidget(path_group, 1)

        # ── NC status ──────────────────────────────────────────────────────────
        nc_group = QGroupBox("Node Controller Status")
        nc_v = QVBoxLayout(nc_group)
        self._nc_table = QTableWidget(MAX_NC, 5)
        self._nc_table.setHorizontalHeaderLabels(["NC #", "State", "FW Major", "FW Minor", "FW Patch"])
        self._nc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._nc_table.setAlternatingRowColors(True)
        nc_hdr = self._nc_table.horizontalHeader()
        for c in range(5):
            nc_hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        nc_hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        self._nc_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nc_table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        nc_v.addWidget(self._nc_table)
        h.addWidget(nc_group, 1)

        outer.addLayout(h)

        # ── Motor / driver-board faults (MMI_path_ml_faults_status) ──────────
        # One label updated in place (never rebuilt) — avoids per-poll widget churn.
        mf_group = QGroupBox("Motor / Driver-Board Faults  (MMI_path_ml_faults_status)")
        mf_v = QVBoxLayout(mf_group)
        self._mf_label = QLabel("No motor faults.")
        self._mf_label.setWordWrap(True)
        self._mf_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._mf_label.setStyleSheet(
            "color:#1a6e34; background:#ffffff; border:1px solid #b0b3d0;"
            "border-radius:4px; padding:6px; font-family:Consolas; font-size:9pt;")
        mf_v.addWidget(self._mf_label)
        outer.addWidget(mf_group)

    def update(self, snap: SystemSnapshot):
        self._path_table.setUpdatesEnabled(False)
        self._nc_table.setUpdatesEnabled(False)
        try:
            self._update(snap)
        finally:
            self._path_table.setUpdatesEnabled(True)
            self._nc_table.setUpdatesEnabled(True)

    def _update(self, snap: SystemSnapshot):
        self._lbl_vel.setText(f"Global Vel: {snap.global_vel:.2f} m/s")
        self._lbl_acc.setText(f"Global Acc: {snap.global_acc:.2f} m/s²")
        self._lbl_hb.setText(f"HLC Heartbeat: {snap.heartbeat}")

        # Paths
        for i in range(1, MAX_PATHS + 1):
            row = i - 1
            data = snap.path_status[i] if i < len(snap.path_status) else None
            veh_in_path = snap.vehicles_in_path[i] if i < len(snap.vehicles_in_path) else 0

            if data and isinstance(data, dict):
                state_val = data.get("state") or data.get("State")
                if state_val is not None and int(state_val) in PATH_STATES:
                    lbl, color = PATH_STATES[int(state_val)]
                else:
                    lbl, color = str(state_val), "#aaaacc"
                details = "  ".join(f"{k}:{v}" for k, v in data.items() if k not in ("state", "State"))
            else:
                lbl, color, details = "NO DATA", "#444466", ""

            set_cell(self._path_table, row, 0, i, "#aaaacc")
            set_cell(self._path_table, row, 1, lbl, color)
            set_cell(self._path_table, row, 2, veh_in_path,
                     "#27ae60" if veh_in_path > 0 else "#555555")
            set_cell(self._path_table, row, 3, details, "#888888")

        # NCs
        for i in range(1, MAX_NC + 1):
            row = i - 1
            data = snap.nc_status[i] if i < len(snap.nc_status) else None

            if data and isinstance(data, dict):
                state_val = data.get("state")
                if state_val is not None and int(state_val) in NC_STATES:
                    lbl, color = NC_STATES[int(state_val)]
                else:
                    lbl, color = str(state_val), "#aaaacc"
                fw_maj = data.get("software_version_major", "—")
                fw_min = data.get("software_version_minor", "—")
                fw_pat = data.get("software_version_patch", "—")
            else:
                lbl, color = "NO DATA", "#444466"
                fw_maj = fw_min = fw_pat = "—"

            set_cell(self._nc_table, row, 0, i, "#aaaacc")
            set_cell(self._nc_table, row, 1, lbl, color)
            set_cell(self._nc_table, row, 2, fw_maj)
            set_cell(self._nc_table, row, 3, fw_min)
            set_cell(self._nc_table, row, 4, fw_pat)

        # Motor / driver-board faults
        mfaults = getattr(snap, "motor_faults", None) or []
        if not mfaults:
            self._mf_label.setText("No motor faults.")
            self._mf_label.setStyleSheet(
                "color:#1a6e34; background:#ffffff; border:1px solid #b0b3d0;"
                "border-radius:4px; padding:6px; font-family:Consolas; font-size:9pt;")
        else:
            serious = sum(1 for f in mfaults if f.get("serious"))
            lines = [("⚠ " if f.get("serious") else "· ") + motor_fault_str(f) for f in mfaults]
            self._mf_label.setText("\n".join(lines))
            color = "#841825" if serious else "#8a5200"
            self._mf_label.setStyleSheet(
                f"color:{color}; background:#ffffff; border:1px solid #b0b3d0;"
                "border-radius:4px; padding:6px; font-family:Consolas; font-size:9pt;")
