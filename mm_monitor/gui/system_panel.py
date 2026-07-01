"""System Overview — health, flags, clickable homing steps, and alarm/blocker list."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QGroupBox,
    QProgressBar, QPushButton, QScrollArea, QButtonGroup, QSizePolicy,
)
from PySide6.QtCore import Qt
from ..plc_reader import SystemSnapshot
from ..system_data import (
    cold_start_info, cold_start_detail, homing_percent, analyze_status,
    current_operation, COLD_START_STEPS, HOMING_STEP_ORDER, SEV_COLORS,
)


def _led(color: str) -> QLabel:
    lbl = QLabel("●")
    lbl.setStyleSheet(f"color: {color}; font-size: 16px; background: transparent;")
    return lbl


class _StatBox(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Box)
        self.setMinimumHeight(72)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setStyleSheet("QFrame { background-color: #e8eaf6; border: 1px solid #b0b3d0; border-radius: 6px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        self._title = QLabel(title)
        self._title.setStyleSheet("color: #555577; font-size: 8pt; background: transparent;")
        self._title.setWordWrap(True)
        self._value = QLabel("—")
        self._value.setStyleSheet("color: #1a1a2e; font-size: 16pt; font-weight: bold; background: transparent;")
        layout.addWidget(self._title)
        layout.addWidget(self._value)

    def set(self, text: str, color: str = "#1a1a2e"):
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {color}; font-size: 16pt; font-weight: bold; background: transparent;")


class _BoolRow(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._led = _led("#555555")
        lbl = QLabel(label)
        lbl.setStyleSheet("background: transparent; font-size: 9pt;")
        layout.addWidget(self._led)
        layout.addWidget(lbl)

    def set(self, active: bool, true_color: str = "#27ae60", false_color: str = "#555555"):
        self._led.setStyleSheet(
            f"color: {true_color if active else false_color}; font-size: 16px; background: transparent;")


class _AlarmRow(QFrame):
    """Reusable alarm row — updated in place (never recreated) to avoid Qt widget churn."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sev = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        self._dot = QLabel("●")
        self._dot.setFixedWidth(18)
        self._dot.setAlignment(Qt.AlignTop)
        self._text = QLabel("")
        self._text.setWordWrap(True)
        self._text.setStyleSheet("background:transparent;")
        lay.addWidget(self._dot)
        lay.addWidget(self._text, 1)
        self.hide()

    def update_content(self, severity: str, title: str, detail: str):
        color = SEV_COLORS.get(severity, "#888888")
        if severity != self._sev:   # only re-style when the color actually changes
            self._sev = severity
            self.setStyleSheet(
                f"QFrame{{background:#e8eaf6;border:1px solid #b0b3d0;"
                f"border-left:4px solid {color};border-radius:4px;}}")
            self._dot.setStyleSheet(f"color:{color};font-size:14px;background:transparent;")
        self._text.setText(f"<b style='color:{color}'>{title}</b><br>"
                           f"<span style='color:#444466;font-size:9pt'>{detail}</span>")
        self.show()


class SystemPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_step: int | None = None   # None = follow live step
        self._last_step: int | None = None        # last step we restyled the timeline for
        self._alarm_sig: tuple | None = None      # signature of currently-shown alarm rows
        self._build_ui()

    # ── construction ─────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(root)
        outer_wrap = QVBoxLayout(self)
        outer_wrap.setContentsMargins(0, 0, 0, 0)
        outer_wrap.addWidget(scroll)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        outer.addWidget(self._build_operation_banner())

        # stat boxes — 3-column grid (2 rows) so each box is taller and not squished wide
        boxes = QGridLayout()
        boxes.setSpacing(8)
        self._box_pallets   = _StatBox("Pallets in System")
        self._box_veh_id    = _StatBox("Vehicles Identified")
        self._box_nc_oper   = _StatBox("NCs Operational")
        self._box_molds     = _StatBox("Vehicles at Molds")
        self._box_modules   = _StatBox("Modules in Auto")
        self._box_cmd_count = _StatBox("HLC Cmd Count")
        stat_list = [self._box_pallets, self._box_veh_id, self._box_nc_oper,
                     self._box_molds, self._box_modules, self._box_cmd_count]
        for idx, b in enumerate(stat_list):
            boxes.addWidget(b, idx // 3, idx % 3)
        for col in range(3):
            boxes.setColumnStretch(col, 1)
        outer.addLayout(boxes)

        # flags — 4-per-row grid so they don't force the panel wide
        flags = QGroupBox("System Flags")
        fl = QGridLayout(flags)
        fl.setSpacing(8)
        self._flag_mm_ready   = _BoolRow("Ready")
        self._flag_hlc        = _BoolRow("HLC Comms")
        self._flag_recovering = _BoolRow("Recovering")
        self._flag_blocked    = _BoolRow("Blocked")
        self._flag_cleanout   = _BoolRow("Cleanout")
        self._flag_mold1      = _BoolRow("Mold 1")
        self._flag_mold2      = _BoolRow("Mold 2")
        flag_list = [self._flag_mm_ready, self._flag_hlc, self._flag_recovering,
                     self._flag_blocked, self._flag_cleanout, self._flag_mold1, self._flag_mold2]
        for idx, f in enumerate(flag_list):
            fl.addWidget(f, idx // 4, idx % 4)
        outer.addWidget(flags)

        outer.addWidget(self._build_homing_group())
        outer.addWidget(self._build_alarms_group(), 1)

    def _build_operation_banner(self) -> QFrame:
        banner = QFrame()
        banner.setMinimumHeight(92)
        self._op_banner = banner
        lay = QVBoxLayout(banner)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self._op_name = QLabel("—")
        self._op_name.setStyleSheet("font-size: 19pt; font-weight: bold; color: #1a1a2e; background: transparent;")
        self._op_pct = QLabel("")
        self._op_pct.setStyleSheet("font-size: 19pt; font-weight: bold; color: #1a1a2e; background: transparent;")
        self._op_pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self._op_name)
        top.addStretch()
        top.addWidget(self._op_pct)
        lay.addLayout(top)

        self._op_bar = QProgressBar()
        self._op_bar.setRange(0, 100)
        self._op_bar.setTextVisible(False)
        self._op_bar.setFixedHeight(18)
        lay.addWidget(self._op_bar)

        self._op_detail = QLabel("")
        self._op_detail.setStyleSheet("font-size: 10pt; color: #333355; background: transparent;")
        self._op_detail.setWordWrap(True)
        lay.addWidget(self._op_detail)
        return banner

    def _update_operation(self, snap: SystemSnapshot):
        op = current_operation(snap)
        color = op["color"]
        self._op_name.setText(f"{op['icon']}  {op['name']}")
        self._op_name.setStyleSheet(
            f"font-size: 19pt; font-weight: bold; color: {color}; background: transparent;")
        self._op_pct.setText(f"{op['pct']}%" if op["active"] else "")
        self._op_pct.setStyleSheet(
            f"font-size: 19pt; font-weight: bold; color: {color}; background: transparent;")
        self._op_bar.setValue(int(op["pct"]))
        self._op_bar.setStyleSheet(
            "QProgressBar{background:#e0e3f0;border:1px solid #b0b3d0;border-radius:4px;}"
            f"QProgressBar::chunk{{background:{color};border-radius:3px;}}")
        self._op_detail.setText(op["detail"])
        # banner border glows in the operation color when an operation is active
        bw = 3 if op["active"] else 1
        self._op_banner.setStyleSheet(
            f"QFrame{{background:#f0f2f8;border:{bw}px solid {color};border-radius:8px;}}")

    def _build_homing_group(self) -> QGroupBox:
        box = QGroupBox("Cold Start / Homing  (click a step for details)")
        v = QVBoxLayout(box)

        self._homing_pct = QProgressBar()
        self._homing_pct.setRange(0, 100)
        self._homing_pct.setValue(100)
        self._homing_pct.setFormat("SYSTEM RUNNING")
        self._homing_pct.setFixedHeight(30)
        v.addWidget(self._homing_pct)

        step_row = QHBoxLayout()
        self._step_num = QLabel("STEP 5")
        self._step_num.setStyleSheet("font-size: 15pt; font-weight: bold; color: #27ae60; background: transparent;")
        self._step_phase = QLabel("IDLE")
        self._step_phase.setStyleSheet(
            "font-size: 11pt; font-weight: bold; color: #555577; background: transparent;"
            "border: 1px solid #aaaacc; border-radius: 4px; padding: 2px 6px;")
        self._step_desc = QLabel("System running")
        self._step_desc.setStyleSheet("font-size: 10pt; color: #333355; background: transparent;")
        self._step_desc.setWordWrap(True)
        step_row.addWidget(self._step_num)
        step_row.addSpacing(10)
        step_row.addWidget(self._step_phase)
        step_row.addSpacing(14)
        step_row.addWidget(self._step_desc)
        step_row.addStretch()
        v.addLayout(step_row)

        # clickable step timeline
        tl = QHBoxLayout()
        tl.setSpacing(3)
        self._step_btns: dict[int, QPushButton] = {}
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        _STEP_STYLE = (
            "QPushButton { min-width: 0px; padding: 0 2px; font-size: 8pt; text-align: center; }"
            "QPushButton:checked { background-color: #c5cae9; font-weight: bold; }"
        )
        for step in HOMING_STEP_ORDER:
            b = QPushButton(str(step))
            b.setCheckable(True)
            b.setFixedSize(92, 28)
            b.setStyleSheet(_STEP_STYLE)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(cold_start_info(step)[1])
            b.clicked.connect(lambda _=False, s=step: self._on_step_clicked(s))
            self._step_btns[step] = b
            self._btn_group.addButton(b)
            tl.addWidget(b)
        tl.addStretch()
        v.addLayout(tl)

        # detail box for the selected step
        self._step_detail = QLabel("Click a step above to see what it does.")
        self._step_detail.setWordWrap(True)
        self._step_detail.setStyleSheet(
            "background:#e8eaf6;border:1px solid #b0b3d0;border-radius:5px;"
            "padding:9px;color:#1a1a2e;font-size:10pt;")
        self._step_detail.setMinimumHeight(64)
        self._step_detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        v.addWidget(self._step_detail)
        return box

    def _build_alarms_group(self) -> QGroupBox:
        box = QGroupBox("Alarms & Homing Blockers")
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 6, 8, 8)
        self._alarms_container = QWidget()
        self._alarms_layout = QVBoxLayout(self._alarms_container)
        self._alarms_layout.setContentsMargins(0, 0, 0, 0)
        self._alarms_layout.setSpacing(6)
        # Fixed pool of reusable rows — created ONCE, updated in place every poll.
        self._alarm_rows = [_AlarmRow() for _ in range(16)]
        for r in self._alarm_rows:
            self._alarms_layout.addWidget(r)
        self._alarms_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._alarms_container)
        scroll.setMinimumHeight(150)
        v.addWidget(scroll)
        return box

    # ── interaction ──────────────────────────────────────────────────────────
    def _on_step_clicked(self, step: int):
        self._selected_step = step
        self._show_step_detail(step)

    def _show_step_detail(self, step: int):
        phase, short, color = cold_start_info(step)
        self._step_detail.setText(
            f"<b style='color:{color}'>Step {step} — {phase}: {short}</b>"
            f"<br><span style='color:#333355'>{cold_start_detail(step)}</span>")

    # ── update ───────────────────────────────────────────────────────────────
    def update(self, snap: SystemSnapshot, homing_dwell_s: float = 0.0):
        self._update_operation(snap)
        self._box_pallets.set(str(snap.pallets_in_system),
                              "#27ae60" if snap.pallets_in_system > 0 else "#888888")
        self._box_veh_id.set(str(snap.vehicles_id),
                             "#27ae60" if snap.vehicles_id > 0 else "#888888")
        nc_ok = snap.nc_operational >= (snap.max_nc or 1)
        self._box_nc_oper.set(f"{snap.nc_operational} / {snap.max_nc or 1}",
                              "#27ae60" if nc_ok else ("#e74c3c" if snap.nc_operational == 0 else "#e67e22"))
        self._box_molds.set(str(snap.vehicles_at_molds))
        self._box_modules.set(str(snap.modules_in_auto))
        self._box_cmd_count.set(str(snap.cmd_count))

        self._flag_mm_ready.set(snap.mm_ready)
        self._flag_hlc.set(snap.hlc_link)
        self._flag_recovering.set(snap.recovering, "#e67e22", "#555555")
        self._flag_blocked.set(snap.pallet_blocked, "#e74c3c", "#27ae60")
        self._flag_cleanout.set(snap.cleanout, "#f39c12", "#555555")
        self._flag_mold1.set(snap.dest_mold1, "#2980b9", "#555555")
        self._flag_mold2.set(snap.dest_mold2, "#8e44ad", "#555555")

        self._update_homing(snap)
        self._update_alarms(snap, homing_dwell_s)

    def _update_homing(self, snap: SystemSnapshot):
        step = snap.cold_start_step
        # Everything in this group derives only from the step, so skip the whole
        # update (and all its setStyleSheet churn) when the step hasn't changed.
        if step == self._last_step:
            return
        self._last_step = step
        phase, desc, color = cold_start_info(step)

        pct = homing_percent(step)
        self._homing_pct.setValue(pct)
        if step == 5:
            self._homing_pct.setFormat("SYSTEM RUNNING — homing complete")
            chunk = "#27ae60"
        else:
            self._homing_pct.setFormat(f"HOMING… {pct}%  ({phase})")
            chunk = color
        self._homing_pct.setStyleSheet(
            "QProgressBar{background:#e0e3f0;border:1px solid #aaaacc;border-radius:4px;"
            "text-align:center;color:#1a1a2e;font-weight:bold;font-size:11pt;}"
            f"QProgressBar::chunk{{background:{chunk};border-radius:3px;}}")

        self._step_num.setText(f"STEP {step}")
        self._step_num.setStyleSheet(
            f"font-size: 20pt; font-weight: bold; color: {color}; background: transparent;")
        self._step_phase.setText(phase)
        self._step_phase.setStyleSheet(
            f"font-size: 13pt; font-weight: bold; color: {color}; background: transparent;"
            f"border: 1px solid {color}; border-radius: 4px; padding: 3px 9px;")
        self._step_desc.setText(desc)

        active_idx = HOMING_STEP_ORDER.index(step) if step in HOMING_STEP_ORDER else -1
        for i, s in enumerate(HOMING_STEP_ORDER):
            _, _, c = COLD_START_STEPS[s]
            btn = self._step_btns[s]
            if i < active_idx:
                style = f"background:#d4edda;color:{c};border:1px solid {c};"
            elif i == active_idx:
                style = f"background:#f0f2f8;color:{c};border:2px solid {c};font-weight:bold;"
                btn.setChecked(True)
            else:
                style = "background:#f0f2f8;color:#8888aa;border:1px solid #b0b3d0;"
            btn.setStyleSheet("QPushButton{min-width:0px;padding:0 2px;text-align:center;"
                              "border-radius:3px;font-size:8pt;" + style + "}"
                              "QPushButton:hover{border-color:#6666aa;}")

        # detail box follows live step unless the user clicked one
        show = self._selected_step if self._selected_step is not None else step
        self._show_step_detail(show)

    def _update_alarms(self, snap: SystemSnapshot, dwell: float):
        blockers = analyze_status(snap, dwell)
        # Update the fixed row pool in place — no widget creation/destruction.
        for i, row in enumerate(self._alarm_rows):
            if i < len(blockers):
                sev, title, detail = blockers[i]
                row.update_content(sev, title, detail)
            else:
                row.hide()
