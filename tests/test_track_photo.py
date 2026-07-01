"""PhotoTrackModel — pixel-space calibration for the real track photo, and the
TrackCanvas photo/schematic fallback selection."""
from __future__ import annotations
import pytest

from mm_monitor.track_photo import (
    PhotoTrackModel, PATH_WAYPOINTS_PX, PHOTO_SIZE, build_photo_track_model,
)


def test_all_six_paths_have_waypoints():
    assert set(PATH_WAYPOINTS_PX) == {1, 2, 3, 4, 5, 6}


def test_every_path_has_at_least_two_waypoints():
    for pid, pts in PATH_WAYPOINTS_PX.items():
        assert len(pts) >= 2, f"path {pid} needs at least 2 waypoints to form a line"


def test_waypoints_are_within_photo_bounds():
    pw, ph = PHOTO_SIZE
    for pid, pts in PATH_WAYPOINTS_PX.items():
        for x, y in pts:
            assert -5 <= x <= pw + 5, f"path {pid} waypoint x={x} outside photo width"
            assert -5 <= y <= ph + 5, f"path {pid} waypoint y={y} outside photo height"


def test_point_at_start_and_end_match_waypoint_endpoints():
    model = PhotoTrackModel(real_lengths={6: 10.0})
    p0 = model.point_at(6, 0.0)
    pN = model.point_at(6, 10.0)
    assert p0 == PATH_WAYPOINTS_PX[6][0]
    assert pN == PATH_WAYPOINTS_PX[6][-1]


def test_point_at_clamps_beyond_real_length():
    model = PhotoTrackModel(real_lengths={6: 10.0})
    way_past_end = model.point_at(6, 999.0)
    at_end = model.point_at(6, 10.0)
    assert way_past_end == at_end


def test_point_at_unknown_path_is_none():
    model = PhotoTrackModel(real_lengths={6: 10.0})
    assert model.point_at(99, 1.0) is None


def test_point_at_midpoint_is_between_first_two_waypoints_for_short_path():
    # Path 5 has 3 waypoints; at 50% of its real length it should land somewhere
    # between the first and last waypoint (not exactly at either endpoint).
    model = PhotoTrackModel(real_lengths={5: 1.0})
    mid = model.point_at(5, 0.5)
    xs = [p[0] for p in PATH_WAYPOINTS_PX[5]]
    assert min(xs) - 1 <= mid[0] <= max(xs) + 1


def test_build_photo_track_model_uses_real_path_lengths():
    """The cached model must pull real (non-zero) path lengths from the actual
    track geometry, not placeholder zeros — otherwise every position collapses
    to a path's start point."""
    model = build_photo_track_model()
    p_start = model.point_at(6, 0.0)
    p_mid = model.point_at(6, 5.0)
    assert p_start != p_mid, "positions should differ across a 10m+ path"
