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
    # other. Densely measured (numpy column-trace of both legs + the U-turn,
    # every ~2-4px) after a coarser 9-point version made a cart look like it
    # "stopped before the turn" — the coarse straight-line legs didn't reflect
    # how much of the real curve happens close to the bottom vs. near the top.
    2: [
        (1449, 175), (1426, 199), (1432, 225), (1434, 251), (1436, 277),
        (1438, 303), (1440, 329), (1442, 355), (1450, 381), (1450, 407),
        (1448, 433), (1450, 459), (1452, 485), (1454, 511), (1456, 537),
        (1462, 563), (1456, 589), (1423, 657), (1473, 603), (1471, 605),
        (1472, 607), (1471, 609), (1469, 611), (1469, 613), (1468, 615),
        (1468, 617), (1467, 619), (1465, 621), (1464, 623), (1463, 625),
        (1463, 627), (1460, 629), (1459, 631), (1458, 633), (1455, 635),
        (1453, 637), (1452, 639), (1450, 641), (1448, 643), (1445, 645),
        (1443, 647), (1440, 649), (1436, 651), (1431, 653), (1427, 655),
        (1401, 655), (1395, 653), (1390, 651), (1386, 649), (1384, 647),
        (1382, 645), (1378, 643), (1375, 641), (1374, 639), (1372, 637),
        (1370, 635), (1369, 633), (1367, 631), (1365, 629), (1364, 627),
        (1362, 625), (1361, 623), (1360, 621), (1359, 619), (1358, 617),
        (1357, 615), (1356, 613), (1354, 611), (1354, 609), (1352, 607),
        (1352, 605), (1352, 603), (1413, 657), (1371, 589), (1362, 563),
        (1362, 537), (1361, 511), (1360, 485), (1358, 459), (1357, 433),
        (1352, 407), (1352, 381), (1352, 355), (1350, 329), (1349, 303),
        (1348, 277), (1345, 251), (1342, 225), (1350, 199), (1358, 175),
    ],
    # Path 3 — long straight connector (hosts station 33, HOME/Cold Start, near
    # its far end): right junction (Path 1's end) across to the left junction.
    3: [(1483, 175), (1200, 175), (900, 176), (600, 177), (518, 175)],
    # Path 4 — Mold 2 (LEFT spur): mirrors Path 2, same dense-trace method.
    4: [
        (518, 175), (524, 201), (524, 227), (524, 253), (523, 279),
        (523, 305), (523, 331), (523, 357), (528, 383), (528, 409),
        (524, 435), (523, 461), (522, 487), (522, 513), (526, 539),
        (528, 565), (518, 591), (510, 605), (534, 607), (533, 609),
        (533, 611), (532, 613), (532, 615), (530, 617), (530, 619),
        (528, 621), (527, 623), (525, 625), (524, 627), (523, 629),
        (521, 631), (520, 633), (518, 635), (516, 637), (515, 639),
        (512, 641), (510, 643), (508, 645), (506, 647), (504, 649),
        (498, 651), (494, 653), (491, 655), (486, 657), (465, 657),
        (459, 655), (454, 653), (450, 651), (447, 649), (444, 647),
        (443, 645), (441, 643), (439, 641), (437, 639), (434, 637),
        (433, 635), (431, 633), (430, 631), (429, 629), (426, 627),
        (426, 625), (424, 623), (423, 621), (422, 619), (421, 617),
        (420, 615), (419, 613), (419, 611), (418, 609), (418, 607),
        (444, 605), (434, 591), (426, 565), (430, 539), (431, 513),
        (432, 487), (432, 461), (432, 435), (428, 409), (428, 383),
        (434, 357), (434, 331), (434, 305), (434, 279), (435, 253),
        (435, 227), (435, 201), (435, 175),
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

    def point_at(self, path_id: int, pos_m: float) -> tuple[float, float] | None:
        pts = self._pts.get(path_id)
        s = self._s.get(path_id)
        if not pts or not s or s[-1] <= 0:
            return None
        real_len = self._real_lengths.get(path_id, 0.0)
        frac = 0.0 if real_len <= 0 else max(0.0, min(1.0, pos_m / real_len))
        target = frac * s[-1]

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
