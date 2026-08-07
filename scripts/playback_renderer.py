"""Render a .mmrec recording onto the real track photo for calibration review.

Outputs PNG frames (and optionally a GIF) showing pallet positions overlaid on
the photo, with station markers, so you can verify whether the current
PATH_WAYPOINTS_PX accurately represent carts moving around the real track.
"""
from __future__ import annotations
import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Project root relative to this script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mm_monitor.gui.track_panel import _Cart, resolve_pallet_spacing
from mm_monitor.recording import Recording
from mm_monitor.system_data import STATION_LOCATIONS
from mm_monitor.track_photo import build_photo_track_model, PHOTO_SIZE

# Same preference map as in track_panel.py for label layout preview.
_LABEL_PREFS = {
    12: (0, -18), 13: (0, 16), 14: (0, -18), 16: (50, -8),
    18: (0, -18), 26: (0, 16), 29: (40, -8), 30: (50, 8),
    33: (-55, -8), 34: (0, -18),
}
_KEY_STATIONS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 26, 29, 30, 33, 34}


def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | None) -> int:
    if font is None:
        return len(text) * 7 + 10
    bbox = draw.textbbox((0, 0), text, font=font)
    return max(bbox[2] - bbox[0] + 10, 44)


def _draw_station(draw: ImageDraw.ImageDraw, xy: tuple[float, float], label: str,
                  font: ImageFont.FreeTypeFont | None):
    x, y = xy
    r = 4
    draw.ellipse([x - r, y - r, x + r, y + r], fill=(212, 160, 23) if label else (136, 153, 170))
    if label and font:
        draw.text((x + 8, y - 8), label, fill=(51, 51, 85), font=font)


def _draw_cart(draw: ImageDraw.ImageDraw, xy: tuple[float, float], cid: int,
               color: tuple[int, int, int] = (41, 128, 185),
               font: ImageFont.FreeTypeFont | None = None):
    x, y = xy
    r = 11
    draw.rectangle([x - r, y - r, x + r, y + r], fill=color, outline=(11, 16, 32), width=2)
    label_font = font or ImageFont.load_default()
    text = str(cid)
    bbox = draw.textbbox((0, 0), text, font=label_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x - tw / 2, y - th / 2), text, fill=(255, 255, 255), font=label_font)

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


def _place_labels(draw: ImageDraw.ImageDraw, w: int, h: int,
                  anchors: list[tuple[tuple[float, float], str, int | None]],
                  font: ImageFont.FreeTypeFont | None):
    """Collision-aware label placement mirroring track_panel._draw_labels.
    anchors: list of ((x, y), text, station_id_or_None)."""
    LH, PAD = 14, 4

    def measure(text: str) -> int:
        if font is None:
            return max(len(text) * 7 + 10, 44)
        bbox = draw.textbbox((0, 0), text, font=font)
        return max(bbox[2] - bbox[0] + 10, 44)

    placed: list[tuple[float, float, float, float]] = []

    for (ax, ay), text, sid in anchors:
        lw = measure(text)
        hw = lw / 2
        pref = _LABEL_PREFS.get(sid) if sid else None

        if pref:
            dx, dy = pref
            candidates = [
                (ax + dx - hw, ay + dy - LH / 2, lw, LH),
                (ax - hw, ay + 4, lw, LH),
                (ax - hw, ay - LH - 4, lw, LH),
                (ax + 6, ay - LH / 2, lw, LH),
                (ax - lw - 6, ay - LH / 2, lw, LH),
                (ax - hw, ay + 20, lw, LH),
                (ax - hw, ay - LH - 20, lw, LH),
            ]
        else:
            candidates = [
                (ax - hw, ay + 4, lw, LH),
                (ax - hw, ay - LH - 4, lw, LH),
                (ax + 6, ay - LH / 2, lw, LH),
                (ax - lw - 6, ay - LH / 2, lw, LH),
                (ax - hw, ay + 20, lw, LH),
                (ax - hw, ay - LH - 20, lw, LH),
            ]

        chosen = None
        for x, y, cw, ch in candidates:
            if x < 2 or x + cw > w - 2 or y < 2 or y + ch > h - 24:
                continue
            ex1, ey1, ex2, ey2 = x - PAD, y - PAD, x + cw + PAD, y + ch + PAD
            collision = False
            for px1, py1, px2, py2 in placed:
                if not (ex2 < px1 or ex1 > px2 or ey2 < py1 or ey1 > py2):
                    collision = True
                    break
            if not collision:
                chosen = (x, y, cw, ch)
                break
        if chosen is None:
            chosen = candidates[0]
        placed.append((chosen[0] - PAD, chosen[1] - PAD,
                       chosen[0] + chosen[2] + PAD, chosen[1] + chosen[3] + PAD))

        cx, cy, cw, ch = chosen
        default_x, default_y = ax - hw, ay + 4
        if abs(cx - default_x) > 2 or abs(cy - default_y) > 2:
            # leader line
            draw.line([(ax, ay), (cx + cw / 2, cy + ch / 2)], fill=(153, 153, 187), width=1)
            # anchor dot
            r = 3
            draw.ellipse([ax - r, ay - r, ax + r, ay + r], fill=(153, 153, 187))

        if font:
            draw.text((cx, cy + 2), text, fill=(51, 51, 85), font=font)
        else:
            draw.text((cx, cy + 2), text, fill=(51, 51, 85))


def render_frame(recording: Recording, idx: int, out_path: Path, draw_stations: bool = True):
    photo_path = ROOT / "mm_monitor" / "data" / "track_photo.png"
    img = Image.open(photo_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    try:
        label_font = ImageFont.truetype("segoeui.ttf", 14)
    except Exception:
        label_font = None
    try:
        info_font = ImageFont.truetype("segoeui.ttf", 16)
    except Exception:
        info_font = ImageFont.load_default()

    model = build_photo_track_model()

    station_anchors: list[tuple[tuple[float, float], str, int | None]] = []

    if draw_stations:
        for sid, (pid, loc, name) in STATION_LOCATIONS.items():
            pt = model.point_at(pid, loc)
            if pt is None:
                continue
            is_key = sid in _KEY_STATIONS
            x, y = pt
            # The photo already prints station names on the rails, so we only
            # draw bright dots to mark the calibrated station positions; adding
            # text labels would duplicate the printed labels.
            r = 5.5 if is_key else 3
            draw.ellipse([x - r, y - r, x + r, y + r],
                         fill=(241, 196, 15) if is_key else (136, 153, 170))

    snap = recording.snapshot(idx)
    raw_carts = _snap_carts(snap)
    resolved = resolve_pallet_spacing(model, raw_carts)
    for c in raw_carts:
        xy = resolved.get(c.id) or model.point_at(c.path, c.pos)
        if xy is None:
            continue
        _draw_cart(draw, xy, c.id, font=label_font)
        # Cart velocity labels are useful live, but in a static calibration
        # render they add clutter on top of the already-labeled photo.

    w, h = img.size
    _place_labels(draw, w, h, station_anchors, label_font)

    t = recording.time_at(idx)
    draw.text((12, 12), f"Frame {idx}  t={t:.1f}s  ({len(raw_carts)} carts)",
              fill=(26, 26, 46), font=info_font)

    img.save(out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render recording frames on the track photo")
    parser.add_argument("recording", type=Path, help=".mmrec file to render")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "track_path_history" / "playback_render",
                        help="Output directory for rendered frames")
    parser.add_argument("--frames", type=int, nargs="+", default=None,
                        help="Specific frame indices to render (default: 0, mid, last)")
    parser.add_argument("--gif", action="store_true", help="Also render a GIF of every Nth frame")
    parser.add_argument("--gif-step", type=int, default=5, help="Frame step for GIF")
    args = parser.parse_args()

    rec = Recording.load(args.recording)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    indices = args.frames or [0, len(rec) // 4, len(rec) // 2, 3 * len(rec) // 4, len(rec) - 1]
    for idx in indices:
        out = out_dir / f"frame_{idx:04d}.png"
        render_frame(rec, idx, out)
        print(out)

    if args.gif:
        frames = []
        for idx in range(0, len(rec), args.gif_step):
            out = out_dir / f"gif_tmp_{idx:04d}.png"
            render_frame(rec, idx, out)
            frames.append(Image.open(out))
        gif_path = out_dir / "playback.gif"
        frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                       duration=50, loop=0)
        print(gif_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
