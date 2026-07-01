"""Recording round-trip: a snapshot written then loaded must survive intact,
and older recordings missing newer fields must still load (forward-compat)."""
from __future__ import annotations
import json

from mm_monitor.recording import Recorder, Recording
from tests.conftest import make_snapshot


def test_record_then_load_roundtrip(tmp_path):
    path = tmp_path / "rec.mmrec"
    rec = Recorder()
    assert rec.start(path)
    snap = make_snapshot(pallets_in_system=7, cold_start_step=17)
    rec.add(snap)
    rec.add(make_snapshot(pallets_in_system=8))
    rec.stop()

    loaded = Recording.load(path)
    assert len(loaded) == 2
    first = loaded.snapshot(0)
    assert first.pallets_in_system == 7
    assert first.cold_start_step == 17
    # active cart data survives the json round-trip
    assert first.vehicle_status[1]["Path_ID"] == 6


def test_load_tolerates_missing_newer_fields(tmp_path):
    """A recording from an older app version won't have every field — load anyway."""
    path = tmp_path / "old.mmrec"
    path.write_text(
        json.dumps({"header": "old", "version": "0.1.0"}) + "\n"
        + json.dumps({"t": 0.0, "snap": {"pallets_in_system": 2}}) + "\n",
        encoding="utf-8",
    )
    loaded = Recording.load(path)
    assert len(loaded) == 1
    assert loaded.snapshot(0).pallets_in_system == 2


def test_index_for_time_finds_last_frame_at_or_before():
    frames = [(0.0, make_snapshot()), (1.0, make_snapshot()), (2.5, make_snapshot())]
    rec = Recording(frames)
    assert rec.index_for_time(-1) == 0
    assert rec.index_for_time(1.0) == 1
    assert rec.index_for_time(2.0) == 1
    assert rec.index_for_time(99) == 2
    assert rec.duration == 2.5


def test_empty_recording_has_zero_duration():
    assert Recording([]).duration == 0.0
    assert len(Recording([])) == 0
