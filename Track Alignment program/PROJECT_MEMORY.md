# MagneMotion Track Alignment Tool — Project Memory

## Purpose
Interactive PySide6 desktop editor for placing every named MagneMotion LITE
pallet stop onto the track photo, so the monitor app can build an accurate live
visual representation of where each pallet is and what it is doing.

## Location
`C:\AI Projects\MagneMotionMonitor\Track Alignment program\`

## Files
- `main.py` — PySide6 stop-placement application
- `run.bat` — Windows launcher (`python main.py`)
- `track_points.csv` — Reference station list extracted from the Magnemotion Position Edits screen
- `track_points_adjusted.csv` — Output of the tool: same stops plus `PixelX`/`PixelY`
- `setup.py` — Package metadata (optional install)

## Current design (v3 — stop-centric navigation)
The tool is now a **full stop-placement navigator**.

- **White dots with labels** — every named pallet stop from `track_points.csv`,
  draggable to the correct rail position.
- **Colored lines** — the interpolated 6 PLC paths so you can see which rail a
  stop belongs to (1 red, 2 blue, 3 green, 4 purple, 5 orange, 6 cyan).
- **Yellow dots** — anchor points for the continuous master rail path (advanced,
  collapsed by default).
- **Stops list** — complete searchable list of all stopping points on the left;
  click any item to jump to it. List shows name, PLC path, real meter position,
  and current pixel coordinates.
- **Selected stop editor** — type exact pixel X/Y.
- **Save Stop Positions** — writes `track_points_adjusted.csv` with the placed
  pixel coordinates. These adjusted coordinates are what the monitor app should
  use for rendering station/pallet locations.

### Workflow
1. Launch `run.bat`. It loads `mm_monitor/data/track_photo.png`, the current
   `mm_monitor/track_photo.py` waypoints (for rail path color), and
   `track_points.csv` stops.
2. Drag each white stop dot onto its exact rail position.
3. Use the search box to filter long lists (e.g. type "Load" or "Mold 1").
4. Click a stop in the list to center the view on it.
5. Click **Save Stop Positions** when all stops are placed.
6. If the colored rail path itself is wrong, expand **Rail Path Anchors** and
   drag the yellow anchor dots, then click **Save Path to track_photo.py**.

### Station mapping
`track_points.csv` columns:
- `Station` — human-readable name (e.g. "Mold 1 Load 2", "HOME / Cold Start").
- `Command` / `Actual` — real distance in meters along the path.
- `TrackLocation` — physical rail section, mapped to PLC path ID:
  - `Top Main Rail` → Path 6
  - `Right Vertical Loop` → Path 2
  - `Left Vertical Loop` → Path 4
  - `Middle Connector` → Path 3

The tool uses the current `track_photo.py` waypoints + `track_geometry.py` real
path lengths to compute an initial pixel (x, y) for each stop. After you drag a
stop, its pixel position is recorded directly.

### Defaults
- Window opens at 1800×1000.
- Anchor simplification uses RDP epsilon = 4 px.
- Interpolation between anchors is linear, so adding more anchors gives smoother curves.
- Resample spacing defaults to 6 px between PLC path points.

## How to Run
Open CMD/PowerShell in the tool folder:
```cmd
cd "C:\AI Projects\MagneMotionMonitor\Track Alignment program"
run.bat
```

## Notes
- Left-click + drag stop dot: move the stop
- Click stop in list: center and select it
- Edit Pixel X/Y spin boxes for exact placement
- Mouse wheel: zoom
- Middle/right drag: pan
- Rail-path anchors are hidden by default; expand the **Rail Path Anchors** group if needed
- Save Stop Positions writes `track_points_adjusted.csv`
- Save Path writes `PATH_WAYPOINTS_PX` back to `mm_monitor/track_photo.py`
- Timestamped waypoint JSON backups are written to `../track_path_history/` on every path save

_Last updated: 2026-08-08 — rewrote as stop-centric navigator with full stop list, drag placement, and pixel-coordinate save_
