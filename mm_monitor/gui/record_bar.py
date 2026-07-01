"""Record / playback control bar (sits below the connection bar)."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QSlider, QComboBox, QFrame,
)
from PySide6.QtCore import Qt, Signal


def _fmt(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m:d}:{s:02d}"


_SKIP_BTN_STYLE = (
    "QPushButton{background:#d0d5eb;color:#1a1a2e;border:1px solid #9999bb;"
    "border-radius:3px;padding:2px 4px;font-size:8pt;min-width:0px;}"
    "QPushButton:hover{background:#a7aed4;}"
    "QPushButton:disabled{color:#999999;background:#e0e0e0;}"
)


class RecordBar(QWidget):
    record_clicked = Signal()
    load_clicked   = Signal()
    play_clicked   = Signal()
    seek           = Signal(int)     # frame index
    skip_seconds   = Signal(float)   # positive = forward, negative = back
    speed_changed  = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._skip_btns: list[QPushButton] = []
        self._build_ui()
        self.set_mode(connected=False, playback=False)

    def _build_ui(self):
        self.setFixedHeight(40)
        self.setStyleSheet("background-color:#e0e3f0;border-bottom:1px solid #b0b3d0;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(6)

        # ── record (live) ────────────────────────────────────────────────────
        self._btn_record = QPushButton("● Record")
        self._btn_record.setFixedWidth(90)
        self._btn_record.clicked.connect(self.record_clicked)
        self._rec_status = QLabel("")
        self._rec_status.setStyleSheet("color:#c0392b;background:transparent;font-size:9pt;")
        lay.addWidget(self._btn_record)
        lay.addWidget(self._rec_status)

        sep = QFrame(); sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#b0b3d0;")
        lay.addWidget(sep)

        # ── playback (offline) ───────────────────────────────────────────────
        self._btn_load = QPushButton("📂 Load")
        self._btn_load.setFixedWidth(80)
        self._btn_load.clicked.connect(self.load_clicked)
        lay.addWidget(self._btn_load)

        # back skip buttons
        for label, delta in [("−5m", -300.0), ("−1m", -60.0), ("−30s", -30.0)]:
            b = QPushButton(label)
            b.setFixedWidth(34)
            b.setStyleSheet(_SKIP_BTN_STYLE)
            b.clicked.connect(lambda _=False, d=delta: self.skip_seconds.emit(d))
            self._skip_btns.append(b)
            lay.addWidget(b)

        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedWidth(32)
        self._btn_play.clicked.connect(self.play_clicked)
        lay.addWidget(self._btn_play)

        # forward skip buttons
        for label, delta in [("+30s", 30.0), ("+1m", 60.0), ("+5m", 300.0)]:
            b = QPushButton(label)
            b.setFixedWidth(34)
            b.setStyleSheet(_SKIP_BTN_STYLE)
            b.clicked.connect(lambda _=False, d=delta: self.skip_seconds.emit(d))
            self._skip_btns.append(b)
            lay.addWidget(b)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.sliderMoved.connect(self.seek)
        self._slider.valueChanged.connect(self._on_slider_value)
        lay.addWidget(self._slider, 1)

        self._time_lbl = QLabel("0:00 / 0:00")
        self._time_lbl.setStyleSheet("color:#555577;background:transparent;font-family:Consolas;font-size:9pt;")
        lay.addWidget(self._time_lbl)

        self._speed = QComboBox()
        self._speed.addItems(["0.5×", "1×", "2×", "4×", "8×"])
        self._speed.setCurrentText("1×")
        self._speed.currentTextChanged.connect(
            lambda t: self.speed_changed.emit(float(t.replace("×", ""))))
        lay.addWidget(self._speed)

    def _on_slider_value(self, v: int):
        self._update_time_label()

    # ── state ────────────────────────────────────────────────────────────────
    def set_mode(self, connected: bool, playback: bool):
        """connected: live PLC link up. playback: a recording is loaded."""
        self._btn_record.setEnabled(connected)
        self._btn_load.setEnabled(not connected)
        pb_active = playback and not connected
        for w in (self._btn_play, self._slider, self._speed):
            w.setEnabled(pb_active)
        for b in self._skip_btns:
            b.setEnabled(pb_active)
        if not playback:
            self._slider.setMaximum(0)
            self._time_lbl.setText("0:00 / 0:00")

    def set_recording(self, active: bool, frames: int = 0, secs: float = 0.0):
        self._btn_record.setText("■ Stop" if active else "● Record")
        self._btn_record.setStyleSheet(
            "QPushButton{background:#ffcccc;color:#7b0000;border:1px solid #c0392b;border-radius:4px;}"
            if active else "")
        self._rec_status.setText(f"REC  {frames} frames  {_fmt(secs)}" if active else "")

    def set_playing(self, playing: bool):
        self._btn_play.setText("❚❚" if playing else "▶")

    def set_total_frames(self, n: int, duration: float):
        self._total = n
        self._duration = duration
        self._slider.setMaximum(max(0, n - 1))
        self._update_time_label()

    def set_position(self, idx: int, t: float):
        self._cur_t = t
        self._slider.blockSignals(True)
        self._slider.setValue(idx)
        self._slider.blockSignals(False)
        self._update_time_label()

    def _update_time_label(self):
        cur = getattr(self, "_cur_t", 0.0)
        dur = getattr(self, "_duration", 0.0)
        self._time_lbl.setText(f"{_fmt(cur)} / {_fmt(dur)}")
