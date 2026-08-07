"""Clean schematic render of a .mmrec recording for calibration/validation.

Uses the vector track geometry (track_geometry.py) and the recording's cart
positions. No photo background, so there is no duplicated station text — just
rails, station dots, and numbered carts. This is useful when the track photo
already has labels baked into it and you want an uncluttered view of whether
carts follow the rails correctly.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mm_monitor.gui.track_panel import _Cart, resolve_pallet_spacing
from mm_monitor.recording import Recording
from mm_monitor.system_data import STATION_LOCATIONS
from mm_monitor.track_geometry import build_track

_PATH_COLORS = {
    1: (91, 107, 140), 2: (41, 128, 185), 3: (127, 140, 141),
    4: (142, 68, 173), 5: (91, 107, 140), 6: (22, 160, 133),
}
_KEY_STATIONS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 26, 29, 30, 33, 34}


def _cart_to_screen(track, x: float, y: float, margin: int) -> tuple[float, float]:
    minx, miny, maxx, maxy = track.bounds
    W, H = max(maxx - minx, 0.1), max(maxy - miny, 0.1)
    size = 1200
    s = (size - 2 * margin) / max(W, H)
    # center, flip Y for image coords
    offx = margin + (size - 2 * margin - W * s) / 2 - minx * s
    offy = margin + (size - 2 * margin - H * s) / 2 + miny * s
    return (offx + x * s, offy - y * s)


def _snap_carts(snap) -> list[_Cart]:
    carts = []
    for i in range(1, 65):
        vs = snap.vehicle_status[i]
        if not vs or not (vs.get("Path_ID") or 0):
            continue
        carts.append(_Cart(
            cid=i,
            path=vs.get("Path_ID") or 0,
            pos=float(vs.get("Position") or 0.0),
            vel=float(vs.get("Velocity") or 0.0),
            dest=vs.get("Dest_Station_ID") or 0,
            alarm=None,
        ))
    return carts


def render_frame(recording: Recording, idx: int, out_path: Path, size: int = 1200):
    track = build_track()
    margin = 50
    img = Image.new("RGBA", (size, int(size * 0.55)), (240, 244, 255, 255))
    draw = ImageDraw.Draw(img)

    # rails
    for pid, pg in track.paths.items():
        pts = [_cart_to_screen(track, x, y, margin) for (x, y) in pg.abs_pts]
        if len(pts) < 2:
            continue
        color = _PATH_COLORS.get(pid, (85, 85, 102))
        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i + 1]], fill=color, width=10)

    # stations
    for sid, (pth, loc, name) in STATION_LOCATIONS.items():
        pt = track.point_at(pth, loc)
        if pt is None:
            continue
        x, y = _cart_to_screen(track, pt[0], pt[1], margin)
        is_key = sid in _KEY_STATIONS
        r = 7 if is_key else 4
        draw.ellipse([x - r, y - r, x + r, y + r],
                     fill=(241, 196, 15) if is_key else (136, 153, 170),
                     outline=(60, 60, 80), width=2)

    # carts — true metric positions; spacing resolver is photo-only.
    snap = recording.snapshot(idx)
    raw = _snap_carts(snap)
    try:
        font = ImageFont.truetype("segoeui.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    for c in raw:
        pt = track.point_at(c.path, c.pos)
        if pt is None:
            continue
        x, y = _cart_to_screen(track, pt[0], pt[1], margin)
        r = 11
        draw.rectangle([x - r, y - r, x + r, y + r], fill=(41, 128, 185),
                       outline=(11, 16, 32), width=2)
        text = str(c.id)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((x - tw / 2, y - th / 2), text, fill=(255, 255, 255), font=font)

    try:
        info_font = ImageFont.truetype("segoeui.ttf", 18)
    except Exception:
        info_font = ImageFont.load_default()
    t = recording.time_at(idx)
    draw.text((15, 15), f"Schematic  Frame {idx}  t={t:.1f}s  ({len(raw)} carts)",
              fill=(26, 26, 46), font=info_font)

    img.save(out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    parser.add_argument("--out-dir", type=Path,
                        default=ROOT / "track_path_history" / "schematic_render")
    parser.add_argument("--frames", type=int, nargs="+", default=None)
    args = parser.parse_args()

    rec = Recording.load(args.recording)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    indices = args.frames or [0, len(rec) // 4, len(rec) // 2, 3 * len(rec) // 4, len(rec) - 1]
    for idx in indices:
        out = args.out_dir / f"frame_{idx:04d}.png"
        render_frame(rec, idx, out)
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
