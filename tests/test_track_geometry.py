"""Geometry tests — the track must parse, close its loop, and place carts sanely."""
from __future__ import annotations
import pytest

from mm_monitor import track_geometry as tg


def test_build_track_returns_all_six_paths():
    model = tg.build_track()
    assert set(model.paths) == {1, 2, 3, 4, 5, 6}


def test_loop_closes_with_solved_radius():
    # the auto-solved radius should close the main loop to a small gap
    model = tg.build_track()
    assert model.closure_error() < 0.35


def test_point_at_clamps_within_path():
    model = tg.build_track()
    pt = model.point_at(6, 5.5)   # station 13 location
    assert pt is not None
    assert len(pt) == 2
    # way past the end clamps to the path end, never returns None for a valid path
    end = model.point_at(6, 9999.0)
    assert end is not None


def test_point_at_unknown_path_is_none():
    model = tg.build_track()
    assert model.point_at(99, 1.0) is None


def test_path_lengths_are_positive():
    model = tg.build_track()
    for pid, pg in model.paths.items():
        assert pg.length > 0, f"path {pid} has zero length"


def test_parse_ignores_comments_and_blanks():
    text = """
    # a comment
    path_start 1 0
    motor_1_meter up   # inline comment

    motor_q_meter right
    """
    paths = tg.parse_mmtrk(text)
    assert 1 in paths
    assert len(paths[1].segs) == 2
