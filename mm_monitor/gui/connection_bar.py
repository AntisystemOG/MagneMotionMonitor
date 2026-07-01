from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox
from PySide6.QtCore import Signal, Qt

from ..system_data import DEFAULT_IP, APP_VERSION

_MINIMIZE_TIMES = [("30 sec", 30), ("1 min", 60), ("10 min", 600), ("30 min", 1800)]


class ConnectionBar(QWidget):
    connect_requested    = Signal(str)
    disconnect_requested = Signal()
    minimize_requested   = Signal(int)   # seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._build_ui()

    def _build_ui(self):
        self.setFixedHeight(44)
        self.setStyleSheet("background-color: #e0e3f0; border-bottom: 1px solid #b0b3d0;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)

        self._led = QLabel("●")
        self._led.setFixedWidth(20)
        self._led.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._led)

        self._btn = QPushButton("Connect")
        self._btn.setFixedWidth(110)
        self._btn.clicked.connect(self._on_button)
        layout.addWidget(self._btn)

        layout.addSpacing(14)

        self._status_lbl = QLabel("Not connected")
        layout.addWidget(self._status_lbl)
        layout.addStretch()

        # Running version (WEEK.DAY.BUILD) — always visible
        ver = QLabel(f"v{APP_VERSION}")
        ver.setToolTip("Running version (week.day.build)")
        ver.setStyleSheet("color: #8888aa; background: transparent; font-size: 9pt; padding: 0 6px;")
        layout.addWidget(ver)

        # ── minimize to cameras ──────────────────────────────────────────────
        min_lbl = QLabel("Minimize for:")
        min_lbl.setStyleSheet("color: #555577; background: transparent; font-size: 9pt;")
        layout.addWidget(min_lbl)

        self._min_time = QComboBox()
        for label, _ in _MINIMIZE_TIMES:
            self._min_time.addItem(label)
        self._min_time.setFixedWidth(80)
        self._min_time.setStyleSheet("font-size: 9pt;")
        layout.addSpacing(4)
        layout.addWidget(self._min_time)

        self._btn_minimize = QPushButton("📷 See Cameras")
        self._btn_minimize.setFixedWidth(130)
        self._btn_minimize.setToolTip("Minimize window to view cameras, auto-restores after chosen time")
        self._btn_minimize.clicked.connect(self._on_minimize)
        layout.addSpacing(6)
        layout.addWidget(self._btn_minimize)

        self._refresh_led(False)

    def _refresh_led(self, connected: bool):
        color = "#27ae60" if connected else "#888888"
        self._led.setStyleSheet(f"color: {color}; font-size: 18px; background: transparent;")

    def _on_button(self):
        if self._connected:
            self.disconnect_requested.emit()
        else:
            self.connect_requested.emit(DEFAULT_IP)

    def _on_minimize(self):
        idx = self._min_time.currentIndex()
        self.minimize_requested.emit(_MINIMIZE_TIMES[idx][1])

    def set_connected(self, connected: bool, message: str = ""):
        self._connected = connected
        self._refresh_led(connected)
        self._btn.setText("Disconnect" if connected else "Connect")
        self._btn.setProperty("connected", "true" if connected else "false")
        self._btn.style().unpolish(self._btn)
        self._btn.style().polish(self._btn)
        color = "#27ae60" if connected else ("#e74c3c" if message else "#888888")
        self._status_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self._status_lbl.setText(message)
