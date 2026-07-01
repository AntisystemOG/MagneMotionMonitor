"""GUI smoke tests — the regression guard for the hard Qt widget-churn crashes.

History (see PROJECT_MEMORY.md): this app hard-crashed when widgets were created
or destroyed inside per-poll update callbacks. The fix was to update widget pools
in place. These tests push many snapshots — including the exact changing-every-tick
patterns that triggered the original crashes — through every panel and assert the
app survives.
"""
from __future__ import annotations
import pytest

from mm_monitor.gui.main_window import MainWindow
from mm_monitor.gui.system_panel import SystemPanel
from mm_monitor.gui.pallet_panel import PalletPanel
from mm_monitor.gui.station_panel import StationPanel
from mm_monitor.gui.path_nc_panel import PathNCPanel
from mm_monitor.gui.motion_panel import MotionPanel
from mm_monitor.gui.track_panel import TrackPanel
from mm_monitor.recording import Recording
from mm_monitor.system_data import HOMING_STEP_ORDER
from tests.conftest import make_snapshot


# ── individual panels ────────────────────────────────────────────────────────

@pytest.mark.parametrize("panel_cls", [
    SystemPanel, PalletPanel, StationPanel, PathNCPanel, MotionPanel, TrackPanel,
])
def test_panel_builds_and_updates(qapp, panel_cls):
    panel = panel_cls()
    snap = make_snapshot()
    # SystemPanel.update takes an extra dwell arg; others take just the snapshot
    if panel_cls is SystemPanel:
        panel.update(snap, 0.0)
    else:
        panel.update(snap)


# ── main window end-to-end ───────────────────────────────────────────────────

@pytest.fixture
def window(qapp):
    w = MainWindow()
    yield w
    w.close()


def test_mainwindow_builds(window):
    assert window._stack.count() == 8


def test_snapshot_routes_through_all_panels(window):
    window._on_snapshot(make_snapshot(), from_playback=True)


@pytest.mark.parametrize("scenario", [
    {"cold_start_step": 5},                       # idle / running
    {"cold_start_step": 17},                      # homing, waiting on NC
    {"cold_start_step": 100},                     # homing, last step
    {"vehicle_fault": True},                       # real fault bit
    {"motor_fault": True},                         # real fault bit
    {"hlc_link": False},                           # comms down
    {"pallets_in_system": 0, "vehicles_id": 0},   # empty system
    {"pallet_blocked": True},
])
def test_snapshot_scenarios_do_not_crash(window, scenario):
    window._on_snapshot(make_snapshot(**scenario), from_playback=True)


def test_jammed_and_queued_carts_render(window):
    snap = make_snapshot()
    snap.vehicle_alarms[1]["alarm"] = True       # jammed (red)
    snap.vehicle_alarms[2]["obstructed"] = True  # queued (benign)
    snap.vehicle_alarms[3]["hindered"] = True
    window._on_snapshot(snap, from_playback=True)


def test_motor_faults_render_in_paths_panel(window):
    snap = make_snapshot()
    snap.motor_faults = [
        {"path": 6, "motor": 4, "motor_states": ["Stopped (FastStop)"],
         "comm": [], "boards": [], "serious": True},
        {"path": 2, "motor": 1, "motor_states": ["In Config Mode"],
         "comm": [], "boards": ["driver board 3"], "serious": False},
    ]
    window._on_snapshot(snap, from_playback=True)
    text = window._path_nc_panel._mf_label.text()
    assert "Path 6" in text and "Motor 4" in text
    # clean snapshot resets the label
    window._on_snapshot(make_snapshot(), from_playback=True)
    assert window._path_nc_panel._mf_label.text() == "No motor faults."


# ── the actual crash patterns (changing-every-tick churn) ────────────────────

def test_repeated_identical_snapshots(window):
    """Per-poll churn: pushing the same snapshot many times must not accumulate
    or destroy widgets (the original hard-crash trigger)."""
    snap = make_snapshot()
    for _ in range(50):
        window._on_snapshot(snap, from_playback=True)


def test_homing_dwell_ticking_every_second(window):
    """The v0.6.1 crash: the 'Homing stuck at step N for Xs' alarm title changes
    every second, which used to rebuild alarm-row widgets each tick. Push a
    steadily increasing dwell and assert survival."""
    for secs in range(0, 120, 3):
        window._sys_panel.update(make_snapshot(cold_start_step=17), float(secs))


def test_cart_count_changing_each_poll(window):
    """Carts appearing/disappearing each poll stresses the track + tables."""
    for n in [0, 1, 5, 3, 8, 0, 2]:
        snap = make_snapshot(pallets_in_system=n, vehicles_id=n)
        # keep only the first n carts active
        for i in range(1, len(snap.vehicle_status)):
            if i > n and snap.vehicle_status[i] is not None:
                snap.vehicle_status[i] = None
                snap.vehicle_alarms[i] = None
        window._on_snapshot(snap, from_playback=True)


# ── live dead-reckoning + playback interpolation (churn safety) ──────────────

def test_live_snapshot_feeds_dead_reckoning_animator(window):
    """The genuine live path (from_playback=False) must route through the
    animator, not the exact-placement path, and repeated polls + repeated
    animation ticks (simulating the 30fps repaint timer) must not crash."""
    for i in range(30):
        snap = make_snapshot()
        snap.vehicle_status[1]["Position"] = 5.0 + i * 0.05
        window._on_snapshot(snap, from_playback=False)
        window._track_panel._canvas._on_anim_tick()   # simulate an animation frame


def test_playback_ticking_interpolates_without_crashing(window):
    """Drive a small in-memory recording through the real playback tick path
    (_play_tick -> _update_track_interpolated) the way the 50ms QTimer would,
    including ticks that land between recorded frames and the final frame
    where there is no 'next' frame to interpolate towards."""
    frames = [(float(i), make_snapshot(pallets_in_system=i + 1)) for i in range(5)]
    window._recording = Recording(frames)
    window._play_idx = 0
    window._play_clock = 0.0
    window._playing = True
    window._play_timer.stop()   # drive ticks manually instead of via the real timer
    for _ in range(40):         # 40 * 50ms = 2s of playback across a 4s recording
        window._play_tick()


def test_playback_reaching_the_end_stops_cleanly(window):
    frames = [(0.0, make_snapshot()), (0.05, make_snapshot())]
    window._recording = Recording(frames)
    window._play_idx = 0
    window._play_clock = 0.0
    window._playing = True
    for _ in range(10):   # well past the recording's 0.05s duration
        window._play_tick()
    assert window._playing is False


# ── real track photo rendering (new paintEvent code path) ────────────────────

def test_track_canvas_finds_the_real_photo(qapp):
    """The bundled track photo should be picked up automatically — if this
    starts failing, check mm_monitor/data/track_photo.png wasn't moved/renamed."""
    panel = TrackPanel()
    assert panel._canvas._photo_pixmap is not None
    assert panel._canvas._photo_model is not None


def test_photo_mode_renders_across_many_live_polls_and_anim_ticks(window):
    """Churn-safety check for the photo paintEvent path specifically (draws a
    QPixmap + calibrated overlay every frame instead of schematic polylines)."""
    assert window._track_panel._canvas._photo_pixmap is not None
    for i in range(30):
        snap = make_snapshot()
        snap.vehicle_status[1]["Path_ID"] = 2   # Mold 1 spur
        snap.vehicle_status[1]["Position"] = 2.5 + i * 0.05
        snap.vehicle_status[2]["Path_ID"] = 4   # Mold 2 spur
        window._on_snapshot(snap, from_playback=False)
        window._track_panel._canvas._on_anim_tick()


def test_photo_mode_playback_interpolation_does_not_crash(window):
    frames = [(float(i), make_snapshot(pallets_in_system=i + 1)) for i in range(4)]
    window._recording = Recording(frames)
    window._play_idx = 0
    window._play_clock = 0.0
    for _ in range(20):
        window._play_tick()


# ── carts held in place during Homing/Cleaning (CartPresenceGuard) ───────────

def test_cart_stays_visible_when_hlc_drops_it_mid_homing(window):
    """The core scenario reported: during Homing, the HLC temporarily stops
    reporting a physically-present cart's Path_ID. It must stay on the Live
    Track (held at its last position), not vanish."""
    present = make_snapshot(cold_start_step=17)   # homing in progress
    window._on_snapshot(present, from_playback=False)
    window._track_panel._canvas._on_anim_tick()
    assert len(window._track_panel._canvas._carts) >= 1

    missing = make_snapshot(cold_start_step=18)   # still homing; HLC drops the carts
    for i in range(1, len(missing.vehicle_status)):
        missing.vehicle_status[i] = None
        missing.vehicle_alarms[i] = None
    window._on_snapshot(missing, from_playback=False)
    held_carts = window._track_panel._canvas._animator.tick(1e18)
    assert len(held_carts) >= 1
    assert all(c.held for c in held_carts)


def test_cart_disappears_normally_outside_homing(window):
    """Outside an active operation, a cart the PLC stops reporting really did
    leave — the guard must not hold it forever."""
    present = make_snapshot(cold_start_step=5)   # running normally
    window._on_snapshot(present, from_playback=False)

    missing = make_snapshot(cold_start_step=5)
    for i in range(1, len(missing.vehicle_status)):
        missing.vehicle_status[i] = None
        missing.vehicle_alarms[i] = None
    window._on_snapshot(missing, from_playback=False)
    held_carts = window._track_panel._canvas._animator.tick(1e18)
    assert held_carts == []


def test_homing_with_intermittent_carts_does_not_crash(window):
    """Churn-safety: carts flickering in and out during a full homing sequence
    (the real-world pattern this feature targets) across many polls."""
    import mm_monitor.system_data as sd
    for i, step in enumerate(sd.HOMING_STEP_ORDER):
        snap = make_snapshot(cold_start_step=step)
        if i % 2 == 0:   # every other poll, the HLC drops all carts
            for vid in range(1, len(snap.vehicle_status)):
                snap.vehicle_status[vid] = None
                snap.vehicle_alarms[vid] = None
        window._on_snapshot(snap, from_playback=False)
        window._track_panel._canvas._on_anim_tick()


def test_system_panel_homing_steps_restyle(qapp):
    """Walk every homing step so each branch of the step-button restyle runs
    (this is where the global theme's min-width could leak back in)."""
    panel = SystemPanel()
    for step in HOMING_STEP_ORDER:
        panel.update(make_snapshot(cold_start_step=step), 1.0)
    # Buttons must stay pinned at their fixed width and never inherit the global
    # theme's min-width: 80px (which historically leaked back in on live restyle
    # and ballooned them). They are set to a fixed 92px.
    for b in panel._step_btns.values():
        assert b.maximumWidth() == 92
