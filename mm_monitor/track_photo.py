"""Pixel-space calibration for the real S7000 track photo (mm_monitor/data/track_photo.png),
so the Live Track view can draw stations/carts directly on the actual hardware photo
instead of the auto-generated schematic.

HOW THIS WAS BUILT (read before touching the waypoints below):
A photo has no coordinate system — unlike track_geometry.py's schematic, which is
mathematically derived from TrackFile.mmtrk (the real per-motor track description), so
there is no way to algorithmically compute where a station sits on a photograph. This
calibration is a best-effort visual alignment, built by:
  1. Rendering the schematic (track_geometry.build_track()) to confirm topology: path
     colors/shapes were compared against the photo to identify which physical spur is
     which path (see PATH→PHOTO_ELEMENT MAP below) — this is ground truth, not a guess.
  2. Measuring the photo's actual pixel geometry (rail centerlines, spur leg positions,
     U-turn bottoms) from the image data (numpy thresholding + manual crop inspection),
     not eyeballed from a downscaled preview.
  3. Placing waypoints for each path in the SAME order the real vehicle travels it
     (confirmed from the segment list in track_geometry.TRACK_MMTRK — e.g. path 6's
     first 2m head screen-LEFT before the curve, due to the schematic's X-axis flip).

PATH → PHOTO ELEMENT MAP (confirmed via schematic color rendering, see PROJECT_MEMORY.md):
  Path 6 (Process)         -> the full top rail incl. both rounded end caps
  Path 3 (unnamed connector)-> the long straight middle section of the lower rail
  Path 4 (Mold 2)           -> LEFT drop spur (U-shape)
  Path 2 (Mold 1)           -> RIGHT drop spur (U-shape)
  Path 1 (Mold 1 Entry/Exit)-> tiny connector at the right junction (no stations)
  Path 5 (Mold 2 Entry/Exit)-> tiny connector at the left junction (1 station: Cleanout)

ACCURACY: paths 6, 2, 4 (28 of 30 real stations, everything the operator actually
watches) are calibrated from measured photo pixels. Paths 2 and 4 (the two mold
spurs) use a DENSE trace (numpy column-scan of both legs + the U-turn bottom, every
~2-4px) rather than a coarse hand-placed polyline — an earlier ~9-point version made
a cart look like it "stopped before the turn" into a spur, because a straight-line
approximation compresses some of the real curve into too few pixels relative to how
much real length it represents, so a cart's fractional position lands short there.
The dense trace fixes that: a cart moving in even real-meter steps now advances
evenly through the whole spur, curve included (verified by walking a simulated cart
in 0.5m steps and checking the pixel spacing stays even all the way around).
Paths 1/3/5 (short connectors, hosting only "Home" and "Cleanout") still use
straight-line approximations between their measured junction points — fine for
"where roughly is this pallet", not survey-grade. If something still looks off
once you can compare it against the real machine, see PATH_WAYPOINTS_PX below.
"""
from __future__ import annotations
import math

# Native pixel size of mm_monitor/data/track_photo.png. The renderer scales this
# (uniformly, letterboxed) to fit whatever widget size it's drawn into.
PHOTO_SIZE = (1584, 672)

# Per-path waypoints in PHOTO-NATIVE pixel space, IN THE SAME ORDER the vehicle
# travels that path (arc-length order). A cart's fractional position along its
# real path (pos_m / path_length_m) is mapped to the same fraction of distance
# along this pixel polyline — so absolute pixel spacing doesn't need to exactly
# match real-world scale, only the relative shape/order needs to be right.
PATH_WAYPOINTS_PX: dict[int, list[tuple[float, float]]] = {
    # Path 6 — Process: left junction -> approach leg -> left cap -> top straight
    # -> right end (hands off to Path 1). Order matches the real travel direction.
    6: [
        (478, 175), (350, 175), (200, 165), (90, 130), (40, 90), (34, 65),
        (90, 60), (200, 63), (400, 64), (600, 65), (800, 65), (1000, 66),
        (1200, 67), (1350, 70), (1420, 85), (1460, 115), (1483, 150),
    ],
    # Path 1 — Mold 1 Entry/Exit (tiny, no stations): closes the gap between
    # Path 6's end and the right spur junction.
    1: [(1483, 150), (1484, 172)],
    # Path 2 — Mold 1 (RIGHT spur): down one leg, around the bottom, up the
    # other. Straight legs are densely measured (numpy column-trace); the U-turn
    # BOTTOM is a semi-ellipse arc through the two measured leg centerlines and
    # the true rail-bottom centerline (measured by a vertical scan at the U's
    # center x). An earlier horizontal-scan trace swung the bottom waypoints
    # wide/low OUTSIDE the rail (a horizontal scan can't follow a tube that runs
    # horizontally at the U bottom), so carts "left the track" at the turn.
    # See scratchpad build_uturn.py / rebuild_spurs.py for the arc method.
    2: [
        (1449, 175), (1431, 207), (1433, 233), (1434, 259), (1436, 285),
        (1438, 311), (1440, 337), (1442, 363), (1450, 389), (1447, 415),
        (1448, 441), (1450, 467), (1452, 493), (1454, 519), (1461, 545),
        (1461, 571), (1456, 593), (1451, 596), (1450, 601), (1448, 606),
        (1444, 611), (1439, 616), (1433, 619), (1426, 622), (1418, 625),
        (1410, 626), (1401, 626), (1393, 626), (1384, 625), (1376, 622),
        (1369, 619), (1363, 616), (1358, 611), (1354, 606), (1352, 601),
        (1352, 596), (1372, 593), (1362, 571), (1360, 545), (1362, 519),
        (1360, 493), (1359, 467), (1358, 441), (1354, 415), (1352, 389),
        (1353, 363), (1352, 337), (1350, 311), (1348, 285), (1346, 259),
        (1344, 233), (1340, 207), (1358, 175),
    ],
    # Path 3 — long straight connector (hosts station 33, HOME/Cold Start, near
    # its far end): right junction (Path 1's end) across to the left junction.
    3: [(1483, 175), (1200, 175), (900, 176), (600, 177), (518, 175)],
    # Path 4 — Mold 2 (LEFT spur): mirrors Path 2, same measured legs + semi-
    # ellipse U-turn arc.
    4: [
        (518, 175), (527, 207), (524, 233), (524, 259), (523, 285),
        (523, 311), (524, 337), (524, 363), (528, 389), (525, 415),
        (523, 441), (522, 467), (523, 493), (522, 519), (528, 545),
        (527, 571), (517, 595), (528, 597), (528, 603), (525, 609),
        (522, 614), (517, 619), (510, 623), (503, 627), (495, 629),
        (487, 631), (478, 632), (470, 631), (461, 629), (453, 627),
        (446, 623), (440, 619), (435, 614), (431, 609), (429, 603),
        (428, 597), (436, 595), (426, 571), (426, 545), (431, 519),
        (431, 493), (432, 467), (432, 441), (430, 415), (429, 389),
        (432, 363), (434, 337), (434, 311), (434, 285), (434, 259),
        (436, 233), (430, 207), (435, 175),
    ],
    # Path 5 — Mold 2 Entry/Exit / Cleanout stub (hosts station 34): short direct
    # bypass alongside Path 4's junction span.
    5: [(518, 175), (476, 172), (435, 175)],
}


def _cumulative_lengths(pts: list[tuple[float, float]]) -> list[float]:
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return s


# Mold spurs (paths 2 & 4): the real path is leg → U-turn → leg, and the
# U-turn is a genuinely SHORT slice of the real length (the two 90° curves
# that make up the 180° turn are only ~8% of the path — see
# track_geometry.build_track()'s segment lengths). But the PHOTOGRAPHED curve's
# pixel-arc-length share is much larger (measured ~19-21%), because the real
# curve is a tight radius while the physical rail's visible turn spans a much
# wider arc in the photo. Mapping "real fraction" straight onto "pixel
# fraction" 1:1 therefore put anything past the turn (e.g. a mold's Load 2
# station, or a cart mid-transit) noticeably further along the pixel path than
# it should be — reported as "the label should be higher up" and "carts take
# a weird route around the bend".
#
# Fix: a piecewise-linear correction, anchored at the two leg/curve transition
# points on both sides — (real_fraction, pixel_fraction) pairs measured directly
# from these paths' own waypoint lists and track_geometry's real segment
# lengths. Between anchors, a real fraction is linearly remapped to the pixel
# fraction it should ACTUALLY correspond to, before the normal arc-length
# lookup runs. Paths without an entry here (1, 3, 5, 6) use real_frac ==
# pixel_frac directly — their curves are a small enough share of the total
# length that this mismatch isn't meaningfully visible.
# Anchors: (0, 0) and the two leg/curve transitions come from track_geometry's
# real segment lengths + the measured pixel arc-length of those transitions in
# the waypoints above. The EXTRA middle anchor (~0.71 real) is a "Load lift":
# the HMI Load 2 meter (3.405 m) maps mathematically to only ~37% up the return
# leg, but on the real machine the load station sits ~2/3 up the leg (field-
# confirmed by the operator with a pointer). Rather than distrust the HMI meter
# everywhere, this single anchor pulls the Load region up to match reality; the
# leg/curve anchors keep the U-turn correct and Cooling (top) unaffected. If the
# operator flags a station as still off, nudge the matching anchor's pixel value.
REAL_TO_PIXEL_BREAKPOINTS: dict[int, list[tuple[float, float]]] = {
    2: [(0.0, 0.0), (0.465, 0.424), (0.546, 0.576), (0.704, 0.860), (1.0, 1.0)],
    4: [(0.0, 0.0), (0.459, 0.424), (0.541, 0.577), (0.712, 0.860), (1.0, 1.0)],
}


def _remap_fraction(frac: float, breakpoints: list[tuple[float, float]]) -> float:
    """Piecewise-linear remap of a real-position fraction to the pixel-arc-length
    fraction it should correspond to, given known (real, pixel) anchor points."""
    if frac <= breakpoints[0][0]:
        return breakpoints[0][1]
    if frac >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for (r0, p0), (r1, p1) in zip(breakpoints, breakpoints[1:]):
        if r0 <= frac <= r1:
            t = 0.0 if r1 <= r0 else (frac - r0) / (r1 - r0)
            return p0 + (p1 - p0) * t
    return frac   # unreachable given the bounds checks above


class PhotoTrackModel:
    """Same query shape as track_geometry.TrackModel (point_at(path, pos_m)) but
    returns photo-native pixel coordinates instead of schematic meter-coordinates,
    using the hand-calibrated waypoints above."""

    def __init__(self, real_lengths: dict[int, float]):
        # real_lengths: path_id -> real length in meters (from track_geometry's
        # already-correct, motor-derived path lengths) — used only to convert a
        # cart's real position into a 0..1 fraction; see module docstring.
        self._real_lengths = real_lengths
        self._pts: dict[int, list[tuple[float, float]]] = {}
        self._s: dict[int, list[float]] = {}
        for pid, waypoints in PATH_WAYPOINTS_PX.items():
            self._pts[pid] = waypoints
            self._s[pid] = _cumulative_lengths(waypoints)

    def pixel_length(self, path_id: int) -> float:
        """Total pixel arc-length of a path's waypoint polyline (0 if unknown)."""
        s = self._s.get(path_id)
        return s[-1] if s else 0.0

    def pixel_s_at(self, path_id: int, pos_m: float) -> float | None:
        """Map a real meter-position to its position along the pixel polyline,
        measured as PIXEL arc-length (0 .. pixel_length). This is the same
        quantity `point_at` walks to — exposed so the pallet-spacing resolver
        (see track_panel.resolve_pallet_spacing) can enforce a minimum on-screen
        gap between carts in real pixel distance, not in meters (a fixed meter
        gap would be a wildly different pixel gap on the tight U-turn vs. a
        straight leg)."""
        s = self._s.get(path_id)
        if not s or s[-1] <= 0:
            return None
        real_len = self._real_lengths.get(path_id, 0.0)
        frac = 0.0 if real_len <= 0 else max(0.0, min(1.0, pos_m / real_len))
        breakpoints = REAL_TO_PIXEL_BREAKPOINTS.get(path_id)
        if breakpoints:
            frac = _remap_fraction(frac, breakpoints)
        return frac * s[-1]

    def point_at_pixel_s(self, path_id: int, pix_s: float) -> tuple[float, float] | None:
        """Return (x, y) for a given PIXEL arc-length along a path's polyline.
        The inverse of pixel_s_at for rendering: the spacing resolver adjusts a
        cart's pix_s to avoid overlap, then this places it back on the rail."""
        pts = self._pts.get(path_id)
        s = self._s.get(path_id)
        if not pts or not s or s[-1] <= 0:
            return None
        target = max(0.0, min(pix_s, s[-1]))
        lo, hi = 0, len(s) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if s[mid] <= target:
                lo = mid
            else:
                hi = mid
        seg_len = s[hi] - s[lo]
        t = 0.0 if seg_len <= 0 else (target - s[lo]) / seg_len
        a, b = pts[lo], pts[hi]
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def point_at(self, path_id: int, pos_m: float) -> tuple[float, float] | None:
        pix_s = self.pixel_s_at(path_id, pos_m)
        if pix_s is None:
            return None
        return self.point_at_pixel_s(path_id, pix_s)


_cached_model: PhotoTrackModel | None = None


def build_photo_track_model() -> PhotoTrackModel:
    """Build (and cache) the photo track model, using real path lengths from the
    authoritative schematic geometry so fractional positioning is correct."""
    global _cached_model
    if _cached_model is None:
        from .track_geometry import build_track
        track = build_track()
        real_lengths = {pid: pg.length for pid, pg in track.paths.items()}
        _cached_model = PhotoTrackModel(real_lengths)
    return _cached_model
