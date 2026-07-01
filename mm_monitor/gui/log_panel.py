from __future__ import annotations
from datetime import datetime
from typing import Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit
from PySide6.QtGui import QTextCursor


class EventLogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        bar = QHBoxLayout()
        bar.addStretch()
        btn_clear = QPushButton("Clear Log")
        bar.addWidget(btn_clear)
        layout.addLayout(bar)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        layout.addWidget(self._text)

        btn_clear.clicked.connect(self._text.clear)

    def _log(self, message: str, color: str = "#cccccc"):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = (
            f'<span style="color:#555577">[{ts}]</span> '
            f'<span style="color:{color}">{message}</span>'
        )
        self._text.append(line)
        self._text.moveCursor(QTextCursor.End)

    def log_info(self, message: str):
        self._log(message, "#2980b9")

    def log_state_change(self, mover_num: int, old_state: str, new_state: str):
        if "FAULT" in new_state:
            color = "#e74c3c"
        elif new_state in ("IDLE", "NO VEHICLE"):
            color = "#27ae60"
        elif new_state == "HOMING":
            color = "#e67e22"
        else:
            color = "#aaaacc"
        self._log(f"Mover {mover_num}: {old_state} → {new_state}", color)

    def log_fault(self, mover_num: int, fault_code: Any):
        self._log(f"⚠  Mover {mover_num} FAULTED — code: {fault_code}", "#e74c3c")

    def log_homing_complete(self, total: int):
        self._log(f"✓  All {total} movers homed", "#27ae60")
