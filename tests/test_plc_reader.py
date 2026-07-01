"""Reader tests that don't need a live PLC — offline behavior and snapshot shape."""
from __future__ import annotations

from mm_monitor.plc_reader import PLCReader, SystemSnapshot
from mm_monitor.system_data import MAX_VEHICLES, MAX_STATIONS


def test_poll_without_connection_returns_default_snapshot():
    reader = PLCReader()
    snap = reader.poll()
    assert isinstance(snap, SystemSnapshot)
    assert snap.cold_start_step == 5          # safe default
    assert snap.pallets_in_system == 0
    assert reader.connected is False


def test_connect_to_bad_host_fails_gracefully():
    reader = PLCReader()
    ok, msg = reader.connect("0.0.0.0")
    assert ok is False
    assert isinstance(msg, str) and msg
    assert reader.connected is False


def test_disconnect_is_safe_when_never_connected():
    reader = PLCReader()
    reader.disconnect()  # must not raise
    assert reader.connected is False


def test_snapshot_arrays_are_one_based_sized():
    snap = SystemSnapshot()
    # index 0 unused, valid indices 1..MAX
    assert len(snap.vehicle_status) == MAX_VEHICLES + 1
    assert len(snap.stations) == MAX_STATIONS + 1
    assert snap.vehicle_status[0] is None


def test_motor_faults_default_empty_list():
    assert SystemSnapshot().motor_faults == []


def test_motor_fault_scan_throttled(monkeypatch):
    """The motor-fault scan must only hit the PLC once per ML_FAULT_INTERVAL;
    in between it returns the cached result."""
    import mm_monitor.plc_reader as pr
    reader = pr.PLCReader()
    calls = {"n": 0}

    def fake_read(*tags):
        calls["n"] += 1
        return {}      # no faults; still counts as a scan
    monkeypatch.setattr(reader, "_read", fake_read)

    reader._read_motor_faults(6, 13)   # first call scans
    reader._read_motor_faults(6, 13)   # within interval → cached, no new scan
    assert calls["n"] == 1
    # force the interval to elapse
    reader._ml_last -= (pr.ML_FAULT_INTERVAL + 1)
    reader._read_motor_faults(6, 13)
    assert calls["n"] == 2
