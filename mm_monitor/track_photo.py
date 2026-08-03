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
    1: [
        (1485.8776532269771, 126.2102010258049), (1487.8362804530773, 134.32745547800442), (1487.263089879491, 150.1161241071498), (1481.0611199373366, 164.06036385811043),
        (1461.880854275564, 178.29165404075468),
    ],
    2: [
        (1455.0478144751912, 206.60857669187482), (1467.8546461468452, 274.4842811719243), (1485.8402891738804, 388.76614624925884), (1496.5367622703557, 455.10185993322483),
        (1494.2496079356831, 459.2896823279316), (1510.6929808856082, 480.1669077054223), (1521.9, 503.6), (1521.2, 520.7),
        (1520.5, 537.8), (1520.3, 541.6), (1519.9, 551.1), (1518.2, 564.2),
        (1516.1, 581.2), (1514.6, 590.4), (1505.2, 599.8), (1497.1, 607.9),
        (1484.9, 612.3), (1481.2, 613.1), (1473.8, 614.8), (1457.2, 617.4),
        (1449.8, 615.7), (1438.7, 613.1), (1431.2, 611.4), (1420.9, 607.2),
        (1414.5, 603.0), (1408.2, 598.8), (1400.3, 593.5), (1395.6, 590.4),
        (1392.9, 581.5), (1390.6, 572.2), (1384.9, 548.2), (1384.7, 542.6),
        (1384.2, 531.2), (1383.5, 512.2), (1383.0, 500.8), (1382.1, 478.0),
        (1381.6, 464.8), (1379.8, 419.2), (1379.4, 409.7), (1378.8, 394.5),
        (1378.0, 375.6), (1377.4, 360.4), (1376.7, 341.4), (1375.7, 316.7),
        (1375.1, 303.5), (1372.5, 275.1), (1371.4, 263.8), (1370.2, 252.4),
        (1366.0, 233.9), (1363.2, 222.9), (1360.0, 210.0),
    ],
    3: [
        (1360.0, 210.0), (1342.7, 210.0), (1321.2, 210.0), (1299.6, 210.0),
        (1269.4, 210.0), (1249.9, 210.0), (1232.7, 210.0), (1211.1, 210.0),
        (1187.4, 210.0), (1155.0, 210.0), (1129.1, 210.0), (1111.8, 210.0),
        (1092.4, 210.0), (1077.3, 210.0), (1062.2, 210.0), (1049.2, 210.0),
        (1027.7, 210.0), (1001.8, 210.0), (988.8, 210.0), (967.2, 210.0),
        (945.7, 210.0), (928.4, 210.0), (904.7, 210.0), (887.4, 210.0),
        (872.3, 210.0), (855.0, 210.0), (837.8, 210.0), (820.5, 210.0),
        (803.2, 210.0), (788.1, 210.0), (773.0, 210.0), (757.9, 210.0),
        (740.7, 210.0), (721.2, 210.0), (701.8, 210.0), (686.7, 210.0),
        (671.6, 210.0), (658.7, 210.0), (643.5, 210.0), (624.1, 210.0),
        (602.5, 210.0), (589.6, 210.0), (576.6, 210.0), (563.7, 210.0),
        (548.6, 210.0), (533.5, 210.0), (518.4, 210.0), (496.8, 210.0),
        (486.0, 210.0), (473.1, 210.0), (449.3, 210.0), (436.4, 210.0),
        (408.3, 210.0), (393.2, 210.0), (378.1, 210.0), (347.9, 210.0),
        (319.8, 210.0), (300.4, 210.0), (270.2, 210.0), (252.9, 210.0),
        (240.0, 210.0),
    ],
    4: [
        (240.0, 210.0), (229.5, 254.7), (228.9, 260.7), (225.8, 292.5),
        (224.3, 318.4), (223.5, 338.4), (223.1, 346.3), (222.9, 352.3),
        (221.7, 382.3), (221.0, 400.2), (220.8, 406.2), (220.6, 410.2),
        (219.1, 448.1), (218.5, 462.1), (218.4, 466.1), (218.0, 476.1),
        (217.8, 480.1), (216.8, 506.0), (216.3, 518.0), (215.9, 528.0),
        (215.2, 546.0), (214.8, 551.9), (212.0, 573.7), (211.5, 577.7),
        (210.3, 587.6), (204.6, 595.4), (203.2, 596.8), (194.7, 605.3),
        (181.0, 612.1), (163.4, 616.1), (161.5, 616.5), (151.7, 617.3),
        (122.5, 610.6), (115.5, 607.0), (103.9, 599.2), (100.5, 597.0),
        (87.3, 579.0), (85.8, 573.2), (84.4, 567.4), (82.9, 561.6),
        (79.8, 546.0), (78.9, 522.0), (78.8, 520.0), (78.5, 512.0),
        (77.6, 490.1), (76.4, 460.1), (76.1, 452.1), (75.8, 446.2),
        (75.1, 428.2), (74.2, 404.2), (73.6, 390.3), (72.7, 368.3),
        (71.1, 326.4), (70.8, 320.4), (70.6, 314.4), (70.5, 312.4),
        (67.1, 270.6), (58.4, 223.6), (56.0, 213.9), (55.5, 211.9),
        (55.0, 210.0),
    ],
    5: [
        (55.0, 210.0), (52.1, 208.1), (47.8, 205.2), (45.7, 203.8),
        (44.9, 203.3), (43.5, 202.3), (40.0, 199.9), (40.0, 196.4),
        (40.0, 193.0), (40.0, 191.2), (40.0, 186.0), (40.0, 185.2),
        (40.0, 184.3), (40.0, 183.5), (40.0, 182.6), (40.0, 181.7),
        (40.0, 180.0),
    ],
    6: [
        (40.0, 180.0), (53.5, 152.9), (68.3, 134.8), (92.7, 119.5),
        (135.2, 111.5), (175.9, 107.4), (212.1, 104.4), (249.9, 102.5),
        (277.2, 101.1), (318.0, 99.6), (354.4, 98.9), (381.6, 98.4),
        (402.8, 98.0), (433.1, 97.7), (468.0, 97.3), (498.3, 97.0),
        (543.7, 96.6), (574.0, 96.3), (613.4, 95.9), (658.8, 95.4),
        (686.1, 95.1), (734.6, 95.0), (758.8, 95.0), (790.6, 95.0),
        (827.0, 95.0), (846.7, 95.0), (890.6, 95.0), (910.3, 95.0),
        (942.1, 95.0), (973.9, 95.0), (992.1, 95.0), (1020.9, 95.0),
        (1051.2, 95.0), (1083.0, 95.0), (1107.2, 95.0), (1130.0, 95.0),
        (1142.1, 95.0), (1157.2, 95.0), (1181.5, 95.0), (1197.7201961105573, 96.13941166832849),
        (1210.9827455478005, 89.30294165835762), (1233.0, 95.0), (1252.6231377689144, 81.7068638695011), (1269.2580421712605, 80.56745220117264),
        (1293.0052982618756, 82.8462755378296), (1314.9535349052774, 83.22607942727242), (1346.7880438096765, 84.08568720615804), (1369.1274554780048, 82.80686386950109),
        (1391.7776532269772, 82.24823664340131), (1413.0288315287364, 82.15117830175897), (1441.6894198604082, 84.13784606070291), (1459.0096159709656, 92.56784769911883),
        (1476.4431443225785, 106.79000491524772),
    ],
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
