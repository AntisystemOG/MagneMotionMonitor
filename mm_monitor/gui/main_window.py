from __future__ import annotations
import threading
import time
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QStatusBar, QFileDialog, QPushButton, QButtonGroup, QLabel, QSizePolicy,
)
from PySide6.QtCore import QTimer, QObject, Signal, Qt
from PySide6.QtGui import QAction

from .. import crash_handler
from ..plc_reader import PLCReader, SystemSnapshot
from ..recording import Recorder, Recording, RECORDINGS_DIR
from ..system_data import cold_start_info, homing_active, current_operation, APP_VERSION
from .connection_bar import ConnectionBar
from .record_bar import RecordBar
from .system_panel import SystemPanel
from .pallet_panel import PalletPanel
from .station_panel import StationPanel
from .path_nc_panel import PathNCPanel
from .motion_panel import MotionPanel
from .track_panel import TrackPanel
from .raw_panel import RawTagsPanel
from .log_panel import EventLogPanel
from .theme import STYLESHEET


class _SysBar(QWidget):
    """Slim borderless stat strip that sits flush above the track canvas."""

    _BG = "#f0f4ff"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet(f"background: {self._BG}; border: none;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(0)

        def _lbl(text="", bold=False, size=10, color="#1a1a2e") -> QLabel:
            l = QLabel(text)
            w = "bold" if bold else "normal"
            l.setStyleSheet(
                f"background:transparent; color:{color}; "
                f"font-size:{size}pt; font-weight:{w}; border:none;")
            return l

        self._op_dot  = _lbl("●", size=14, color="#888888")
        self._op_name = _lbl("—", bold=True, size=11)
        lay.addWidget(self._op_dot)
        lay.addSpacing(6)
        lay.addWidget(self._op_name)

        def _sep():
            s = _lbl("  |  ", color="#b0b3d0")
            return s

        lay.addWidget(_sep())
        self._lbl_pallets  = _lbl()
        self._lbl_vehicles = _lbl()
        self._lbl_ncs      = _lbl()
        self._lbl_faults   = _lbl(color="#c0392b", bold=True)

        for w in (self._lbl_pallets, _sep(),
                  self._lbl_vehicles, _sep(),
                  self._lbl_ncs):
            lay.addWidget(w)

        lay.addSpacing(20)
        lay.addWidget(self._lbl_faults)
        lay.addStretch()

    def update(self, snap: SystemSnapshot):
        op = current_operation(snap)
        self._op_dot.setStyleSheet(
            f"background:transparent; color:{op['color']}; "
            f"font-size:14pt; font-weight:bold; border:none;")
        name = op["name"]
        if op["active"]:
            name += f"  {op['pct']}%"
        self._op_name.setText(name)
        self._op_name.setStyleSheet(
            f"background:transparent; color:{op['color']}; "
            f"font-size:11pt; font-weight:bold; border:none;")

        self._lbl_pallets.setText(f"Pallets: {snap.pallets_in_system}")
        self._lbl_vehicles.setText(f"Vehicles: {snap.vehicles_id}")
        self._lbl_ncs.setText(f"NCs: {snap.nc_operational}/{snap.max_nc}")

        faults = []
        if snap.vehicle_fault: faults.append("VEH FAULT")
        if snap.motor_fault:   faults.append("MOTOR FAULT")
        self._lbl_faults.setText("  ⚠ " + "  ⚠ ".join(faults) if faults else "")


class _Sig(QObject):
    connected  = Signal(bool, str)
    snapshot   = Signal(object)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from PySide6.QtGui import QIcon
        self.setWindowIcon(QIcon("src/resources/app_icon.png"))
        self._reader  = PLCReader()
        self._signals = _Sig()
        self._prev_step: int = 5
        self._prev_hlc: bool = False
        self._prev_ready: bool = False
        self._prev_pallet_states: dict[int, str] = {}
        self._dwell_step: int = 5
        self._dwell_since: float = time.monotonic()

        # record / playback
        self._recorder = Recorder()
        self._recording: Recording | None = None
        self._playing = False
        self._play_clock = 0.0
        self._play_speed = 1.0
        self._play_idx = 0

        self.setWindowTitle(f"MagneMotion Monitor — Boxing Station   v{APP_VERSION}")
        self.setMinimumSize(960, 700)
        self.setStyleSheet(STYLESHEET)

        self._build_menu()
        self._build_ui()
        self._wire()


    # ── construction ─────────────────────────────────────────────────────────

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        self._conn_bar = ConnectionBar()
        vbox.addWidget(self._conn_bar)

        self._record_bar = RecordBar()
        vbox.addWidget(self._record_bar)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #b0b3d0;")
        vbox.addWidget(sep)

        # ── main area: left nav + content stack ──────────────────────────────
        main_area = QWidget()
        main_hbox = QHBoxLayout(main_area)
        main_hbox.setContentsMargins(0, 0, 0, 0)
        main_hbox.setSpacing(0)

        # Left nav panel — plain buttons, horizontal text
        nav_panel = QWidget()
        nav_panel.setFixedWidth(155)
        nav_panel.setStyleSheet(
            "QWidget { background-color: #e0e3f0; border-right: 1px solid #b0b3d0; }")
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(6, 10, 6, 10)
        nav_layout.setSpacing(3)

        self._stack = QStackedWidget()

        _NAV_BTN = (
            "QPushButton {"
            "  background-color: transparent; color: #333355;"
            "  border: none; border-radius: 5px;"
            "  padding: 10px 14px; font-size: 10pt; text-align: left;"
            "}"
            "QPushButton:hover { background-color: #d0d5eb; }"
            "QPushButton:checked {"
            "  background-color: #c5cae9; color: #1a1a2e; font-weight: bold;"
            "  border-left: 3px solid #e94560;"
            "}"
        )

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        _nav_labels = [
            "Overview", "System", "Pallet Tracker", "Motion / Speed",
            "Stations", "Paths & NCs", "Raw Tags", "Event Log",
        ]
        for i, label in enumerate(_nav_labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(_NAV_BTN)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFlat(True)
            btn.clicked.connect(lambda _=False, idx=i: self._stack.setCurrentIndex(idx))
            self._nav_group.addButton(btn, i)
            nav_layout.addWidget(btn)
        nav_layout.addStretch()
        self._nav_group.button(0).setChecked(True)

        main_hbox.addWidget(nav_panel)
        main_hbox.addWidget(self._stack, 1)
        vbox.addWidget(main_area, 1)

        # ── panels ───────────────────────────────────────────────────────────
        self._sys_panel    = SystemPanel()
        # Ignored tells QStackedWidget not to use sys_panel's wide minimum
        # when computing the stack's own minimum — the panel still renders fine.
        self._sys_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self._pallet_panel = PalletPanel()
        self._track_panel  = TrackPanel()
        self._motion_panel = MotionPanel()
        self._station_panel= StationPanel()
        self._path_nc_panel= PathNCPanel()
        self._raw_panel    = RawTagsPanel()
        self._log_panel    = EventLogPanel()

        # Overview: slim borderless stat bar flush above the track — no dividers
        self._sys_bar = _SysBar()
        overview_widget = QWidget()
        overview_widget.setStyleSheet("background: #f0f4ff; border: none;")
        ov_layout = QVBoxLayout(overview_widget)
        ov_layout.setContentsMargins(0, 0, 0, 0)
        ov_layout.setSpacing(0)
        ov_layout.addWidget(self._sys_bar)
        ov_layout.addWidget(self._track_panel, 1)

        self._stack.addWidget(overview_widget)      # 0 – Overview
        self._stack.addWidget(self._sys_panel)      # 1 – System
        self._stack.addWidget(self._pallet_panel)   # 2 – Pallet Tracker
        self._stack.addWidget(self._motion_panel)   # 3 – Motion / Speed
        self._stack.addWidget(self._station_panel)  # 4 – Stations
        self._stack.addWidget(self._path_nc_panel)  # 5 – Paths & NCs
        self._stack.addWidget(self._raw_panel)      # 6 – Raw Tags
        self._stack.addWidget(self._log_panel)      # 7 – Event Log

        self.setStatusBar(QStatusBar())

        # Single persistent poll thread (NOT a new thread per tick — that pileup
        # crashed the app when reads ran longer than the interval while connected).
        self._poll_stop = threading.Event()
        self._poll_thread: threading.Thread | None = None

        self._play_timer = QTimer(self)
        self._play_timer.setInterval(50)
        self._play_timer.timeout.connect(self._play_tick)

    def _wire(self):
        self._conn_bar.connect_requested.connect(self._on_connect)
        self._conn_bar.disconnect_requested.connect(self._on_disconnect)
        self._conn_bar.minimize_requested.connect(self._on_minimize_requested)
        self._signals.connected.connect(self._on_connect_result)
        self._signals.snapshot.connect(self._on_snapshot)
        self._record_bar.record_clicked.connect(self._on_record_clicked)
        self._record_bar.load_clicked.connect(self._on_load_clicked)
        self._record_bar.play_clicked.connect(self._on_play_clicked)
        self._record_bar.seek.connect(self._on_seek)
        self._record_bar.skip_seconds.connect(self._on_skip_seconds)
        self._record_bar.speed_changed.connect(self._on_speed_changed)
        self._track_panel.open_system_detail.connect(
            lambda: self._nav_group.button(1).setChecked(True) or
                    self._stack.setCurrentIndex(1))

    # ── minimize / camera view ───────────────────────────────────────────────

    def _on_minimize_requested(self, secs: int):
        self.showMinimized()
        QTimer.singleShot(secs * 1000, self._restore_from_minimize)

    def _restore_from_minimize(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    # ── connection ───────────────────────────────────────────────────────────

    def _on_connect(self, ip: str):
        self._conn_bar.set_connected(False, "Connecting…")
        self.statusBar().showMessage("Connecting…")
        threading.Thread(target=self._connect_worker, args=(ip,), daemon=True).start()

    def _connect_worker(self, ip: str):
        ok, msg = self._reader.connect(ip)
        self._signals.connected.emit(ok, msg)

    def _on_connect_result(self, ok: bool, msg: str):
        self._conn_bar.set_connected(ok, msg)
        self.statusBar().showMessage(msg)
        if ok:
            self._stop_playback()
            self._log_panel.log_info(f"Connected — {msg}")
            self._start_poll_thread()
        self._record_bar.set_mode(connected=ok, playback=self._recording is not None)

    def _on_disconnect(self):
        self._stop_poll_thread()
        self._reader.disconnect()
        # A new connection should never show carts "held" over from this session.
        self._track_panel.reset_smoothing()
        if self._recorder.active:
            self._recorder.stop()
            self._record_bar.set_recording(False)
            self._log_panel.log_info(f"Recording stopped ({self._recorder.count} frames)")
        self._conn_bar.set_connected(False, "Disconnected")
        self.statusBar().showMessage("Disconnected")
        self._log_panel.log_info("Disconnected")
        self._record_bar.set_mode(connected=False, playback=self._recording is not None)

    # ── polling ──────────────────────────────────────────────────────────────

    def _start_poll_thread(self):
        self._stop_poll_thread()
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _stop_poll_thread(self):
        self._poll_stop.set()   # the loop checks this; reader.disconnect() unblocks any read
        self._poll_thread = None

    def _poll_loop(self):
        """One persistent thread: read → emit → wait. Never piles up because the
        next read only starts after the previous finishes plus the interval."""
        interval = 0.75
        while not self._poll_stop.is_set():
            t0 = time.monotonic()
            try:
                snap = self._reader.poll()
                if not self._poll_stop.is_set():
                    self._signals.snapshot.emit(snap)
            except Exception:
                pass
            # wait the remainder of the interval, but wake immediately on stop
            remaining = interval - (time.monotonic() - t0)
            self._poll_stop.wait(remaining if remaining > 0.05 else 0.05)

    def _safe(self, name: str, fn, *args):
        """Run a panel update; on error, log+popup but keep the app alive."""
        try:
            fn(*args)
        except Exception:
            crash_handler.report_context(f"updating panel: {name}")

    def _on_snapshot(self, snap: SystemSnapshot, from_playback: bool = False):
        # capture to the recording file when live (never while replaying)
        if self._recorder.active and not from_playback:
            self._recorder.add(snap)
            self._record_bar.set_recording(True, self._recorder.count, self._recorder.elapsed)

        # track how long the cold-start routine has sat on the current step
        if snap.cold_start_step != self._dwell_step:
            self._dwell_step = snap.cold_start_step
            self._dwell_since = time.monotonic()
        dwell = time.monotonic() - self._dwell_since

        self._safe("System Overview", self._sys_panel.update, snap, dwell)
        self._safe("SysBar", self._sys_bar.update, snap)
        # Live polls feed the dead-reckoning animator (smooths motion between
        # polls); playback/discrete jumps show the exact recorded position —
        # continuous playback interpolation is driven separately by _play_tick.
        if from_playback:
            self._safe("Live Track", self._track_panel.update, snap)
        else:
            self._safe("Live Track", self._track_panel.feed_live_snapshot, snap)
        self._safe("Pallet Tracker",  self._pallet_panel.update, snap)
        self._safe("Motion / Speed",  self._motion_panel.update, snap)
        self._safe("Stations",        self._station_panel.update, snap)
        self._safe("Paths & NCs",     self._path_nc_panel.update, snap)

        # Build raw tags dict from snapshot scalars + key arrays
        raw: dict[str, tuple[str, object]] = {
            "cold_start_service.step":  ("INT",  snap.cold_start_step),
            "Recovering_Pallets":        ("BOOL", snap.recovering),
            "hlc_link_status":           ("BOOL", snap.hlc_link),
            "nc_operational":            ("INT",  snap.nc_operational),
            "Vehicles_Indentified":      ("DINT", snap.vehicles_id),
            "Pallets_In_System":         ("DINT", snap.pallets_in_system),
            "MagneMotion_Ready":         ("BOOL", snap.mm_ready),
            "MagneMotion_Pallet_Blocked":("BOOL", snap.pallet_blocked),
            "Vehicles_at_Molds":         ("DINT", snap.vehicles_at_molds),
            "Homing_Pallets":            ("DINT", snap.homing_count),
            "Destination_Mold1":         ("BOOL", snap.dest_mold1),
            "Destination_Mold2":         ("BOOL", snap.dest_mold2),
            "CleanoutPallets":           ("BOOL", snap.cleanout),
            "Modules_In_Automation":     ("DINT", snap.modules_in_auto),
            "master_command_count":      ("DINT", snap.cmd_count),
            "MMI_heartbeat":             ("DINT", snap.heartbeat),
            "MM_Global_Velocity":        ("REAL", snap.global_vel),
            "MM_Global_Acc":             ("REAL", snap.global_acc),
        }
        for i in range(1, len(snap.vehicle_status)):
            if snap.vehicle_status[i]:
                raw[f"MMI_vehicle_status[{i}]"] = ("UDT", snap.vehicle_status[i])
        for i in range(1, len(snap.path_status)):
            if snap.path_status[i]:
                raw[f"MMI_path_status[{i}]"] = ("UDT", snap.path_status[i])
        for i in range(1, len(snap.nc_status)):
            if snap.nc_status[i]:
                raw[f"MMI_node_controller_status[{i}]"] = ("UDT", snap.nc_status[i])

        self._safe("Raw Tags",  self._raw_panel.update_tags, raw)
        self._safe("Event Log", self._check_events, snap)

    # ── event detection ───────────────────────────────────────────────────────

    def _check_events(self, snap: SystemSnapshot):
        # Cold start step change
        if snap.cold_start_step != self._prev_step:
            _, desc, _ = cold_start_info(snap.cold_start_step)
            self._log_panel.log_info(f"Homing step → {snap.cold_start_step}: {desc}")
            if snap.cold_start_step == 5 and self._prev_step != 5:
                self._log_panel.log_homing_complete(snap.pallets_in_system)
            self._prev_step = snap.cold_start_step

        # HLC link change
        if snap.hlc_link != self._prev_hlc:
            if snap.hlc_link:
                self._log_panel.log_info("HLC link UP")
            else:
                self._log_panel.log_fault(0, "HLC link DOWN — lost communication with Node Controller")
            self._prev_hlc = snap.hlc_link

        # System ready change
        if snap.mm_ready != self._prev_ready:
            msg = "MagneMotion_Ready → TRUE" if snap.mm_ready else "MagneMotion_Ready → FALSE"
            self._log_panel.log_info(msg)
            self._prev_ready = snap.mm_ready

        # Pallet blocked
        if snap.pallet_blocked:
            pass  # log only once — state change would repeat; use a latch if needed

    # ── record / playback ──────────────────────────────────────────────────────

    def _on_record_clicked(self):
        if self._recorder.active:
            self._recorder.stop()
            self._record_bar.set_recording(False)
            self._log_panel.log_info(f"Recording saved: {self._recorder.path} "
                                     f"({self._recorder.count} frames)")
            return
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        default = str(RECORDINGS_DIR / time.strftime("rec_%Y%m%d_%H%M%S.mmrec"))
        path, _ = QFileDialog.getSaveFileName(self, "Save Recording", default,
                                              "MagneMotion recording (*.mmrec)")
        if path:
            if self._recorder.start(path):
                self._record_bar.set_recording(True, 0, 0.0)
                self._log_panel.log_info(f"Recording started: {path}")
            else:
                self._log_panel.log_fault(0, "Could not start recording (file error)")

    def _on_load_clicked(self):
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Load Recording", str(RECORDINGS_DIR),
                                              "MagneMotion recording (*.mmrec);;All files (*)")
        if not path:
            return
        try:
            self._recording = Recording.load(path)
        except Exception:
            crash_handler.report_context(f"loading recording: {path}")
            return
        if len(self._recording) == 0:
            self._log_panel.log_fault(0, "Recording is empty")
            self._recording = None
            return
        self._play_idx = 0
        self._play_clock = 0.0
        self._playing = False
        self._track_panel.reset_smoothing()   # don't carry held carts from a prior session
        self._record_bar.set_mode(connected=False, playback=True)
        self._record_bar.set_total_frames(len(self._recording), self._recording.duration)
        self._record_bar.set_position(0, 0.0)
        self._render_frame(0)
        self.statusBar().showMessage(
            f"Playback: {len(self._recording)} frames, {self._recording.duration:.1f}s — {path}")
        self._log_panel.log_info(f"Loaded recording: {path} ({len(self._recording)} frames)")

    def _on_play_clicked(self):
        if not self._recording:
            return
        self._playing = not self._playing
        self._record_bar.set_playing(self._playing)
        if self._playing:
            # restart from beginning if parked at the end
            if self._play_idx >= len(self._recording) - 1:
                self._play_idx = 0
                self._play_clock = 0.0
            self._play_timer.start()
        else:
            self._play_timer.stop()

    def _on_seek(self, idx: int):
        if not self._recording:
            return
        idx = max(0, min(idx, len(self._recording) - 1))
        self._play_idx = idx
        self._play_clock = self._recording.time_at(idx)
        # A seek breaks the "sequential polls" assumption CartPresenceGuard
        # relies on (it could jump backward in time) — forget any held carts
        # so resuming playback afterward doesn't inject stale ones.
        self._track_panel.reset_smoothing()
        self._render_frame(idx)

    def _on_skip_seconds(self, delta: float):
        if not self._recording:
            return
        t = max(0.0, min(self._play_clock + delta, self._recording.duration))
        idx = self._recording.index_for_time(t)
        self._play_idx = idx
        self._play_clock = t
        self._track_panel.reset_smoothing()   # see _on_seek
        self._render_frame(idx)

    def _on_speed_changed(self, speed: float):
        self._play_speed = speed

    def _play_tick(self):
        if not self._recording:
            self._play_timer.stop()
            return
        self._play_clock += (self._play_timer.interval() / 1000.0) * self._play_speed
        idx = self._recording.index_for_time(self._play_clock)
        if idx != self._play_idx:
            self._play_idx = idx
            self._render_frame(idx)   # full panel refresh (tables/log/etc) on each new frame
        # Every tick (not just on a frame change): interpolate the track view
        # between the two recorded frames straddling the playhead, so cart
        # motion is smooth at the 50ms tick rate instead of stepping once per
        # recorded frame (which can be under 1 fps depending on record interval).
        self._update_track_interpolated()
        if idx >= len(self._recording) - 1:   # reached the end
            self._playing = False
            self._play_timer.stop()
            self._record_bar.set_playing(False)

    def _render_frame(self, idx: int):
        snap = self._recording.snapshot(idx)
        self._record_bar.set_position(idx, self._recording.time_at(idx))
        self._on_snapshot(snap, from_playback=True)

    def _update_track_interpolated(self):
        """Feed the track panel the current + next recorded frame plus how far
        the playhead sits between their timestamps, so it can interpolate exact
        cart positions rather than holding the last frame's position until the
        next one arrives. Safe to call even when idx hasn't advanced this tick,
        and even when paused (frac stays fixed at the current playhead time)."""
        if not self._recording:
            return
        idx = self._play_idx
        cur_t = self._recording.time_at(idx)
        cur_snap = self._recording.snapshot(idx)
        if idx + 1 < len(self._recording):
            next_t = self._recording.time_at(idx + 1)
            next_snap = self._recording.snapshot(idx + 1)
            span = next_t - cur_t
            frac = 0.0 if span <= 0 else max(0.0, min(1.0, (self._play_clock - cur_t) / span))
        else:
            next_snap, frac = None, 0.0
        self._safe("Live Track (playback)", self._track_panel.update_playback,
                   cur_snap, next_snap, frac)

    def _stop_playback(self):
        self._playing = False
        self._play_timer.stop()
        self._record_bar.set_playing(False)
