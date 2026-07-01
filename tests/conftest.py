"""Shared pytest fixtures for the MagneMotion Monitor test suite.

Qt is forced into the headless 'offscreen' platform so the GUI smoke tests run
without a display (CI-friendly). A single QApplication is created per session
because Qt only allows one.
"""
from __future__ import annotations
import os

# Must be set BEFORE PySide6 is imported anywhere.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from mm_monitor.plc_reader import SystemSnapshot
from mm_monitor.system_data import MAX_VEHICLES, MAX_PATHS, MAX_NC, MAX_STATIONS


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole session (Qt singleton)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _veh(path_id=6, pos=5.5, vel=0.0, dest=14):
    return {
        "Path_ID": path_id,
        "Dest_Path_ID": path_id,
        "Position": pos,
        "Commanded_Position": pos,
        "Velocity": vel,
        "Dest_Station_ID": dest,
        "Command": 0,
        "Flags": 0,
    }


def make_snapshot(**overrides) -> SystemSnapshot:
    """Build a realistic, fully-populated SystemSnapshot for exercising panels.

    Defaults represent a healthy running system with three active carts. Pass
    keyword overrides to set any scalar field (e.g. cold_start_step=17,
    vehicle_fault=True). Use the helpers below for fault/alarm scenarios.
    """
    snap = SystemSnapshot()
    snap.cold_start_step = 5
    snap.hlc_link = True
    snap.mm_ready = True
    snap.nc_operational = 1
    snap.vehicles_id = 3
    snap.pallets_in_system = 3
    snap.max_nc = 1
    snap.max_path = 6
    snap.max_veh = 64
    snap.heartbeat = 1234
    snap.global_vel = 1.0
    snap.global_acc = 2.0
    snap.propulsion_power = True

    # three active carts on the process path
    snap.vehicle_status = [None] * (MAX_VEHICLES + 1)
    snap.vehicle_alarms = [None] * (MAX_VEHICLES + 1)
    snap.vehicle_mgr = [None] * (MAX_VEHICLES + 1)
    for i, (p, pos, vel) in enumerate(
        [(6, 5.5, 0.5), (6, 7.7, 0.0), (2, 3.0, 0.2)], start=1
    ):
        snap.vehicle_status[i] = _veh(p, pos, vel, dest=14)
        snap.vehicle_alarms[i] = {
            "signal": False, "obstructed": False, "hindered": False,
            "suspect": False, "alarm": False, "obstructed_secs": 0.0,
        }
        snap.vehicle_mgr[i] = {
            "dest_station_id": 14, "arrived_station_id": 13,
            "state": 3, "order_number": i,
        }

    # one NC operational, six paths operational
    snap.nc_status = [None] + [{"state": 3} for _ in range(MAX_NC)]
    snap.path_status = [None] + [{"state": 2} for _ in range(MAX_PATHS)]

    # stations 1..34 idle, one occupied
    snap.stations = [None]
    for sid in range(1, MAX_STATIONS):
        snap.stations.append({
            "state": 0, "active_vehicle_id": 0, "occupied": False,
            "process_complete": False, "station_hold_flag": False,
        })
    snap.stations[13]["active_vehicle_id"] = 1
    snap.stations[13]["occupied"] = True

    snap.vehicles_in_path = [0, 0, 1, 0, 0, 0, 2, 0, 0, 0]

    # homing root-cause inputs — healthy defaults (MSG idle, all paths command-complete)
    snap.msg_path_cmd_step = 10
    snap.path_cmd_status = [None] + [128] * MAX_PATHS   # 128 = MMI_CMD_COMPLETE
    snap.cs_cmd_count = 7
    snap.path_cmd_count = [None] + [7] * MAX_PATHS      # all matched to cs_cmd_count
    snap.cs_timer_acc = 0
    snap.cs_timer_pre = 0

    for k, v in overrides.items():
        setattr(snap, k, v)
    return snap


@pytest.fixture
def snapshot() -> SystemSnapshot:
    return make_snapshot()
