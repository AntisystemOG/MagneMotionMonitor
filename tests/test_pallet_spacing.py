"""resolve_pallet_spacing — the "beads on a string" anti-overlap algorithm that
keeps same-path pallets from rendering on top of each other."""
from __future__ import annotations
import math

from mm_monitor.gui.track_panel import (
    _Cart, resolve_pallet_spacing, _CART_MIN_GAP_PX,
)
from mm_monitor.track_photo import build_photo_track_model


def _cart(cid, path, pos, vel=0.0):
    return _Cart(cid, path, pos, vel, dest=0, alarm=None)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_every_cart_gets_a_position_none_dropped():
    model = build_photo_track_model()
    carts = [_cart(i, 6, 5.0 + i * 0.5) for i in range(1, 6)]
    out = resolve_pallet_spacing(model, carts)
    assert set(out) == {c.id for c in carts}


def test_two_carts_at_same_station_are_separated():
    """PreLoad 1 (3.000 m) and Load 1 (3.062 m) on Mold 1 are ~13px apart raw —
    closer than one cart body. After resolution they must be at least the
    minimum gap apart so their IDs stay readable."""
    model = build_photo_track_model()
    carts = [_cart(1, 2, 3.000), _cart(2, 2, 3.062)]
    out = resolve_pallet_spacing(model, carts)
    assert _dist(out[1], out[2]) >= _CART_MIN_GAP_PX - 0.5


# Cart body is 2 * _CART_R (= 22px). "Not overlapping" means centers are at
# least that far apart in straight-line distance. Near a tight U-turn, carts a
# full arc-gap apart can be slightly closer than the arc-gap in euclidean terms
# (the rail doubles back), but must never be closer than the body width — that's
# physically real (a pallet just before the apex sits beside one just after).
_CART_BODY_PX = 22.0


def test_many_carts_stacked_never_overlap_bodies():
    model = build_photo_track_model()
    # every Mold 1 station occupied (positions only cm apart in places, and the
    # cluster straddles the U-turn where euclidean < arc-length)
    positions = [2.65, 2.75, 3.00, 3.012, 3.405, 4.50]
    carts = [_cart(i, 2, pos) for i, pos in enumerate(positions, start=1)]
    out = resolve_pallet_spacing(model, carts)
    pts = list(out.values())
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            assert _dist(pts[i], pts[j]) >= _CART_BODY_PX - 1.0


def test_queued_carts_on_a_straight_get_the_full_arc_gap():
    """On the long straight process line (no doubling-back), the arc-length gap
    and the euclidean gap coincide, so carts get the full _CART_MIN_GAP_PX."""
    model = build_photo_track_model()
    # three carts within a hair of each other mid-straight on path 6
    carts = [_cart(1, 6, 5.00), _cart(2, 6, 5.01), _cart(3, 6, 5.02)]
    out = resolve_pallet_spacing(model, carts)
    pts = sorted(out.values(), key=lambda p: p[0])
    for a, b in zip(pts, pts[1:]):
        assert _dist(a, b) >= _CART_MIN_GAP_PX - 1.0


def test_carts_on_different_paths_do_not_interact():
    model = build_photo_track_model()
    # one cart on Mold 1, one at the "same" real position on Mold 2 — different
    # physical paths, so neither should be nudged by the other.
    solo1 = resolve_pallet_spacing(model, [_cart(1, 2, 3.0)])
    solo2 = resolve_pallet_spacing(model, [_cart(2, 4, 3.0)])
    both = resolve_pallet_spacing(model, [_cart(1, 2, 3.0), _cart(2, 4, 3.0)])
    assert both[1] == solo1[1]
    assert both[2] == solo2[2]


def test_lead_cart_keeps_its_true_position():
    """The furthest-along cart is the queue lead and should not move; trailing
    carts queue behind it."""
    model = build_photo_track_model()
    lead_solo = resolve_pallet_spacing(model, [_cart(1, 2, 4.50)])[1]
    out = resolve_pallet_spacing(model, [_cart(1, 2, 4.50), _cart(2, 2, 4.45)])
    assert out[1] == lead_solo


def test_queue_order_preserved_no_swapping():
    """Along the path, resolved pixel arc-length must stay in the same order as
    the carts' real positions (no cart teleporting past another)."""
    model = build_photo_track_model()
    carts = [_cart(1, 2, 4.50), _cart(2, 2, 4.40), _cart(3, 2, 4.35)]
    out = resolve_pallet_spacing(model, carts)
    # cart 1 (furthest) should have the largest pixel arc-length, etc.
    s1 = model.pixel_length(2)  # sanity: helper exists
    # recover pix_s of each resolved point by nearest-position isn't trivial;
    # instead assert the lead (1) is not behind 2, and 2 not behind 3, in y or x.
    # On the return leg the carts go up (decreasing y), so higher pos -> smaller y.
    assert out[1][1] <= out[2][1] <= out[3][1] + 1  # monotonic up the leg


def test_empty_and_single_cart_are_safe():
    model = build_photo_track_model()
    assert resolve_pallet_spacing(model, []) == {}
    one = resolve_pallet_spacing(model, [_cart(1, 6, 5.0)])
    assert set(one) == {1}
