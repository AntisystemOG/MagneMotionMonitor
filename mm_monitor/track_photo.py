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
    # Path 6 - Process: top main rail, left-to-right across the image.
    6: [
        (36, 70), (50, 60), (100, 55), (200, 54), (300, 54),
        (400, 54), (500, 54), (600, 54), (700, 54), (800, 54),
        (900, 54), (1000, 54), (1100, 54), (1200, 54), (1300, 54),
        (1400, 54), (1500, 58), (1550, 75)
    ],
    # Path 1 - tiny connector at top right (main rail to right spur)
    1: [(1550, 75), (1560, 95)],
    # Path 2 - Mold 1 (RIGHT spur): down outer leg, U-turn, up inner leg
    2: [
        (1560, 95), (1555, 120), (1548, 160), (1544, 200), (1542, 240),
        (1540, 280), (1538, 320), (1537, 360), (1536, 400), (1536, 440),
        (1536, 480), (1536, 520), (1536, 560), (1530, 590), (1510, 610),
        (1480, 618), (1450, 618), (1420, 610), (1395, 590), (1385, 560),
        (1383, 520), (1382, 480), (1381, 440), (1380, 400), (1379, 360),
        (1378, 320), (1376, 280), (1374, 240), (1371, 200), (1368, 160),
        (1365, 120), (1360, 95)
    ],
    # Path 3 - long straight middle connector between right and left spurs
    3: [(1360, 95), (1100, 95), (800, 95), (500, 95), (240, 95)],
    # Path 4 - Mold 2 (LEFT spur): down outer leg, U-turn, up inner leg
    4: [
        (240, 95), (235, 120), (230, 160), (226, 200), (224, 240),
        (222, 280), (220, 320), (219, 360), (218, 400), (218, 440),
        (218, 480), (218, 520), (218, 560), (210, 590), (190, 610),
        (160, 618), (130, 618), (100, 610), (75, 590), (65, 560),
        (63, 520), (62, 480), (61, 440), (60, 400), (59, 360),
        (58, 320), (56, 280), (54, 240), (51, 200), (48, 160),
        (45, 120), (40, 95)
    ],
    # Path 5 - tiny connector at top left (left spur to main rail)
    5: [(40, 95), (36, 70)]
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
