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
    # other. Densely measured (numpy column-trace, every ~2-4px). v2: near the
    # bottom, the trace initially misclassified the inner/outer edge of the ONE
    # curving tube as "2 separate rail legs" (the same heuristic used for the
    # genuinely-separate straight legs) — the waypoint order jumped to the apex
    # early, then back up, then down to the apex again, so several different
    # real positions all rendered clustered at the bottom turn. Fixed by
    # classifying "2 runs" by the gap between them: >40px = separate legs,
    # <=40px = one curving tube's own edges (see scratchpad trace_rails3.py
    # method if this ever needs re-deriving).
    2: [
        (1449, 175), (1431, 207), (1433, 233), (1434, 259), (1436, 285),
        (1438, 311), (1440, 337), (1442, 363), (1450, 389), (1447, 415),
        (1448, 441), (1450, 467), (1452, 493), (1454, 519), (1461, 545),
        (1461, 571), (1456, 593), (1475, 597), (1473, 601), (1471, 605),
        (1471, 609), (1469, 613), (1468, 617), (1465, 621), (1463, 625),
        (1460, 629), (1458, 633), (1453, 637), (1450, 641), (1445, 645),
        (1440, 649), (1431, 653), (1423, 657), (1409, 657), (1395, 653),
        (1386, 649), (1382, 645), (1375, 641), (1372, 637), (1369, 633),
        (1365, 629), (1362, 625), (1360, 621), (1358, 617), (1356, 613),
        (1354, 609), (1352, 605), (1350, 601), (1350, 597), (1372, 593),
        (1362, 571), (1360, 545), (1362, 519), (1360, 493), (1359, 467),
        (1358, 441), (1354, 415), (1352, 389), (1353, 363), (1352, 337),
        (1350, 311), (1348, 285), (1346, 259), (1344, 233), (1340, 207),
        (1358, 175),
    ],
    # Path 3 — long straight connector (hosts station 33, HOME/Cold Start, near
    # its far end): right junction (Path 1's end) across to the left junction.
    3: [(1483, 175), (1200, 175), (900, 176), (600, 177), (518, 175)],
    # Path 4 — Mold 2 (LEFT spur): mirrors Path 2, same corrected dense-trace method.
    4: [
        (518, 175), (527, 207), (524, 233), (524, 259), (523, 285),
        (523, 311), (524, 337), (524, 363), (528, 389), (525, 415),
        (523, 441), (522, 467), (523, 493), (522, 519), (528, 545),
        (527, 571), (517, 595), (536, 597), (535, 601), (535, 605),
        (533, 609), (532, 613), (530, 617), (528, 621), (525, 625),
        (523, 629), (520, 633), (516, 637), (512, 641), (508, 645),
        (504, 649), (494, 653), (486, 657), (465, 657), (454, 653),
        (447, 649), (443, 645), (439, 641), (434, 637), (431, 633),
        (429, 629), (426, 625), (423, 621), (421, 617), (419, 613),
        (418, 609), (417, 605), (416, 601), (415, 597), (436, 595),
        (426, 571), (426, 545), (431, 519), (431, 493), (432, 467),
        (432, 441), (430, 415), (429, 389), (432, 363), (434, 337),
        (434, 311), (434, 285), (434, 259), (436, 233), (430, 207),
        (435, 175),
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
REAL_TO_PIXEL_BREAKPOINTS: dict[int, list[tuple[float, float]]] = {
    2: [(0.0, 0.0), (0.465, 0.394), (0.546, 0.585), (1.0, 1.0)],
    4: [(0.0, 0.0), (0.459, 0.395), (0.541, 0.606), (1.0, 1.0)],
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
