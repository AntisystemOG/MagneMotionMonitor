"""Track geometry engine for the S7000 Boxing Station MagneMover LITE loop.

Parses the MagneMover LITE track file (TrackFile.mmtrk) into real 2-D geometry so
the Live Track view can place each cart at its true (path, position) on the layout.

Each path is a sequence of straight and 90° curve motors with ABSOLUTE orientation
(up/down/left/right), so each path's shape is fully determined; only its starting
point depends on the previous path it connects from (path_start <id> <prev>).

Coordinates are in meters, math convention (x right, y up). The renderer flips Y.
"""
from __future__ import annotations
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

# Embedded track (matches mm_monitor/data/TrackFile.mmtrk) so the EXE needs no
# external file. If the data file is present it is preferred (lets you swap tracks).
TRACK_MMTRK = """
path_start 1 6
motor_r_curve up
motor_q_meter right
path_start 2 6
motor_q_meter up
motor_1_meter up
motor_1_meter up
motor_r_curve up
motor_r_curve right
motor_1_meter down
motor_1_meter down
motor_l_curve down
path_start 3 1
motor_1_meter right
motor_1_meter right
motor_1_meter right
motor_1_meter right
motor_q_meter right
motor_1_meter right
path_start 4 3
motor_l_curve right
motor_1_meter up
motor_1_meter up
motor_r_curve up
motor_r_curve right
motor_1_meter down
motor_1_meter down
motor_l_curve down
path_start 5 3
motor_q_meter right
motor_q_meter right
path_start 6 4
motor_1_meter right
motor_1_meter right
motor_r_curve right
motor_r_curve down
motor_1_meter left
motor_1_meter left
motor_1_meter left
motor_1_meter left
motor_1_meter left
motor_1_meter left
motor_1_meter left
motor_1_meter left
motor_r_curve left
"""

# Centerline radius of a MagneMover LITE 90° curve motor, in meters.
# 0.2 m keeps curves realistic with only a ~0.3 m loop-closure gap (bridged with
# junction markers in the renderer). See _solve_closure_radius() to re-tune.
ML_CURVE_RADIUS = 0.2

_ORIENT = {
    "right": (1.0, 0.0),
    "left":  (-1.0, 0.0),
    "up":    (0.0, 1.0),
    "down":  (0.0, -1.0),
}
_CURVE_STEPS = 12


def _rot(v, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


@dataclass
class _Seg:
    kind: str          # "straight" | "curve"
    orient: str        # entry orientation
    length: float = 0.0   # straight length (m)
    turn: int = 0      # +1 left (ccw), -1 right (cw)


@dataclass
class PathGeom:
    pid: int
    prev: int
    segs: list = field(default_factory=list)
    pts: list = field(default_factory=list)      # local (x,y) densified polyline
    s: list = field(default_factory=list)        # cumulative arc length per pt
    end_off: tuple = (0.0, 0.0)                   # end - start (local)
    abs_pts: list = field(default_factory=list)  # translated to absolute coords

    @property
    def length(self) -> float:
        return self.s[-1] if self.s else 0.0


def parse_mmtrk(text: str) -> dict[int, PathGeom]:
    paths: dict[int, PathGeom] = {}
    cur: PathGeom | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tok = line.split()
        cmd = tok[0]
        if cmd == "path_start":
            pid = int(tok[1])
            prev = int(tok[2]) if len(tok) > 2 else 0
            cur = PathGeom(pid=pid, prev=prev)
            paths[pid] = cur
        elif cmd == "motor_1_meter" and cur:
            cur.segs.append(_Seg("straight", tok[1], 1.0))
        elif cmd == "motor_q_meter" and cur:
            cur.segs.append(_Seg("straight", tok[1], 0.25))
        elif cmd == "motor_r_curve" and cur:
            cur.segs.append(_Seg("curve", tok[1], turn=-1))
        elif cmd == "motor_l_curve" and cur:
            cur.segs.append(_Seg("curve", tok[1], turn=+1))
    return paths


def _walk(path: PathGeom, R: float):
    pts = [(0.0, 0.0)]
    s = [0.0]
    cur = (0.0, 0.0)
    acc = 0.0
    for seg in path.segs:
        o = _ORIENT[seg.orient]
        if seg.kind == "straight":
            end = (cur[0] + o[0] * seg.length, cur[1] + o[1] * seg.length)
            acc += seg.length
            pts.append(end)
            s.append(acc)
            cur = end
        else:  # curve, 90°
            heading = o
            normal = _rot(heading, 90 if seg.turn > 0 else -90)
            center = (cur[0] + R * normal[0], cur[1] + R * normal[1])
            start_ang = math.atan2(cur[1] - center[1], cur[0] - center[0])
            sweep = math.radians(90) * (1 if seg.turn > 0 else -1)
            seg_len = R * math.radians(90)
            for i in range(1, _CURVE_STEPS + 1):
                ang = start_ang + sweep * (i / _CURVE_STEPS)
                pt = (center[0] + R * math.cos(ang), center[1] + R * math.sin(ang))
                acc += seg_len / _CURVE_STEPS
                pts.append(pt)
                s.append(acc)
                cur = pt
    path.pts = pts
    path.s = s
    path.end_off = (cur[0], cur[1])


class TrackModel:
    def __init__(self, paths: dict[int, PathGeom]):
        self.paths = paths
        self._resolve_layout()
        self._compute_bounds()

    def _resolve_layout(self):
        abs_start: dict[int, tuple] = {1: (0.0, 0.0)}
        # Fixpoint resolve: a path starts where its previous path ends.
        for _ in range(len(self.paths) + 2):
            for pid, pg in self.paths.items():
                if pid in abs_start:
                    continue
                if pg.prev in abs_start:
                    ps = abs_start[pg.prev]
                    pe = self.paths[pg.prev].end_off
                    abs_start[pid] = (ps[0] + pe[0], ps[1] + pe[1])
        for pid, pg in self.paths.items():
            ox, oy = abs_start.get(pid, (0.0, 0.0))
            pg.abs_pts = [(x + ox, y + oy) for (x, y) in pg.pts]

    def _compute_bounds(self):
        xs, ys = [], []
        for pg in self.paths.values():
            for (x, y) in pg.abs_pts:
                xs.append(x)
                ys.append(y)
        if not xs:
            self.bounds = (0.0, 0.0, 1.0, 1.0)
        else:
            self.bounds = (min(xs), min(ys), max(xs), max(ys))

    def point_at(self, pid: int, pos_m: float) -> tuple[float, float] | None:
        pg = self.paths.get(pid)
        if not pg or not pg.abs_pts:
            return None
        total = pg.length
        pos = max(0.0, min(pos_m, total))
        s = pg.s
        # binary search for segment
        lo, hi = 0, len(s) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if s[mid] <= pos:
                lo = mid
            else:
                hi = mid
        seg_len = s[hi] - s[lo]
        t = 0.0 if seg_len <= 0 else (pos - s[lo]) / seg_len
        a, b = pg.abs_pts[lo], pg.abs_pts[hi]
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def closure_error(self) -> float:
        """Distance between where path 6 ends and path 1 begins (loop gap)."""
        if 6 not in self.paths or 1 not in self.paths:
            return 0.0
        p6 = self.paths[6].abs_pts[-1]
        p1 = self.paths[1].abs_pts[0]
        return math.hypot(p6[0] - p1[0], p6[1] - p1[1])


def _build_from_text(text: str, R: float) -> TrackModel:
    paths = parse_mmtrk(text)
    for pg in paths.values():
        _walk(pg, R)
    return TrackModel(paths)


def _solve_closure_radius(text: str) -> float:
    """1-D search for the curve radius that makes the main loop close (no gaps
    at path junctions). The loop closes in Y for any radius and in X at one
    specific radius, so this finds a near-exact closure."""
    best_R, best_err = ML_CURVE_RADIUS, float("inf")
    R = 0.05
    while R <= 0.60:
        err = _build_from_text(text, R).closure_error()
        if err < best_err:
            best_err, best_R = err, R
        R += 0.0025
    return round(best_R, 4)


def _load_track_text() -> str:
    data_file = Path(__file__).parent / "data" / "TrackFile.mmtrk"
    try:
        if data_file.exists():
            return data_file.read_text()
    except Exception:
        pass
    return TRACK_MMTRK


_solved_R: float | None = None


def build_track(R: float | None = None) -> TrackModel:
    """Build the track model. If R is None, auto-solve the curve radius that
    closes the loop (gap-free junctions) and cache it."""
    global _solved_R
    text = _load_track_text()
    if R is None:
        if _solved_R is None:
            _solved_R = _solve_closure_radius(text)
        R = _solved_R
    return _build_from_text(text, R)


if __name__ == "__main__":
    text = _load_track_text()
    R = _solve_closure_radius(text)
    print(f"Best closure radius: {R} m")
    model = _build_from_text(text, R)
    print(f"Closure error: {model.closure_error():.4f} m")
    print(f"Track bounds: {tuple(round(b,2) for b in model.bounds)}")
    for pid in sorted(model.paths):
        print(f"  Path {pid}: length={model.paths[pid].length:.3f} m, "
              f"prev={model.paths[pid].prev}")
    # sample: station 30 on path 6 at 10.1 m
    pt = model.point_at(6, 10.1)
    print(f"Station 30 (path 6 @ 10.1m) -> {tuple(round(c,2) for c in pt)}")
