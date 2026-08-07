"""Pre-build verification for MagneMotion Monitor.

Run from the project root to confirm track_photo.py and the waypoints are
healthy before building the EXE. Exits non-zero if the photo model cannot be
built or any path has zero pixel length.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mm_monitor.track_photo import build_photo_track_model, PATH_WAYPOINTS_PX


def main() -> int:
    try:
        model = build_photo_track_model()
    except Exception as exc:
        print(f"FAIL: build_photo_track_model() raised: {exc}")
        return 1

    counts = {pid: len(pts) for pid, pts in PATH_WAYPOINTS_PX.items()}
    lengths = {pid: model.pixel_length(pid) for pid in counts}

    print("Path waypoint counts:", counts)
    print("Path pixel lengths:", lengths)

    for pid in sorted(counts):
        if lengths[pid] <= 0:
            print(f"FAIL: path {pid} has zero pixel length")
            return 1
        if counts[pid] < 2:
            print(f"FAIL: path {pid} has fewer than 2 waypoints")
            return 1

    print("PASS: all paths have valid photo model data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
