import sys
from pathlib import Path

paths = [
    Path(r"C:\AI Projects\MagneMotionMonitor\mm_monitor\data\track_photo.png"),
    Path(r"C:\AI Projects\MagneMotionMonitor\mm_monitor\track_photo.py"),
    Path(r"C:\AI Projects\MagneMotionMonitor\Track Alignment program\track_points.csv"),
]

print(f"Python: {sys.executable}")
print(f"Platform: {sys.platform}")
for p in paths:
    print(f"{'EXISTS' if p.exists() else 'MISSING'}: {p}")

try:
    import PySide6
    print(f"PySide6 version: {PySide6.__version__}")
except ImportError:
    print("PySide6 is NOT installed in this Python environment.")
