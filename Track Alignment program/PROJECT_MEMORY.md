# MagneMotion Track Alignment Tool — Project Memory

## Purpose
Interactive PySide6 desktop editor for dragging MagneMotion LITE track waypoints onto the track photo and exporting the corrected `PATH_WAYPOINTS_PX` block back to `mm_monitor/track_photo.py`.

## Location
`C:\AI Projects\MagneMotionMonitor\Track Alignment program\`

## Files
- `main.py` — PySide6 alignment application
- `run.bat` — Windows launcher (`python main.py`)
- `track_points.csv` — Reference station list extracted from the Magnemotion Position Edits screen
- `setup.py` — Package metadata (optional install)

## Key Paths (Windows-native)
- Project root: `C:\AI Projects\MagneMotionMonitor`
- Default image: `..\mm_monitor\data\track_photo.png`
- Default waypoints: `..\mm_monitor\track_photo.py`
- Backup history: `..\track_path_history\`

## Current Status
- Tool launches, but paths were originally written as WSL-style (`/mnt/c/...`) and must be Windows-native for Windows Python.
- Black-screen fix applied (light background, `fitInView` after window shown).
- `track_points.csv` created with station names/command/actual/location, but no pixel coordinates yet.

## Next Steps
1. Convert all hard-coded paths in `main.py` to Windows-native paths.
2. Verify the program auto-loads the current `track_photo.png` and its waypoints on launch.
3. After points are aligned via the tool, click **Save** to update `track_photo.py`.
4. Timestamped waypoint JSON backups are written to `..\track_path_history\` on every save.

## How to Run
Open CMD/PowerShell in the tool folder:
```cmd
cd "C:\AI Projects\MagneMotionMonitor\Track Alignment program"
run.bat
```

## Notes
- Left-click + drag: move waypoint
- Mouse wheel: zoom
- Middle/right drag: pan
- Add Point Mode: click image to add a new waypoint
- Double-click point or Delete Selected Point button: remove waypoint
- Save button: writes `PATH_WAYPOINTS_PX` back to `track_photo.py`

_Last updated: session of track alignment tool creation_
