"""CartPresenceGuard — holds a cart at its last known position when the HLC
temporarily stops reporting it (Path_ID -> 0) WHILE Homing or Cleaning is in
progress, instead of letting it disappear from the Live Track."""
from __future__ import annotations

from mm_monitor.gui.track_panel import _Cart, CartPresenceGuard, _operation_active
from tests.conftest import make_snapshot


def _cart(cid=1, path=6, pos=5.0, vel=0.5):
    return _Cart(cid, path, pos, vel, dest=0, alarm=None)


# ── _operation_active ────────────────────────────────────────────────────────

def test_operation_active_true_during_homing():
    assert _operation_active(make_snapshot(cold_start_step=17)) is True


def test_operation_active_true_during_cleanout():
    assert _operation_active(make_snapshot(cleanout=True, pallets_in_system=3)) is True


def test_operation_active_false_when_running():
    assert _operation_active(make_snapshot(cold_start_step=5)) is False


# ── CartPresenceGuard ─────────────────────────────────────────────────────────

def test_cart_missing_during_active_operation_is_held_at_last_position():
    guard = CartPresenceGuard()
    guard.apply([_cart(cid=1, pos=5.0)], operation_active=True)   # seen once
    out = guard.apply([], operation_active=True)                  # now missing
    assert len(out) == 1
    assert out[0].id == 1 and out[0].pos == 5.0
    assert out[0].held is True


def test_held_cart_velocity_is_frozen_to_zero():
    """A held cart's old velocity shouldn't be trusted (we don't know it's
    still true), so it must not keep implying motion."""
    guard = CartPresenceGuard()
    guard.apply([_cart(vel=1.5)], operation_active=True)
    out = guard.apply([], operation_active=True)
    assert out[0].vel == 0.0


def test_cart_missing_outside_active_operation_is_dropped():
    guard = CartPresenceGuard()
    guard.apply([_cart(cid=1)], operation_active=True)
    out = guard.apply([], operation_active=False)   # operation ended, still missing
    assert out == []


def test_cart_reappearing_with_real_data_is_no_longer_held():
    guard = CartPresenceGuard()
    guard.apply([_cart(cid=1, pos=5.0)], operation_active=True)
    guard.apply([], operation_active=True)                         # dropped out
    out = guard.apply([_cart(cid=1, pos=6.0)], operation_active=True)  # real data returns
    assert len(out) == 1
    assert out[0].pos == 6.0 and out[0].held is False


def test_present_carts_pass_through_unchanged():
    guard = CartPresenceGuard()
    out = guard.apply([_cart(cid=1, pos=5.0)], operation_active=True)
    assert len(out) == 1 and out[0].held is False


def test_stale_memory_clears_once_operation_ends_and_cart_stays_missing():
    """A cart that was held during an operation and is STILL missing once the
    operation ends must stop being remembered — it really left."""
    guard = CartPresenceGuard()
    guard.apply([_cart(cid=1)], operation_active=True)
    guard.apply([], operation_active=True)     # held during the operation
    guard.apply([], operation_active=False)    # operation over, still gone -> forget it
    out = guard.apply([], operation_active=True)   # a later, unrelated operation starts
    assert out == []   # must NOT resurrect the long-gone cart


def test_multiple_carts_only_missing_ones_are_held():
    guard = CartPresenceGuard()
    guard.apply([_cart(cid=1, pos=1.0), _cart(cid=2, pos=2.0)], operation_active=True)
    out = guard.apply([_cart(cid=1, pos=1.5)], operation_active=True)   # cart 2 missing
    ids_held = {c.id: c.held for c in out}
    assert ids_held == {1: False, 2: True}


def test_reset_clears_all_memory():
    guard = CartPresenceGuard()
    guard.apply([_cart(cid=1)], operation_active=True)
    guard.reset()
    out = guard.apply([], operation_active=True)
    assert out == []
