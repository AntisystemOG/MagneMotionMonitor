# MagneMotion Monitor — Project Memory

> Living document to bring people and LLMs up to speed on what this app is, how it
> works, the real-system facts it depends on, and the non-obvious fixes made.
> Last updated for **v27.3.1** (WEEK.DAY.BUILD — see Build section).

## What it is
A standalone Windows desktop app (Python + PySide6) that monitors a **Rockwell/MagneMotion
MagneMover LITE** independent-cart system at the **S7000 Module Assembly Boxing station**.
It connects to the station's Allen-Bradley PLC over EtherNet/IP (via `pycomm3`), reads the
MagneMotion interface tags, and visualizes system health, cart positions on the real track,
the two operator operations (home-out and cleanout), alarms/blockers, and supports
recording live data for offline playback.

This is **not** related to the separate "PLCTools" project.

## Run / build
```bash
cd "C:\AI Projects\MagneMotionMonitor"
pip install -r requirements.txt        # PySide6, pycomm3
python main.py
```
Default PLC IP is pre-filled (192.168.1.10). Click **Connect**.

## Tests
```bash
pip install -r requirements-dev.txt    # adds pytest
pytest                                  # 57 tests, headless Qt, no PLC needed
```
## Build the EXE / versioning
```bash
python release.py             # bump version, then build dist/MagneMotionMonitor.exe
python release.py --no-build  # just bump mm_monitor/version.py
```
Produces a single double-clickable **`dist/MagneMotionMonitor.exe`** (~48 MB, windowed/no console).
`MagneMotionMonitor.spec` bundles `mm_monitor/data/` and pulls in all `pycomm3` submodules
(`collect_submodules`) so the EXE never fails on a dynamic import. `dist/` and `build/` are gitignored.

**App icon**: `assets/app_icon.ico` (built from the MagneMotion company logo, PNG source in
`Pictures and graphics\Magnamotion log.PNG` — a wide wordmark padded onto a transparent square
canvas, not stretched, then saved at 7 sizes 16-256px). Two separate places reference it: the
`.spec`'s `icon=` param sets the **.exe file's own icon** (what Explorer/taskbar-pin shows before
running), and `main.py`'s `app.setWindowIcon(...)` sets the **running window/taskbar icon** —
both need the file; `_resource_path()` in `main.py` resolves it whether running from source or
frozen (checks `sys._MEIPASS` first, same pattern as `track_photo.py`'s `_PHOTO_PATH`).
**Pictures/graphics for this project** are saved to `Pictures and graphics\` in the project root —
check there before asking the user to save a new image file.

**Version scheme = `WEEK.DAY.BUILD`** (e.g. `26.5.1` = ISO week 26, Fri, build 1). `release.py`
writes `mm_monitor/version.py`; `system_data.APP_VERSION` imports it (falls back to `"dev"` from
source). The running version shows in the **window title** and the **connection-bar** (top-right).
BUILD resets to 1 each new day and increments on same-day rebuilds.

`tests/` is a headless smoke + logic suite (Qt forced to `offscreen` in `conftest.py`).
The important file is `test_panels_smoke.py` — it builds every panel and the MainWindow
and pushes synthetic `SystemSnapshot`s through `_on_snapshot`, including the exact
changing-every-tick patterns (homing-dwell counter, appearing/disappearing carts,
50× identical snapshots) that caused the historical Qt widget-churn hard crashes. Run it
after any change to a panel's `update()` or to the homing step-button styling.

## The real system (ground-truth facts)
Source files live in `Magnamotion Project/` (L5X, ladder PDFs, tag CSVs) and the runtime
config in `mm_monitor/data/` (TrackFile.mmtrk, node_configuration.xml).

- **PLC:** 5069-L340ERS2/B **GuardLogix 5380** at **192.168.1.10**, program scope `Program:MagneMotion`.
- **HLC (MagneMotion Node Controller):** 192.168.1.200 (the PLC talks to it; the app talks to the PLC).
- **1 Node Controller** (`max_nc_id`=1), **6 paths** (`max_path_id`), **up to 64 vehicles** (`PLC_max_vehicle_ID`).
- HLC pushes vehicle status every 100 ms.

### Paths (node_configuration.xml)
1 Mold 1 Entry/Exit · 2 Mold 1 · 3 Cleanout · 4 Mold 2 · 5 Mold 2 Entry/Exit · 6 Process.
Main travel loop = paths 1→3→4→6; paths 2 & 4 are mold loops, path 6 the long process backstretch.

### Stations
30 process stations + Home (33) + Cleanout (34). Full map with per-path meter locations is in
`system_data.STATION_LOCATIONS` (from node_configuration.xml — the authoritative config that
matches the running ladder). NOTE: `Magnemotion_setup.xml` is a DIFFERENT/older config and is ignored.

### State values (CRITICAL — verified from init_constants in the L5X)
These are easy to get wrong; the values are non-obvious:
- **Node Controller** (`MMI_node_controller_status[i].state`): INIT=1, FAULTED=2, **OPERATIONAL=3**
- **Path** (`MMI_path_status[i].state`): INIT=0, STARTUP=1, **OPERATIONAL=2**, RESET=3, PROGRAMMING=4
- Station: IDLE=0, DWELL=1, PROCESSING=2, DEPART=4
- Vehicle mgr: IDLE=1, PLACE_ORDER=2, WAIT_FOR_ARRIVAL=3

### Key tags read each poll (see `plc_reader.poll()`)
- Scalars (program scope): `cold_start_service.step`, `Recovering_Pallets`, `hlc_link_status`,
  `nc_operational`, `Vehicles_Indentified`, `Pallets_In_System`, `MagneMotion_Ready`,
  `MagneMotion_Pallet_Blocked`, `Vehicles_at_Molds`, `Homing_Pallets`, `Destination_Mold1/2`,
  `CleanoutPallets`, `PalletsatCleanout`, `confirm_Pallet_cleanout`, `max_nc_id/path_id/vehicle_id`.
- Controller scope: `MMI_heartbeat`, `MM_Global_Velocity/Acc`,
  `MMI_vehicle_status[1..64]`, `MMI_vehicle_alarms[1..64]`, `MMI_path_status[1..8]`,
  `MMI_node_controller_status[1..8]`, `vehicle_mgr_array[..].{dest,arrived,state,order}`,
  `stations_array[1..34].{state,active_vehicle_id,occupied,process_complete,hold}`,
  `vehicles_in_path[0..9]`.
- Real fault bits (separate **Alarms** program): `Program:Alarms.MagneMotion_Vehicle_Fault`,
  `Program:Alarms.MagneMotion_Motor_Fault`.
- Per-motor faults: `MMI_path_ml_faults_status[path,motor]` (2-D, paths 1..6 × motors 1..13 per
  `max_motor_id`). Read on a **throttled 5 s cadence** (it's a large array that changes slowly);
  the result is cached between scans. Decoded in `system_data.decode_motor_fault()`:
  `Motor_Overall` bits (.0 Not_Operational, .1 In_Config, .2 In_Diag, .3 Suspended, .4 Stopped/FastStop,
  .7 Not_Responding — mapping from the `motor_alarm_mgr` ST routine) plus comm faults (OS scheduler /
  upstream / downstream) and Master/Driver board fault SINTs. A fault is "serious" if Not_Operational,
  Stopped, Not_Responding, or any comm/board fault; config/diag/suspended alone are "non-running" states.

## The two operator operations (the important ones)
The operator only commands two things; their progress is the headline indicator (top banner on
System Overview, `system_data.current_operation()`):
1. **HOME OUT (Cold Start):** `cold_start_service.step` runs 5→100. Progress = step position in the
   sequence. Steps & plain-English explanations in `COLD_START_STEPS` / `COLD_START_DETAIL`.
   Sequence: 10,15,16,17,18,20,25,30,50,55,60,70,80,90,100 → back to 5 (idle/running).
   Common hang: **step 17** waits for the NC to report OPERATIONAL (state 3).
2. **CLEAN PALLETS (Cleanout):** `CleanoutPallets` set → pallets sent to the cleanout section
   (path 3 backstretch). Progress = `vehicles_in_path[3] / Pallets_In_System`. `PalletsatCleanout`
   latches when done ("ready to remove").

### Step 25/30 (RESET) and 55/60 (STARTUP) — the slow part of homing
Step **20** sends a RESET to all paths and arms a **300 s (5-min) timeout** (`timer.PRE=300000`);
step **50** sends STARTUP with a 5 s timeout. Steps 25↔30 (and 55↔60) then loop, waiting for EVERY
path to report its command COMPLETE (`last_command_accepted_completion_status==0x80` AND
`last_command_accepted_count==command_count`). So step 25 "taking long" = waiting up to 5 minutes
for all path motors to finish RESET; if the timeout expires it retries from step 20.
`system_data.cold_start_progress()` surfaces this in the operation banner:
"Resetting paths: 4/6 RESET complete — 2:47 until retry" (reads `cold_start_service.timer.ACC/PRE`
+ `command_count` + per-path `MMI_path_command_status`).

## Alarms / homing-blocker analysis (`system_data.analyze_status`)
Returns (severity, title, detail). Flags: real Vehicle/Motor fault bits, HLC link down,
NC not operational (state≠3), jammed/alarmed pallets, pallet-blocked flag, path not operational
(state≠2), **per-motor faults** (serious → critical, non-running states → info), and a
**step-aware homing diagnosis** (dwell ≥ 15 s).

### Step-aware homing diagnosis (`system_data.homing_diagnosis`) — "why won't it home?"
The `cold_start_service` steps are pure *wait-gates* on tags that OTHER routines / the HLC
produce, so a homing hang is always traceable to a different subsystem. When a step dwells
≥ `HOMING_STUCK_SECS` (15 s) the app names the exact gate and who owns it:
- **step 17/18** → waits for every NC `state==3`; names the offline NC(s). (Node Controller / HLC)
- **step 20** → needs `hlc_link_status` TRUE (from `hlc_link_monitor`) **and** the path-command MSG
  service idle (`msg_service_path_cmd_step==10`); reports whichever is the actual blocker.
- **step 25/30** → every path's RESET must report `last_command_accepted_completion_status==0x80`
  (`MMI_CMD_COMPLETE`=128); names the incomplete path(s) and cross-references serious motor faults.
- **step 50/55/60** → same for the STARTUP command.
- **step 90/100** → vehicles not being discovered / vehicle-mgr not accepting orders.
New tags read to support this: `MMI_path_command_status[1..8]` (per-path completion) and
`msg_service_path_cmd_step`. NOTE: corrected the cold-start step labels — **step 18** is the real
NC-wait loop (the routine alternates 17↔18 while waiting); the old code had 17/18 mislabeled. Shown in the System Overview
"Alarms & Homing Blockers" list and as colored carts on the Live Track.

### Pallet "jam" vs "queue" (important nuance)
A vehicle's `Obstructed` bit just means "a unit is ahead of me" — **normal queuing** (mold dwell
is 30 s). So obstruction alone is shown as **"queued"** (benign, not a blocker). A real jam is only
flagged when obstructed continuously **>90 s** (`JAM_OBSTRUCT_SECS`, tracked via `obstructed_secs`
in the reader) or when the HLC sets `AlarmPresent`.

## Recording & playback (`recording.py`, `gui/record_bar.py`)
- While connected, **● Record** writes each snapshot to a `.mmrec` file (JSON-lines) in
  `%APPDATA%/MagneMotionMonitor/recordings/`.
- While disconnected, **📂 Load Recording** + transport (play/pause, scrub slider, 0.5×–8× speed)
  replays the snapshots through the exact same UI path. Live and playback are mutually exclusive.

## Tabs
System Overview (operation banner, stats, flags, clickable homing steps, alarms) · Live Track
(**real photo of the physical track** with carts placed by path+position, jammed=red —
falls back to the auto-generated .mmtrk schematic if the photo is missing) · Pallet Tracker ·
Motion/Speed · Stations · Paths & NCs (path/NC state, NC firmware, **per-motor / driver-board
faults**) · Raw Tags · Event Log.

### Real track photo (`track_photo.py`, replaces the schematic as the default view)
`mm_monitor/data/track_photo.png` is an actual photo of the physical S7000 track. Since a
photo has no coordinate system (unlike the schematic, which is mathematically derived from
TrackFile.mmtrk), station/cart positions on it are a **hand-calibrated, best-effort visual
alignment** — see the long comment at the top of `track_photo.py` for the full method:
1. Render the schematic and compare colors/shapes against the photo to identify which
   physical spur is which path — this step is ground truth (topology from real motor
   segments), not a guess. Confirmed mapping: **Path 6 (Process) = full top rail** (incl.
   both rounded end caps) · **Path 3 = long straight middle of the lower rail** · **Path 4
   (Mold 2) = LEFT drop spur** · **Path 2 (Mold 1) = RIGHT drop spur** · Path 1/5 = tiny
   connectors at the right/left junctions (Path 1 has no stations; Path 5 hosts Cleanout).
2. Measure the photo's actual pixel geometry (numpy thresholding of the rail vs. background,
   cross-checked with cropped close-ups) rather than eyeballing a downscaled preview.
3. Place waypoints in the same order the real vehicle travels each path (confirmed from the
   raw motor-segment list in `track_geometry.TRACK_MMTRK` — e.g. Path 6's first 2m head
   screen-LEFT before the curve, because the schematic's transform flips the X axis).
`PhotoTrackModel.point_at(path, pos_m)` maps a cart's real meter-position to a **fraction**
of distance along its hand-placed pixel polyline (not an absolute px/m conversion) — so it's
robust to the hand-placed waypoints not having perfectly uniform scale.
**Accuracy**: paths 6/2/4 (28 of 30 real stations — everything the operator actually watches)
are calibrated from measured pixels and land visually right on the rail. Paths 1/3/5 (hosting
only Home + Cleanout) use straight-line approximations between measured junction points —
good enough for "roughly where is this pallet," not survey-grade. If something looks off once
you can compare it against the real machine, nudge the waypoints in `PATH_WAYPOINTS_PX`.
**Automatic fallback**: if `track_photo.png` is missing or fails to decode, `TrackCanvas`
falls back to the schematic entirely — nothing else changes, unaffected by which is active.

### Cart motion smoothing (`gui/track_panel.py`)
Raw PLC samples arrive in discrete jumps (~0.75s live poll interval, or once per
recorded frame in playback) — drawing them directly made carts visibly teleport.
Two independent smoothing paths, both in `track_panel.py`:
- **Live — `CartAnimator`**: dead-reckons each cart forward from its last known
  (position, velocity, timestamp) using elapsed wall-clock time — "assume it kept
  moving the way we last saw it" — driven by a 30fps `QTimer` inside `TrackCanvas`.
  If a new poll disagrees with the prediction (cart stopped, changed speed, a slow
  poll), the display blends to the truth over 0.15s instead of snapping.
  Extrapolation is capped at 3s so a cart freezes rather than drifts forever if
  polling stalls. A path change (junction transition) has no continuous geometry
  to smooth across, so the new path/position is adopted immediately.
- **Playback — `interpolate_carts()`**: both the current and next recorded frame
  are already on disk, so positions are interpolated exactly between them (no
  prediction needed) — driven every 50ms tick by `MainWindow._update_track_interpolated`,
  independent of how far apart the recorded frames actually are.
- `TrackCanvas` exposes `feed_live(carts)` (animator path) and `set_carts_exact(carts)`
  (direct — used by playback and any discrete jump like seek/skip/pause).
  `TrackPanel.feed_live_snapshot(snap)` vs `TrackPanel.update(snap)` /
  `update_playback(cur, next, frac)` are the corresponding entry points;
  `MainWindow._on_snapshot` branches on `from_playback` to pick the right one.

### Carts held in place during Homing / Cleaning (`CartPresenceGuard`)
`MMI_vehicle_status` is written entirely by the HLC — the PLC ladder never zeroes it.
During cold-start RESET/STARTUP (steps 20-60) and during cleanout, the HLC genuinely
stops reporting a valid `Path_ID` for pallets it hasn't re-localized yet (it only
resumes at steps 80-100, "waiting for HLC to push vehicle locations" / "scanning
MMI_vehicle_status"). Drawing that literally made physically-present pallets vanish
from the Live Track for the duration of the operation. `CartPresenceGuard`
(`gui/track_panel.py`) fixes this: while `system_data.current_operation(snap)["active"]`
is true (Homing, Cleaning, or Recovering — the same operator-commanded-operation
notion already used for the progress banner), a cart missing from the current poll is
held at its last confirmed (path, position) with velocity frozen to 0 and `_Cart.held
= True`, drawn muted with a dashed outline and an "assumed position" label instead of
its normal state/speed label. Outside an active operation a missing cart is trusted at
face value and dropped immediately (it really left). Wired into both
`feed_live_snapshot` (live) and `update_playback` (playback's continuous forward
ticking, which is just as sequential as live polling) — but NOT the bare `update()`
used by a discrete seek/skip, which should show exactly what was recorded at that
instant. `held` propagates through `CartAnimator`'s dead-reckoning state too (a held
cart's frozen position naturally survives `tick()`). `TrackPanel.reset_smoothing()`
clears all held/animated state — called on disconnect, on loading a new recording, and
on every seek/skip (a jump breaks the "sequential polls" assumption this guard relies on).

## Architecture
```
main.py                      entry; installs crash handler then builds MainWindow
mm_monitor/
  plc_reader.py              PLCReader + SystemSnapshot (one poll = one snapshot)
  system_data.py             ALL system constants, state maps, station/track data, analysis funcs
  track_geometry.py          parses TrackFile.mmtrk → 2-D TrackModel; auto-solves curve radius
  recording.py               Recorder + Recording (record/playback)
  crash_handler.py           global crash capture (popup + crash_logs + faulthandler)
  data/                      TrackFile.mmtrk, node_configuration.xml (bundled)
  gui/
    main_window.py           orchestrator: poll timer, playback timer, routes snapshot to panels
    connection_bar.py, record_bar.py
    system_panel.py, pallet_panel.py, station_panel.py, path_nc_panel.py,
    motion_panel.py, track_panel.py, raw_panel.py, log_panel.py
    theme.py
```
Data flow: poll thread → `SystemSnapshot` → Qt signal → `MainWindow._on_snapshot` → each
`panel.update(snap)` (each wrapped in `_safe()` so one bad panel logs instead of crashing).

## Crash safety (hard-won — this machine hard-crashes on Qt widget churn)
Hard C++/Qt crashes show NO Python popup (just the app closing). Causes found & fixed:
- **Per-poll widget creation/destruction** is the trigger. Fixed: alarms rows rebuild only when the
  alarm set changes; Motion speed bars are text (not per-poll `QProgressBar` via `setCellWidget`);
  homing step buttons re-style only on step change. All table updates wrap `setUpdatesEnabled(False/True)`
  and disable sorting during rebuild.
- `crash_handler` installs `sys.excepthook` + `threading.excepthook` + Qt message handler +
  **`faulthandler`** (native stack on segfault → `%APPDATA%/MagneMotionMonitor/crash_logs/faulthandler.log`).
  If a silent crash recurs, that file is the evidence to grab.

## Fix history (most recent first)
- **Path status overlay tried and removed** — briefly drew all 6 paths as a translucent line
  colored by live `MMI_path_status` (the "draw in a spur, pull its condition from the PLC"
  request), then removed per user feedback ("looks like crap") — Live Track is back to just
  the photo + station dots + cart markers, no colored path lines. App icon (MagneMotion logo,
  `assets/app_icon.ico`) is unrelated and stays in place. Test suite back to 123.
- **App icon** — MagneMotion company logo is the .exe file icon and running window/taskbar
  icon, via `assets/app_icon.ico`.
- **Fixed mold-spur cart positioning ("stops before the turn")** — replaced the coarse
  ~9-point hand-placed calibration for Path 2/Path 4 (the mold spurs) with a dense
  numpy column-scan trace (both legs + the U-turn bottom, every ~2-4px). The coarse
  version compressed some of the real curve into too few pixels relative to its real
  length, so a cart's fractional position landed short there, looking like it paused
  before entering the spur. Verified by walking a simulated cart in 0.5m steps around
  the full spur and confirming even pixel spacing throughout, including the turn.
- **Carts held in place during Homing/Cleaning** — `CartPresenceGuard` stops pallets from
  vanishing off the Live Track when the HLC temporarily drops `Path_ID` during cold-start
  RESET/STARTUP or cleanout (real hardware behavior, not a bug); shows them at their last
  known position (dashed, "assumed position") until real telemetry returns or the operation
  ends. Test suite 123 (+14), verified under a real Qt event loop simulating a full homing
  sequence with telemetry dropout.
- **Real track photo replaces the schematic** — Live Track now draws `mm_monitor/data/track_photo.png`
  (an actual photo of the physical S7000 track) as the background, with stations/carts placed
  via a hand-calibrated `PhotoTrackModel` (see track_photo.py). Falls back to the schematic
  automatically if the photo is missing/fails to load. Test suite 109 (+11).
- **Smooth cart motion** — replaced the direct "snap to latest sample" cart placement with
  live dead-reckoning (`CartAnimator`, extrapolates from last known velocity, 30fps) and
  exact frame-to-frame interpolation during playback (`interpolate_carts`, 50ms tick) — no
  more clunky per-poll/per-frame teleporting. Test suite 98 (+16).
- **WEEK.DAY.BUILD versioning** — switched to date-based `WEEK.DAY.BUILD` versions written by
  `release.py` into `mm_monitor/version.py`; shown in the window title + connection bar. Added
  step 25/30 & 55/60 RESET/STARTUP **progress** (paths-done + 5-min timeout countdown) in the
  operation banner. Test suite 82.
- **v0.7.1** — Step-aware homing diagnosis: when a cold-start step stalls, `analyze_status` now
  names the exact wait-gate and the OTHER routine/subsystem responsible (NC operational, HLC link,
  path-command MSG service, per-path RESET/STARTUP completion, vehicle discovery). Reads two new
  tags for this (`MMI_path_command_status`, `msg_service_path_cmd_step`). Corrected the cold-start
  step 15/16/17/18 descriptions to match the actual ladder (step 18 = NC-wait loop). Built the
  distributable `MagneMotionMonitor.exe` (PyInstaller spec). Test suite now 77.
- **v0.7.0** — Per-motor fault detection: reads `MMI_path_ml_faults_status` (throttled 5 s) and
  surfaces motor/comm/driver-board faults in `analyze_status` and a new section on the Paths & NCs
  tab. Layout overhaul: Overview tab = slim stat bar above the Live Track with a clickable
  homing/cleaning progress bar; left-side nav (plain horizontal buttons); System moved to its own
  tab. Whole UI fits with no horizontal scrollbar (min window 960×700). Connect bar simplified to a
  single Connect button (IP is fixed at 192.168.1.10). Crash dialog re-themed light. Removed dead
  code (`config.py`, `settings_dialog.py`, `path_panel.py`, `mover_panel.py`, orphaned color tables).
  Added a headless `tests/` suite (pytest, 69 tests) — see the Tests section.
- **v0.6.3** — UI polish pass: light theme throughout (no more dark background); carts on track
  are now squares, not circles; jammed carts show "! JAMMED" in red (was "⚠ STALLED"); queued
  carts show "queued" with no exclamation; playback bar adds −5m/−1m/−30s/+30s/+1m/+5m skip
  buttons; minimize button top-right with 30s/1m/10m/30m timer auto-restores the window.
- **v0.6.2** — Fixed persistent crash when connected: QTimer spawned a new thread every 750 ms;
  if reads took >750 ms threads piled up until crash. Fix: single persistent `_poll_loop` thread.
  Also switched to active-only reads (alarms + mgr only for carts with Path_ID ≠ 0).
- **v0.6.1** — Fixed the ~30 s hard crash. Root cause: the "Homing stuck at step N for **Xs**"
  alarm title changes every second, so the alarms panel (which rebuilt QFrame rows when the alarm
  text changed) destroyed/recreated widgets every poll → Qt C++ widget-churn crash. Fix: alarms now
  use a fixed pool of 16 reusable rows updated IN PLACE. Also converted every always-updating table
  (pallet/station/paths-NCs/motion/raw) to in-place cell updates via `gui/_tableutil.set_cell`, and
  disabled live sorting on the pallet table (sortable + repopulated = the documented crash pattern).
- **v0.6.0** — Fixed false "node offline" fault: NC OPERATIONAL is state **3** (was assumed 1);
  PATH OPERATIONAL is **2** (was assumed 4). Added real Vehicle/Motor fault bits from the Alarms
  program. Added prominent operation banner (home-out & cleanout progress). Added cleanout progress.
  Added record/playback. Added homing step 70.
- **v0.5.1** — Fixed false "JAMMED": obstruction = queuing; only >90 s stall or AlarmPresent is a jam.
  Fixed widget-churn crash (alarms/motion/step styling) + malformed stylesheet; added faulthandler.
- **v0.5.0** — Alarm tags (`MMI_vehicle_alarms` etc.), homing-blocker analysis, clickable step
  explanations, jammed carts on track. Read `max_nc_id`/`max_path_id` (system has only 1 NC).
- **v0.4.0** — Real geometric Live Track from TrackFile.mmtrk (auto-solved curve radius for gap-free
  junctions); authoritative path names + station meter-locations from node_configuration.xml.
- **v0.3.0** — Homing % meter; Motion/Speed tab (no per-cart power telemetry exists — speed &
  following-error instead); global crash handler with copyable popup.
- Initial — System Overview/Pallet/Station/Paths/Raw/Log tabs reading the MMI_* tag interface.

## Known limitations / TODO
- Curve radius (track geometry) is auto-solved for loop closure; carts on curves are approximate,
  carts on straights (where stations are) are accurate.
- No per-cart electrical power / motor current — the HLC does not publish it.
- `MMI_motor_alarm[100]` (the flat, ladder-derived per-motor array) is not read — the app reads
  the authoritative 2-D source `MMI_path_ml_faults_status` directly instead.
