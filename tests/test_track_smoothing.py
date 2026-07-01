"""Cart motion smoothing — CartAnimator (live dead-reckoning) and
interpolate_carts (exact playback interpolation between known frames)."""
from __future__ import annotations

from mm_monitor.gui.track_panel import (
    _Cart, CartAnimator, carts_from_snapshot, interpolate_carts,
    path_states_from_snapshot,
)
from tests.conftest import make_snapshot


def _cart(cid=1, path=6, pos=5.0, vel=0.5, dest=14, alarm=None):
    return _Cart(cid, path, pos, vel, dest, alarm)


# ── carts_from_snapshot ──────────────────────────────────────────────────────

def test_carts_from_snapshot_skips_untracked_vehicles():
    snap = make_snapshot()
    snap.vehicle_status[1]["Path_ID"] = 0   # HLC no longer tracking this one
    carts = carts_from_snapshot(snap)
    assert all(c.id != 1 for c in carts)


def test_carts_from_snapshot_reads_position_and_velocity():
    snap = make_snapshot()
    carts = carts_from_snapshot(snap)
    c1 = next(c for c in carts if c.id == 1)
    assert c1.path == 6 and c1.pos == 5.5 and c1.vel == 0.5


# ── path_states_from_snapshot (drives the photo-view path status overlay) ────

def test_path_states_reads_all_real_paths():
    # MAX_PATHS is 8 (array bound), but only paths 1-6 are real on this system —
    # path_states_from_snapshot reads whatever the snapshot has, and the photo
    # renderer only draws the 6 it has calibrated waypoints for (extras are
    # harmless unused dict entries).
    states = path_states_from_snapshot(make_snapshot())
    assert {1, 2, 3, 4, 5, 6}.issubset(states)
    assert all(states[pid] == 2 for pid in range(1, 7))   # default fixture: OPERATIONAL


def test_path_states_reflects_a_faulted_or_resetting_path():
    snap = make_snapshot()
    snap.path_status[4] = {"state": 3}   # Path 4 (Mold 2) in RESET
    states = path_states_from_snapshot(snap)
    assert states[4] == 3
    assert states[2] == 2   # other paths unaffected


def test_path_states_skips_paths_with_no_data():
    snap = make_snapshot()
    snap.path_status[3] = None
    states = path_states_from_snapshot(snap)
    assert 3 not in states
    assert 2 in states


# ── interpolate_carts (playback: both endpoints known) ───────────────────────

def test_interpolate_carts_halfway():
    cur = [_cart(pos=0.0)]
    nxt = [_cart(pos=2.0)]
    out = interpolate_carts(cur, nxt, 0.5)
    assert out[0].pos == 1.0


def test_interpolate_carts_frac_zero_returns_current_unchanged():
    cur = [_cart(pos=3.0)]
    out = interpolate_carts(cur, [_cart(pos=9.0)], 0.0)
    assert out[0].pos == 3.0


def test_interpolate_carts_no_next_frame_holds_current():
    cur = [_cart(pos=3.0)]
    out = interpolate_carts(cur, None, 0.8)
    assert out[0].pos == 3.0


def test_interpolate_carts_path_change_snaps_instead_of_smearing():
    """A cart moving to a different path (junction transition) between two
    recorded frames must not be linearly blended across unrelated geometry —
    it should just show the current frame's position until the next keyframe."""
    cur = [_cart(path=2, pos=4.0)]
    nxt = [_cart(path=6, pos=0.5)]
    out = interpolate_carts(cur, nxt, 0.5)
    assert out[0].path == 2 and out[0].pos == 4.0


def test_interpolate_carts_cart_absent_next_frame_holds_current():
    cur = [_cart(cid=1, pos=4.0), _cart(cid=2, pos=1.0)]
    nxt = [_cart(cid=1, pos=5.0)]   # cart 2 left the tracked set
    out = interpolate_carts(cur, nxt, 0.5)
    c2 = next(c for c in out if c.id == 2)
    assert c2.pos == 1.0


# ── CartAnimator (live: dead-reckon from last known velocity) ────────────────

def test_animator_dead_reckons_forward_using_velocity():
    anim = CartAnimator()
    anim.on_live_snapshot([_cart(pos=5.0, vel=1.0)], now=0.0)
    out = anim.tick(now=2.0)   # 2 seconds later, no new sample
    assert abs(out[0].pos - 7.0) < 1e-9   # 5.0 + 1.0*2.0


def test_animator_new_cart_appears_at_its_reported_position():
    anim = CartAnimator()
    anim.on_live_snapshot([_cart(cid=1, pos=3.0, vel=0.0)], now=0.0)
    out = anim.tick(now=0.0)
    assert out[0].pos == 3.0


def test_animator_drops_carts_no_longer_seen():
    anim = CartAnimator()
    anim.on_live_snapshot([_cart(cid=1), _cart(cid=2)], now=0.0)
    anim.on_live_snapshot([_cart(cid=1)], now=1.0)   # cart 2 gone from this poll
    out = anim.tick(now=1.0)
    assert [c.id for c in out] == [1]


def test_animator_extrapolation_capped_when_polls_stall():
    """If the poll thread stalls, a cart must not drift forever — it freezes
    after MAX_EXTRAPOLATE_SEC instead of extrapolating indefinitely."""
    anim = CartAnimator()
    anim.on_live_snapshot([_cart(pos=0.0, vel=1.0)], now=0.0)
    far_future = anim.CORRECTION_SEC + 999.0
    out = anim.tick(now=far_future)
    assert out[0].pos == anim.MAX_EXTRAPOLATE_SEC * 1.0   # capped, not 999


def test_animator_blends_correction_instead_of_snapping():
    """When a new sample disagrees with the dead-reckoned prediction (cart
    stopped, changed speed, or a poll was slow), the display should blend to
    the truth over CORRECTION_SEC rather than teleport there instantly."""
    anim = CartAnimator()
    anim.on_live_snapshot([_cart(pos=0.0, vel=1.0)], now=0.0)
    # Predicted position at t=1.0 would be 1.0m, but the real sample says 4.0m
    # (a big miss) -> a correction blend should start, not an instant jump.
    anim.on_live_snapshot([_cart(pos=4.0, vel=0.0)], now=1.0)
    just_after = anim.tick(now=1.001)
    assert abs(just_after[0].pos - 4.0) > 0.1   # not yet snapped to the truth
    settled = anim.tick(now=1.0 + anim.CORRECTION_SEC + 0.01)
    assert abs(settled[0].pos - 4.0) < 1e-6      # fully blended in by then


def test_animator_path_change_accepts_new_value_directly():
    """A cart moving to a different path (e.g. a junction) has no continuous
    geometry to dead-reckon across — the new path/position should be adopted
    immediately rather than smoothed from the old path's position."""
    anim = CartAnimator()
    anim.on_live_snapshot([_cart(path=2, pos=4.0, vel=0.0)], now=0.0)
    anim.on_live_snapshot([_cart(path=6, pos=0.1, vel=0.0)], now=0.5)
    out = anim.tick(now=0.5)
    assert out[0].path == 6 and out[0].pos == 0.1
