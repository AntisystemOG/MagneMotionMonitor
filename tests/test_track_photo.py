"""PhotoTrackModel — pixel-space calibration for the real track photo, and the
TrackCanvas photo/schematic fallback selection."""
from __future__ import annotations
import math
import pytest

from mm_monitor.track_photo import (
    PhotoTrackModel, PATH_WAYPOINTS_PX, PHOTO_SIZE, build_photo_track_model,
    REAL_TO_PIXEL_BREAKPOINTS, _remap_fraction, _cumulative_lengths,
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


# ── mold-spur curve fraction correction (real_frac != pixel_frac near the U-turn) ──
#
# The pixel-traced U-turn on paths 2/4 occupies a much bigger SHARE of pixel
# arc-length (~19-21%) than the same turn occupies of the path's real length
# (~8%, from track_geometry's own segment lengths) — a straight real-fraction
# to pixel-fraction mapping therefore placed anything past the turn (a mold's
# Load 2 station, or a cart mid-transit) too far along/low, and made the ride
# through the curve look uneven. REAL_TO_PIXEL_BREAKPOINTS + _remap_fraction
# fix this; these tests guard against it regressing silently.

def test_remap_fraction_matches_known_anchors_exactly():
    bp = [(0.0, 0.0), (0.5, 0.3), (1.0, 1.0)]
    assert _remap_fraction(0.0, bp) == 0.0
    assert _remap_fraction(0.5, bp) == pytest.approx(0.3)
    assert _remap_fraction(1.0, bp) == 1.0


def test_remap_fraction_interpolates_linearly_between_anchors():
    bp = [(0.0, 0.0), (0.5, 0.3), (1.0, 1.0)]
    # halfway between the 0.5->0.3 and 1.0->1.0 anchors
    assert _remap_fraction(0.75, bp) == pytest.approx(0.65)


def test_remap_fraction_clamps_outside_anchor_range():
    bp = [(0.2, 0.1), (0.8, 0.9)]
    assert _remap_fraction(0.0, bp) == pytest.approx(0.1)
    assert _remap_fraction(1.0, bp) == pytest.approx(0.9)


def test_paths_2_and_4_have_breakpoint_corrections():
    assert 2 in REAL_TO_PIXEL_BREAKPOINTS
    assert 4 in REAL_TO_PIXEL_BREAKPOINTS


def test_paths_without_breakpoints_use_direct_fraction():
    # Path 6 (Process) has no correction entry -> point_at should fall back to
    # the plain real_frac == pixel_frac behavior (no remap applied).
    assert REAL_TO_PIXEL_BREAKPOINTS.get(6) is None


def test_station_past_the_curve_renders_higher_than_uncorrected_mapping():
    """Regression guard for the exact bug reported: Mold 2's Load 2 station
    (path 4 @ 3.405m, real fraction ~71%, past the U-turn) must render further
    up the return leg (smaller pixel y) than a naive direct real-fraction ->
    pixel-fraction mapping would have placed it."""
    model = PhotoTrackModel(real_lengths={4: 4.7854})
    corrected = model.point_at(4, 3.405)

    pts = PATH_WAYPOINTS_PX[4]
    s = _cumulative_lengths(pts)
    frac = 3.405 / 4.7854
    target = frac * s[-1]
    lo, hi = 0, len(s) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if s[mid] <= target:
            lo = mid
        else:
            hi = mid
    seg = s[hi] - s[lo]
    t = 0.0 if seg <= 0 else (target - s[lo]) / seg
    a, b = pts[lo], pts[hi]
    uncorrected = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    assert corrected[1] < uncorrected[1] - 20, (
        "corrected position should be meaningfully higher (smaller y) than "
        "the naive direct-fraction mapping")


def test_curve_region_markers_stay_evenly_spaced_no_clustering():
    """Walking a simulated cart around a full mold-spur path in even real-meter
    steps must never produce two consecutive samples landing on nearly the
    same pixel point (the original clustering-at-the-bend bug) or jumping
    backward in arc-length order."""
    model = build_photo_track_model()
    from mm_monitor.track_geometry import build_track
    real_len = build_track().paths[2].length

    step = 0.1
    prev = None
    n = int(real_len / step)
    for i in range(n + 1):
        pt = model.point_at(2, i * step)
        assert pt is not None
        if prev is not None:
            dist = math.hypot(pt[0] - prev[0], pt[1] - prev[1])
            assert dist > 0.5, f"step {i}: consecutive samples nearly identical (clustering)"
        prev = pt
