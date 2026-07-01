"""Logic tests for system_data — the analysis/decoding functions that drive the UI."""
from __future__ import annotations
import pytest

from mm_monitor import system_data as sd
from tests.conftest import make_snapshot


# ── vehicle alarm decoding ───────────────────────────────────────────────────

def test_decode_alarm_from_int_bits():
    a = sd.decode_vehicle_alarm(0x10 | 0x02)  # AlarmPresent + Obstructed
    assert a["alarm"] is True
    assert a["obstructed"] is True
    assert a["hindered"] is False


def test_decode_alarm_from_udt_dict():
    a = sd.decode_vehicle_alarm({"AlarmPresent": True, "Hindered": True})
    assert a["alarm"] is True
    assert a["hindered"] is True
    assert a["suspect"] is False


def test_decode_alarm_garbage_is_all_false():
    a = sd.decode_vehicle_alarm(None)
    assert not any(a.values())


# ── alarm kind priority (the jam-vs-queue nuance) ────────────────────────────

def test_alarm_present_is_jammed():
    kind = sd.vehicle_alarm_kind({"alarm": True, "obstructed": True})
    assert kind == "jammed"


def test_obstructed_alone_is_queued_not_jammed():
    kind = sd.vehicle_alarm_kind({"obstructed": True})
    assert kind == "queued"


def test_no_alarm_is_none():
    assert sd.vehicle_alarm_kind({"signal": False}) is None
    assert sd.vehicle_alarm_kind(None) is None


# ── homing percent ───────────────────────────────────────────────────────────

def test_homing_percent_idle_is_complete():
    assert sd.homing_percent(5) == 100


def test_homing_percent_monotonic_through_sequence():
    pcts = [sd.homing_percent(s) for s in sd.HOMING_SEQUENCE]
    assert pcts == sorted(pcts)
    assert pcts[-1] == 100  # step 100 = fully done


def test_homing_percent_unknown_step_falls_back():
    # a step not in the sequence should not raise and stays in range
    assert 0 <= sd.homing_percent(42) <= 100


# ── current_operation banner logic ───────────────────────────────────────────

def test_operation_running_when_idle_with_pallets():
    op = sd.current_operation(make_snapshot())
    assert op["name"] == "RUNNING"
    assert op["active"] is False


def test_operation_homing_when_cold_start_running():
    op = sd.current_operation(make_snapshot(cold_start_step=17))
    assert "HOMING" in op["name"]
    assert op["active"] is True
    assert 0 <= op["pct"] <= 100


def test_operation_cleaning_progress():
    snap = make_snapshot(cold_start_step=5, cleanout=True, pallets_in_system=4)
    snap.vehicles_in_path[3] = 2
    op = sd.current_operation(snap)
    assert op["name"] == "CLEANING PALLETS"
    assert op["pct"] == 50


def test_operation_idle_when_no_pallets():
    op = sd.current_operation(make_snapshot(pallets_in_system=0))
    assert op["name"] == "IDLE"


# ── analyze_status (alarm/blocker list) ──────────────────────────────────────

def test_analyze_clean_system_reports_no_alarms():
    out = sd.analyze_status(make_snapshot())
    assert len(out) == 1
    sev, title, _ = out[0]
    assert sev == "info"
    assert "No active alarms" in title


def test_analyze_flags_vehicle_fault_as_critical():
    out = sd.analyze_status(make_snapshot(vehicle_fault=True))
    assert any(sev == "critical" and "Vehicle Fault" in title for sev, title, _ in out)


def test_analyze_flags_hlc_down():
    out = sd.analyze_status(make_snapshot(hlc_link=False))
    assert any("HLC link DOWN" in title for _, title, _ in out)


def test_analyze_jammed_pallet_from_alarm_present():
    snap = make_snapshot()
    snap.vehicle_alarms[2]["alarm"] = True
    out = sd.analyze_status(snap)
    assert any("JAMMED" in title for _, title, _ in out)


def test_analyze_obstructed_is_queued_never_jammed():
    snap = make_snapshot()
    snap.vehicle_alarms[2]["obstructed"] = True
    out = sd.analyze_status(snap)
    titles = " ".join(t for _, t, _ in out)
    assert "queued" in titles
    assert "JAMMED" not in titles


def test_analyze_nc_not_operational_during_homing_is_critical():
    snap = make_snapshot(cold_start_step=17)
    snap.nc_status[1] = {"state": 1}  # INIT, not OPERATIONAL
    out = sd.analyze_status(snap)
    assert any(sev == "critical" and "Node Controller" in title for sev, title, _ in out)


def test_analyze_homing_dwell_warning():
    out = sd.analyze_status(make_snapshot(cold_start_step=17), homing_dwell_s=45)
    assert any("stuck at step 17" in title for _, title, _ in out)


# ── motor / driver-board fault decoding ──────────────────────────────────────

def _ml(**bits):
    """Build a MMI_path_ml_faults_status element with all members zero except given."""
    elem = {
        "OS_Scheduler": 0, "Upstream_Comm": 0, "Downstream_Comm": 0,
        "Motor_Overall": 0, "Master_Board_Faults_A": 0, "Master_Board_Faults_B": 0,
    }
    for n in range(1, 9):
        elem[f"Driver_Board_{n}_Faults"] = 0
    elem.update(bits)
    return elem


def test_decode_motor_clean_is_none():
    assert sd.decode_motor_fault(_ml()) is None
    assert sd.decode_motor_fault(None) is None


def test_decode_motor_stopped_is_serious():
    f = sd.decode_motor_fault(_ml(Motor_Overall=1 << 4))   # Stopped (FastStop)
    assert f["serious"] is True
    assert "Stopped (FastStop)" in f["motor_states"]


def test_decode_motor_not_responding_is_serious():
    f = sd.decode_motor_fault(_ml(Motor_Overall=1 << 7))   # bit 7 = Not Responding
    assert f["serious"] is True
    assert "Not Responding" in f["motor_states"]


def test_decode_motor_config_mode_is_not_serious():
    f = sd.decode_motor_fault(_ml(Motor_Overall=1 << 1))   # In Config Mode
    assert f["serious"] is False
    assert "In Config Mode" in f["motor_states"]


def test_decode_motor_driver_board_fault_is_serious():
    f = sd.decode_motor_fault(_ml(Driver_Board_3_Faults=2))
    assert f["serious"] is True
    assert any("driver board 3" in b for b in f["boards"])


def test_decode_motor_comm_fault_is_serious():
    f = sd.decode_motor_fault(_ml(Upstream_Comm=1))
    assert f["serious"] is True
    assert "upstream comm" in f["comm"]


def test_motor_fault_str_includes_path_and_motor():
    f = sd.decode_motor_fault(_ml(Motor_Overall=1 << 4))
    f["path"], f["motor"] = 6, 4
    s = sd.motor_fault_str(f)
    assert "Path 6" in s and "Motor 4" in s


def test_analyze_serious_motor_fault_is_critical():
    snap = make_snapshot()
    snap.motor_faults = [{"path": 6, "motor": 4, "motor_states": ["Stopped (FastStop)"],
                          "comm": [], "boards": [], "serious": True}]
    out = sd.analyze_status(snap)
    assert any(sev == "critical" and "Motor/driver fault" in title for sev, title, _ in out)


def test_analyze_minor_motor_state_is_info_not_critical():
    snap = make_snapshot()
    snap.motor_faults = [{"path": 2, "motor": 1, "motor_states": ["In Config Mode"],
                          "comm": [], "boards": [], "serious": False}]
    out = sd.analyze_status(snap)
    assert any(sev == "info" and "non-running state" in title for sev, title, _ in out)
    assert not any("Motor/driver fault" in title for _, title, _ in out)


# ── cold-start path-command progress (step 25/30/55/60) ──────────────────────

def test_cold_start_progress_none_when_not_in_path_wait():
    assert sd.cold_start_progress(make_snapshot(cold_start_step=5)) is None
    assert sd.cold_start_progress(make_snapshot(cold_start_step=18)) is None


def test_cold_start_progress_counts_completed_reset_paths():
    snap = make_snapshot(cold_start_step=30, max_path=6)
    # only 4 of 6 paths have completed the CURRENT reset command
    snap.cs_cmd_count = 7
    snap.path_cmd_count = [None] + [7, 7, 7, 7, 5, 5]   # paths 5,6 still on an old command
    snap.path_cmd_status = [None] + [128, 128, 128, 128, 128, 128]
    prog = sd.cold_start_progress(snap)
    assert prog["label"] == "Resetting paths"
    assert prog["done"] == 4 and prog["total"] == 6


def test_cold_start_progress_countdown_from_timer():
    snap = make_snapshot(cold_start_step=25)
    snap.cs_timer_pre = 300000      # 5 min
    snap.cs_timer_acc = 120000      # 2 min elapsed
    prog = sd.cold_start_progress(snap)
    assert abs(prog["secs_left"] - 180.0) < 0.5     # ~3 min left
    assert "until retry" in prog["detail"]


def test_cold_start_progress_startup_label():
    prog = sd.cold_start_progress(make_snapshot(cold_start_step=60))
    assert prog["label"] == "Starting paths"


def test_operation_banner_includes_reset_progress():
    snap = make_snapshot(cold_start_step=30)
    snap.cs_timer_pre = 300000
    snap.cs_timer_acc = 60000
    op = sd.current_operation(snap)
    assert "RESET complete" in op["detail"]


# ── step-aware homing diagnosis (cross-routine root cause) ───────────────────

def test_homing_diagnosis_none_when_running():
    assert sd.homing_diagnosis(make_snapshot(cold_start_step=5), 999) is None


def test_homing_diagnosis_none_when_dwell_short():
    assert sd.homing_diagnosis(make_snapshot(cold_start_step=18), 2) is None


def test_homing_diagnosis_step18_names_offline_nc():
    snap = make_snapshot(cold_start_step=18)
    snap.nc_status[1] = {"state": 1}            # INIT, not OPERATIONAL
    sev, title, detail = sd.homing_diagnosis(snap, 30)
    assert sev == "critical"
    assert "step 18" in title
    assert "NC 1" in detail and "Node Controller" in detail


def test_homing_diagnosis_step20_blames_hlc_link():
    snap = make_snapshot(cold_start_step=20, hlc_link=False)
    _, _, detail = sd.homing_diagnosis(snap, 30)
    assert "hlc_link_status" in detail and "hlc_link_monitor" in detail


def test_homing_diagnosis_step20_blames_stuck_msg_service():
    snap = make_snapshot(cold_start_step=20, hlc_link=True)
    snap.msg_path_cmd_step = 20                  # not idle (10)
    _, _, detail = sd.homing_diagnosis(snap, 30)
    assert "message service" in detail and "20" in detail


def test_homing_diagnosis_step30_identifies_incomplete_path():
    snap = make_snapshot(cold_start_step=30)
    snap.path_cmd_status[3] = 0                  # path 3 not COMPLETE (0x80)
    _, _, detail = sd.homing_diagnosis(snap, 30)
    assert "RESET" in detail and "Path 3" in detail


def test_homing_diagnosis_step60_cross_references_motor_fault():
    snap = make_snapshot(cold_start_step=60)
    snap.path_cmd_status[6] = 0
    snap.motor_faults = [{"path": 6, "motor": 2, "motor_states": ["Not Responding"],
                          "comm": [], "boards": [], "serious": True}]
    _, _, detail = sd.homing_diagnosis(snap, 30)
    assert "STARTUP" in detail
    assert "motor fault" in detail.lower() and "6" in detail


def test_analyze_status_includes_step_aware_diagnosis():
    snap = make_snapshot(cold_start_step=18)
    snap.nc_status[1] = {"state": 2}            # FAULTED
    out = sd.analyze_status(snap, homing_dwell_s=40)
    assert any("Homing stuck at step 18" in title for _, title, _ in out)


# ── lookup helpers ───────────────────────────────────────────────────────────

def test_station_and_path_names():
    assert sd.station_name(33) == "HOME / Cold Start"
    assert sd.path_name(6) == "Process"
    assert sd.path_name(0) == "—"


def test_cold_start_info_unknown_step():
    phase, desc, color = sd.cold_start_info(999)
    assert "Unknown" in desc
