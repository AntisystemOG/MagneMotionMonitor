"""System-specific constants for the S7000 Module Assembly Boxing MagneMotion system.

All tag names, UDT structures, array sizes, and state values derived directly from:
  - S7000_Module_Assembly_Boxing_patched_MagneMotion_Tags.CSV
  - S7000_Module_Assembly_Boxing_patched_Controller_Tags.CSV
  - MagneMotion_Program.L5X
"""

# ── Path names (path_id → name) — from node_configuration.xml ────────────────
PATH_NAMES: dict[int, str] = {
    1: "Mold 1 Entry/Exit",
    2: "Mold 1",
    3: "Cleanout",
    4: "Mold 2",
    5: "Mold 2 Entry/Exit",
    6: "Process",
}


def path_name(pid: int) -> str:
    return PATH_NAMES.get(pid, f"Path {pid}" if pid else "—")


# ── Station map (station_id → (path_id, location_m, name)) ───────────────────
# Authoritative source: node_configuration.xml (matches the running PLC ladder).
# location_m is meters from the start of that station's path.
STATION_LOCATIONS: dict[int, tuple[int, float, str]] = {
    # Path 2 — Mold 1
    1:  (2, 2.65,  "Mold 1 Pre-Load"),
    2:  (2, 2.75,  "Mold 1 Pre-Load"),
    3:  (2, 3.00,  "Mold 1 Pre-Load"),
    4:  (2, 3.00,  "Mold 1 Load"),
    5:  (2, 3.248, "Mold 1 Load"),
    6:  (2, 4.50,  "Mold 1 Cooling"),
    # Path 4 — Mold 2
    7:  (4, 2.65,  "Mold 2 Pre-Load"),
    8:  (4, 2.75,  "Mold 2 Pre-Load"),
    9:  (4, 3.00,  "Mold 2 Pre-Load"),
    10: (4, 3.00,  "Mold 2 Load"),
    11: (4, 3.248, "Mold 2 Load"),
    12: (4, 4.25,  "Mold 2 Cooling"),
    # Path 6 — Process
    13: (6, 5.50,   "Pre-Load Roller"),
    14: (6, 5.893,  "Load Roller"),
    15: (6, 6.50,   "Pre-Load Pin"),
    16: (6, 6.8398, "Load Pin"),
    17: (6, 7.55,   "Pre-Insp Pin"),
    18: (6, 7.7075, "Insp Pin 1"),
    19: (6, 7.759,  "Insp Pin 2"),
    20: (6, 7.81,   "Insp Pin 3"),
    21: (6, 7.8483, "Roller Test 1"),
    22: (6, 8.088,  "Roller Test 2"),
    23: (6, 8.3283, "Roller Test 3"),
    24: (6, 8.64,   "Roller Test 4"),
    25: (6, 8.933,  "Roller Test 5"),
    26: (6, 9.1383, "Roller Test 6"),
    27: (6, 9.25,   "Pre-Offload"),
    28: (6, 9.60,   "Pre-Offload"),
    29: (6, 9.9438, "Offload"),
    30: (6, 10.10,  "Mold Direction Check"),
    # Path 3 / Path 5 — Home & Cleanout
    33: (3, 4.50,  "HOME / Cold Start"),
    34: (5, 0.15,  "Cleanout"),
}

# station_id → display name
STATION_NAMES: dict[int, str] = {sid: v[2] for sid, v in STATION_LOCATIONS.items()}


def station_name(idx: int) -> str:
    return STATION_NAMES.get(idx, f"Station {idx}" if idx else "—")


def station_location(idx: int) -> tuple[int, float] | None:
    """Return (path_id, location_m) for a station, or None."""
    v = STATION_LOCATIONS.get(idx)
    return (v[0], v[1]) if v else None


# ── Cold-start (homing) step → (phase, description, color) ─────────────────
# From cold_start_service routine rung comments in MagneMotion_Program.L5X
COLD_START_STEPS: dict[int, tuple[str, str, str]] = {
    5:   ("IDLE",      "System running — pallets active",                         "#27ae60"),
    10:  ("INIT",      "Initializing constants & station table",                  "#2980b9"),
    15:  ("INIT",      "Clearing position-order active flags",                    "#2980b9"),
    16:  ("INIT",      "Clearing the vehicle-manager array",                      "#2980b9"),
    17:  ("WAIT NC",   "Checking Node Controllers",                               "#e67e22"),
    18:  ("WAIT NC",   "Waiting for all Node Controllers to go OPERATIONAL",      "#e67e22"),
    20:  ("RESET",     "Sending RESET command to all paths",                      "#8e44ad"),
    25:  ("RESET",     "Waiting for path reset to be accepted",                   "#8e44ad"),
    30:  ("RESET",     "Verifying all paths completed reset",                     "#8e44ad"),
    50:  ("STARTUP",   "Sending STARTUP command to all paths",                    "#e67e22"),
    55:  ("STARTUP",   "Waiting for path startup to be accepted",                 "#e67e22"),
    60:  ("STARTUP",   "Verifying all paths completed startup",                   "#e67e22"),
    70:  ("STARTUP",   "Startup complete — preparing to discover vehicles",       "#f39c12"),
    80:  ("DISCOVER",  "Waiting 1 s for HLC to push vehicle locations",           "#f39c12"),
    90:  ("DISCOVER",  "Scanning MMI_vehicle_status for vehicles on track",       "#f39c12"),
    100: ("ORDER",     "Ordering detected vehicles to Home Station",              "#27ae60"),
}

# Plain-English explanation of each cold-start/homing step (shown on click).
# Derived from the cold_start_service rung comments in MagneMotion_Program.L5X.
COLD_START_DETAIL: dict[int, str] = {
    5:   "System running normally. The cold-start routine is idle and homing is complete — "
         "pallets are being managed for production. This is where you want to end up after homing.",
    10:  "Initializing. Loading constant values and building the station table, clearing the "
         "command timeout counters, and preparing the position-order list. First step of a cold start.",
    15:  "Clearing the 'active' flag on every position-order entry (the move-command list the PLC "
         "sends to the HLC) so no stale move orders are left over from before.",
    16:  "Clearing the vehicle-manager array so only freshly-discovered vehicles get tracked. "
         "This prevents stale pallet data from a previous run.",
    17:  "Initializing the Node-Controller check, then advancing to the wait loop. Transient — the "
         "routine alternates between steps 17 and 18 while waiting for the NCs.",
    18:  "Waiting for ALL Node Controllers to report OPERATIONAL (state 3) before resetting the "
         "track. If homing hangs around step 17/18, a Node Controller is not coming online — check "
         "NC power, the NCHost/configuration file, and motor communications.",
    20:  "Sending a RESET command to all paths (path 0 = all paths). This returns every motor "
         "to a known starting state before startup.",
    25:  "Waiting for the RESET command to be accepted by the HLC. Retries automatically every "
         "~10 seconds if there is a network interruption.",
    30:  "Verifying every path finished its RESET by checking each path's last-completed command. "
         "Advances once all paths report reset complete. If stuck, a path/motor is not resetting.",
    50:  "Sending a STARTUP command to all paths. This energizes the motors and brings the track online.",
    55:  "Waiting for the STARTUP command to be accepted by the HLC.",
    60:  "Verifying every path finished STARTUP. Advances once all paths are running. If stuck here, "
         "a path or motor failed to start (check path/motor faults).",
    70:  "Startup is complete. Brief transition step before the controller starts discovering which "
         "pallets are on the track.",
    80:  "Waiting ~1 second for the HLC to push the latest vehicle locations into MMI_vehicle_status "
         "so the PLC can see which pallets are on the track.",
    90:  "Scanning MMI_vehicle_status for real vehicles (Path_ID non-zero) to count how many pallets "
         "were discovered on the track.",
    100: "Ordering each discovered pallet to its Home station to get the line moving. When finished, "
         "the routine returns to step 5 (running).",
}


def cold_start_detail(step: int) -> str:
    return COLD_START_DETAIL.get(step, f"Step {step}: no description available.")


# Completion code a path reports when a RESET/STARTUP command finished OK
# (init_constants: MOV(128, MMI_CMD_COMPLETE)). Steps 30 & 60 wait for this on every path.
MMI_CMD_COMPLETE = 128

# Dwell (seconds on one cold-start step) before the app calls homing "stuck".
HOMING_STUCK_SECS = 15.0

HOMING_STEP_ORDER = [5, 10, 15, 16, 17, 18, 20, 25, 30, 50, 55, 60, 70, 80, 90, 100]

# The homing progression in execution order (excludes the idle/done step 5).
HOMING_SEQUENCE = [10, 15, 16, 17, 18, 20, 25, 30, 50, 55, 60, 70, 80, 90, 100]


def cold_start_info(step: int) -> tuple[str, str, str]:
    if step in COLD_START_STEPS:
        return COLD_START_STEPS[step]
    return "?", f"Unknown step {step}", "#888888"


def homing_active(step: int) -> bool:
    return step != 5


def homing_percent(step: int) -> int:
    """0–100 % completion of the cold-start/homing sequence.
    Step 5 (idle) returns 100 — the panel renders it as 'complete / running'."""
    if step == 5:
        return 100
    if step in HOMING_SEQUENCE:
        return int(round((HOMING_SEQUENCE.index(step) + 1) / len(HOMING_SEQUENCE) * 100))
    # unknown intermediate step → nearest-lower known step's progress
    lower = [s for s in HOMING_SEQUENCE if s <= step]
    if lower:
        return int(round((HOMING_SEQUENCE.index(lower[-1]) + 1) / len(HOMING_SEQUENCE) * 100))
    return 0


def _fmt_mmss(secs: float) -> str:
    secs = max(0, int(secs))
    return f"{secs // 60}:{secs % 60:02d}"


def cold_start_progress(snap) -> dict | None:
    """During the path RESET (steps 20/25/30) and STARTUP (50/55/60) waits, report
    how many paths have finished and how long until the command times out and retries.

    A path is "done" only when its last *accepted* command count matches the cold-start
    command count AND it reports COMPLETE (0x80) — the same test the ladder uses, so a
    stale COMPLETE from a previous command isn't miscounted. Returns
    {label, done, total, secs_left, detail} or None when not in a path-command wait."""
    step = snap.cold_start_step
    if step in (20, 25, 30):
        label, cmd = "Resetting paths", "RESET"
    elif step in (50, 55, 60):
        label, cmd = "Starting paths", "STARTUP"
    else:
        return None

    total = snap.max_path or MAX_PATHS
    counts = getattr(snap, "path_cmd_count", None) or []
    stats  = getattr(snap, "path_cmd_status", None) or []
    cs_cmd = getattr(snap, "cs_cmd_count", None)
    done = 0
    for p in range(1, total + 1):
        cnt = counts[p] if p < len(counts) else None
        st  = stats[p]  if p < len(stats)  else None
        if (st is not None and int(st) == MMI_CMD_COMPLETE
                and (cs_cmd is None or cnt is None or int(cnt) == int(cs_cmd))):
            done += 1

    pre = getattr(snap, "cs_timer_pre", 0) or 0
    acc = getattr(snap, "cs_timer_acc", 0) or 0
    secs_left = max(0.0, (pre - acc) / 1000.0) if pre else 0.0
    detail = f"{label}: {done}/{total} {cmd} complete"
    if pre:
        detail += f" — {_fmt_mmss(secs_left)} until retry"
    return {"label": label, "done": done, "total": total,
            "secs_left": secs_left, "detail": detail}


def current_operation(snap) -> dict:
    """Identify which operator command is running and its progress.
    The two operator-commanded operations are HOME OUT (cold start) and CLEAN PALLETS.
    Returns: {name, pct, detail, color, active, icon}."""
    step = snap.cold_start_step
    pallets = max(snap.pallets_in_system, 0)
    vip3 = snap.vehicles_in_path[3] if len(snap.vehicles_in_path) > 3 else 0

    # 1) HOME OUT — cold start state machine running
    if step != 5:
        _, desc, color = cold_start_info(step)
        detail = f"Step {step}: {desc}"
        prog = cold_start_progress(snap)
        if prog:
            detail += f"  ·  {prog['detail']}"
        return {"name": "HOMING — Cold Start", "pct": homing_percent(step),
                "detail": detail, "color": color, "active": True, "icon": "⌂"}

    # 2) CLEAN PALLETS — sending pallets to the cleanout section
    if snap.pallets_at_cleanout:
        return {"name": "PALLETS AT CLEANOUT", "pct": 100,
                "detail": "All pallets staged at the cleanout section — ready to remove.",
                "color": "#27ae60", "active": True, "icon": "⚒"}
    if snap.cleanout:
        pct = int(min(vip3 / pallets, 1.0) * 100) if pallets > 0 else 0
        return {"name": "CLEANING PALLETS", "pct": pct,
                "detail": f"{vip3} of {pallets} pallets have reached the cleanout section.",
                "color": "#f39c12", "active": True, "icon": "⚒"}

    # 3) RECOVERING — pallets moving back to their stations after a home
    if snap.recovering:
        homed = snap.homing_count
        pct = int(min(homed / pallets, 1.0) * 100) if pallets > 0 else 0
        return {"name": "RECOVERING PALLETS", "pct": pct,
                "detail": f"Moving pallets to their stations ({homed}/{pallets}).",
                "color": "#2980b9", "active": True, "icon": "⟳"}

    # 4) idle / running
    if pallets > 0:
        return {"name": "RUNNING", "pct": 100, "detail": "System running normally — production.",
                "color": "#27ae60", "active": False, "icon": "▶"}
    return {"name": "IDLE", "pct": 0, "detail": "No pallets in system.",
            "color": "#888888", "active": False, "icon": "●"}


# ── Node Controller state values ────────────────────────────────────────────
# From init_constants: MMI_NODE_DEVICE_STATUS_INIT=1, FAULTED=2, OPERATIONAL=3.
NC_OPERATIONAL = 3
NC_STATES: dict[int, tuple[str, str]] = {
    1: ("INIT",        "#e67e22"),
    2: ("FAULTED",     "#e74c3c"),
    3: ("OPERATIONAL", "#27ae60"),
}

# ── Path state values ───────────────────────────────────────────────────────
# From init_constants: PATH_STATE_INIT=0, STARTUP=1, OPERATIONAL=2, RESET=3, PROGRAMMING=4.
PATH_OPERATIONAL = 2
PATH_STATES: dict[int, tuple[str, str]] = {
    0: ("INIT",        "#888888"),
    1: ("STARTUP",     "#e67e22"),
    2: ("OPERATIONAL", "#27ae60"),
    3: ("RESET",       "#8e44ad"),
    4: ("PROGRAMMING", "#2980b9"),
}

# ── Vehicle manager state values (from init_constants: WAIT_FOR_ARRIVAL=3) ──
VEHICLE_MGR_STATES: dict[int, str] = {
    1: "IDLE",
    2: "PLACE ORDER",
    3: "WAIT ARRIVAL",
}

# ── Station state values (from init_constants: DEPART=4) ────────────────────
STATION_STATES: dict[int, tuple[str, str]] = {
    0: ("IDLE",       "#27ae60"),
    1: ("DWELL",      "#f39c12"),
    2: ("PROCESSING", "#8e44ad"),
    4: ("DEPART",     "#2980b9"),
}

# ── Array bounds ─────────────────────────────────────────────────────────────
# From tag declarations in Controller_Tags.CSV
MAX_VEHICLES = 64   # MMI_vehicle_status[65], indices 1-64 are valid
MAX_PATHS    = 8    # MMI_path_status[9], indices 1-8
MAX_NC       = 8    # MMI_node_controller_status[9], indices 1-8
MAX_STATIONS = 35   # stations_array[40], indices 0-34
MAX_MOTOR    = 13   # motors per path (init_constants: max_motor_id = 13)

# ── Controller-scope tag names ───────────────────────────────────────────────
# Tags with no program prefix — live in the controller scope
T_HEARTBEAT     = "MMI_heartbeat"
T_VEHICLE_ST    = "MMI_vehicle_status"       # [65]  udt_MMI_vehicle_status
T_PATH_ST       = "MMI_path_status"          # [9]   udt_MMI_path_status
T_NC_ST         = "MMI_node_controller_status"  # [9]  udt_MMI_node_controller_status
T_EXT_VEH_ST    = "MMI_extended_vehicle_status" # [65]
T_VEH_MGR       = "vehicle_mgr_array"        # [65]  udt_vehicle_mgr_array_entry
T_GLOBAL_VEL    = "MM_Global_Velocity"
T_GLOBAL_ACC    = "MM_Global_Acc"
T_VEHICLE_ALARMS = "MMI_vehicle_alarms"      # [65]  udt_MMI_vehicle_alarm (bits)
T_PATH_CMD_ST    = "MMI_path_command_status" # [9]   udt_MMI_path_command_status
T_PATH_ML_FAULTS = "MMI_path_ml_faults_status"  # [9,21] udt_MMI_ml_faults (per-motor)

# ── Program-scope tag names (MagneMotion program) ────────────────────────────
_P = "Program:MagneMotion"
PT_COLD_STEP    = f"{_P}.cold_start_service.step"
PT_RECOVERING   = f"{_P}.Recovering_Pallets"
PT_HLC_LINK     = f"{_P}.hlc_link_status"
PT_NC_OPER      = f"{_P}.nc_operational"
PT_VEH_ID       = f"{_P}.Vehicles_Indentified"
PT_PALLETS_SYS  = f"{_P}.Pallets_In_System"
PT_MM_READY     = f"{_P}.MagneMotion_Ready"
PT_BLOCKED      = f"{_P}.MagneMotion_Pallet_Blocked"
PT_VEH_MOLDS    = f"{_P}.Vehicles_at_Molds"
PT_STATIONS     = f"{_P}.stations_array"     # [40]
PT_VEH_IN_PATH  = f"{_P}.vehicles_in_path"  # [10]
PT_MAX_NC       = f"{_P}.max_nc_id"
PT_MAX_VEH      = f"{_P}.max_vehicle_id"
PT_MAX_ST       = f"{_P}.max_station_id"
PT_MAX_PATH     = f"{_P}.max_path_id"
PT_MAX_MOTOR    = f"{_P}.max_motor_id"
PT_HOMING_CNT   = f"{_P}.Homing_Pallets"
PT_DEST_MOLD1   = f"{_P}.Destination_Mold1"
PT_DEST_MOLD2   = f"{_P}.Destination_Mold2"
PT_CLEANOUT     = f"{_P}.CleanoutPallets"
PT_MODULES_AUTO = f"{_P}.Modules_In_Automation"
PT_CMD_COUNT    = f"{_P}.master_command_count"
PT_PALLETS_AT_CLEANOUT = f"{_P}.PalletsatCleanout"
PT_CONFIRM_CLEANOUT    = f"{_P}.confirm_Pallet_cleanout"
# Path-command message-service step. Steps 20/50 can only send RESET/STARTUP when
# this is 10 (idle). If it's stuck elsewhere, the MSG service is mid-command.
PT_MSG_PATH_CMD_STEP   = f"{_P}.msg_service_path_cmd_step"
# Cold-start command count + the RESET/STARTUP timeout timer (PRE=300 s for RESET,
# 5 s for STARTUP). Lets us show "paths done / total" and the countdown to retry.
PT_CS_CMD_COUNT        = f"{_P}.cold_start_service.command_count"
PT_CS_TIMER_ACC        = f"{_P}.cold_start_service.timer.ACC"
PT_CS_TIMER_PRE        = f"{_P}.cold_start_service.timer.PRE"

# Real MagneMotion fault bits live in the separate "Alarms" program.
AL_VEHICLE_FAULT = "Program:Alarms.MagneMotion_Vehicle_Fault"
AL_MOTOR_FAULT   = "Program:Alarms.MagneMotion_Motor_Fault"

# ── udt_MMI_vehicle_status members (from L5X DataType definition) ────────────
# Path_ID (INT)          — path vehicle is on; 0 = not tracked by HLC
# Dest_Path_ID (INT)     — destination path ID
# Position (REAL)        — position along current path (meters)
# Commanded_Position (REAL)
# Velocity (REAL)        — current velocity (m/s)
# Dest_Station_ID (INT)  — current destination station (0 = none)
# Command (SINT, hex)    — current HLC command
# Flags (SINT, binary)   — status flags

# ── udt_station_entry members (from L5X DataType definition) ─────────────────
# state (INT)            — station state (see STATION_STATES)
# station_hold_flag (BIT)
# timer (TIMER)
# dwell_period (INT)
# active_vehicle_id (INT) — vehicle ID currently at this station (0 = empty)
# path_id (INT)
# position (REAL)
# next_station_id (INT)
# velocity / acceleration / direction
# occupied (BIT)
# process_complete (BIT)

# ── Default HLC IP (from MSG ConnectionPath in L5X) ─────────────────────────
HLC_IP     = "192.168.1.200"   # MagneMotion High-Level Controller (Node Controller)
DEFAULT_IP = "192.168.1.10"    # GuardLogix 5380 (5069-L340ERS2/B)

# Version is WEEK.DAY.BUILD, written by release.py into version.py. Fall back to
# "dev" when running from source without a generated version file.
try:
    from .version import VERSION as APP_VERSION
except Exception:
    APP_VERSION = "dev"

# Propulsion power relay EDM feedback (safety). Best-effort read — the closest
# thing to a "power" signal published to the PLC. From I/O comment in Controller_Tags.CSV.
T_PROP_POWER = "I10_420_3[4]"


# ── Vehicle alarm decoding (udt_MMI_vehicle_alarm bits) ─────────────────────
# Bit layout from the L5X DataType definition:
#   bit0 VehicleSignal · bit1 Obstructed · bit2 Hindered · bit3 Suspect · bit4 AlarmPresent
def decode_vehicle_alarm(raw) -> dict:
    """Accepts either a UDT dict (pycomm3 expands the bit members) or a raw int."""
    if isinstance(raw, dict):
        return {
            "signal":    bool(raw.get("VehicleSignal", False)),
            "obstructed": bool(raw.get("Obstructed", False)),
            "hindered":   bool(raw.get("Hindered", False)),
            "suspect":    bool(raw.get("Suspect", False)),
            "alarm":      bool(raw.get("AlarmPresent", False)),
        }
    if isinstance(raw, int):
        return {
            "signal":     bool(raw & 0x01),
            "obstructed": bool(raw & 0x02),
            "hindered":   bool(raw & 0x04),
            "suspect":    bool(raw & 0x08),
            "alarm":      bool(raw & 0x10),
        }
    return {"signal": False, "obstructed": False, "hindered": False,
            "suspect": False, "alarm": False}


# ── Motor / driver-board fault decoding (udt_MMI_ml_faults) ─────────────────
# Source tag: MMI_path_ml_faults_status[path, motor]. Each element holds several
# SINT bitfields. Motor_Overall bit layout is taken from the motor_alarm_mgr ST
# routine in the L5X (it maps these exact bits to MMI_motor_alarm):
#   .0 Not_Operational · .1 In_Config_Mode · .2 In_Diag_Mode · .3 Suspended
#   .4 Stopped (FastStop) · .7 Not_Responding
_MOTOR_OVERALL_BITS = [
    (0, "Not Operational"),
    (1, "In Config Mode"),
    (2, "In Diag Mode"),
    (3, "Suspended"),
    (4, "Stopped (FastStop)"),
    (7, "Not Responding"),
]
# Motor_Overall bits that mean a genuine fault (vs. a transient startup state).
_MOTOR_SERIOUS_MASK = (1 << 0) | (1 << 4) | (1 << 7)   # Not_Operational, Stopped, Not_Responding


def _as_int(v) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def decode_motor_fault(elem: dict | None) -> dict | None:
    """Decode one MMI_path_ml_faults_status[path,motor] element.

    Returns None when the motor is clean, otherwise a dict:
      {motor_states:[...], comm:[...], boards:[...], serious:bool}
    `serious` is True for a real fault (not just a config/diag/suspended state)."""
    if not isinstance(elem, dict):
        return None
    overall = _as_int(elem.get("Motor_Overall"))
    motor_states = [label for bit, label in _MOTOR_OVERALL_BITS if overall & (1 << bit)]

    comm = []
    if _as_int(elem.get("OS_Scheduler")):    comm.append("OS scheduler")
    if _as_int(elem.get("Upstream_Comm")):   comm.append("upstream comm")
    if _as_int(elem.get("Downstream_Comm")): comm.append("downstream comm")

    boards = []
    if _as_int(elem.get("Master_Board_Faults_A")) or _as_int(elem.get("Master_Board_Faults_B")):
        boards.append("master board")
    drv = [n for n in range(1, 9) if _as_int(elem.get(f"Driver_Board_{n}_Faults"))]
    if drv:
        boards.append("driver board " + ",".join(str(n) for n in drv))

    if not (motor_states or comm or boards):
        return None
    serious = bool((overall & _MOTOR_SERIOUS_MASK) or comm or boards)
    return {"motor_states": motor_states, "comm": comm, "boards": boards, "serious": serious}


def motor_fault_str(f: dict) -> str:
    """One-line human summary of a decoded motor fault (with its path/motor)."""
    parts = []
    if f.get("motor_states"):
        parts.append(", ".join(f["motor_states"]))
    if f.get("comm"):
        parts.append("comm: " + ", ".join(f["comm"]))
    if f.get("boards"):
        parts.append("board: " + ", ".join(f["boards"]))
    return f"Path {f.get('path')} / Motor {f.get('motor')} — {'; '.join(parts)}"


# A vehicle's Obstructed bit is set whenever something is ahead of it — this is
# NORMAL queuing behind another pallet or at a station dwell (mold dwell is 30 s).
# So obstruction alone is "queued", not a fault. Only a long, unbroken stall (or
# the HLC's own AlarmPresent bit) indicates a real jam.
JAM_OBSTRUCT_SECS = 90.0


def vehicle_alarm_kind(a: dict | None) -> str | None:
    """Most significant state for a cart, or None.
    Priority: jammed (HLC AlarmPresent) > hindered > queued (Obstructed) > suspect.
    Obstructed alone is normal traffic — always "queued", never "jammed"."""
    if not a:
        return None
    if a.get("alarm"):
        return "jammed"     # AlarmPresent set by HLC = real fault → red JAMMED
    if a.get("obstructed"):
        return "queued"     # something ahead = normal queuing, never a jam
    if a.get("hindered"):
        return "hindered"
    if a.get("suspect"):
        return "suspect"
    return None


# ── Homing-blocker / alarm analysis ─────────────────────────────────────────
# severity strings drive the UI color: "critical" (red), "warning" (amber), "info"
SEV_COLORS = {"critical": "#e74c3c", "warning": "#f39c12", "info": "#2980b9"}


def _nc_state(snap, i: int) -> int | None:
    nc = snap.nc_status[i] if i < len(snap.nc_status) else None
    s = nc.get("state") if nc else None
    return int(s) if s is not None else None


def _incomplete_paths(snap) -> list[int]:
    """Paths whose last RESET/STARTUP command has NOT reported COMPLETE (0x80)."""
    pcs = getattr(snap, "path_cmd_status", None) or []
    bad = []
    for p in range(1, (snap.max_path or MAX_PATHS) + 1):
        st = pcs[p] if p < len(pcs) else None
        if st is not None and int(st) != MMI_CMD_COMPLETE:
            bad.append(p)
    return bad


def _path_cmd_cause(snap, cmd: str, complete_step: int) -> str:
    bad = _incomplete_paths(snap)
    who = ", ".join(f"Path {p}" for p in bad) if bad else "one or more paths"
    mf_paths = sorted({f["path"] for f in (getattr(snap, "motor_faults", None) or [])
                       if f.get("serious")})
    extra = ""
    if mf_paths:
        extra = (f" Serious motor faults are present on path(s) "
                 f"{', '.join(str(p) for p in mf_paths)} — likely why the {cmd} did not complete.")
    return (f"Step {complete_step} loops until every path reports its {cmd} command COMPLETE "
            f"(status 0x80). Not complete: {who}. That path's motors did not accept or finish the "
            f"{cmd} — this is in the path/motor subsystem (HLC), not the cold-start routine.{extra}")


def homing_diagnosis(snap, dwell_s: float) -> tuple[str, str, str] | None:
    """When homing is stuck, name the exact wait condition and which OTHER routine /
    subsystem owns it. The cold_start_service steps are pure wait-gates on tags that
    other routines (or the HLC) produce, so a hang is always traceable to one of them.
    Returns (severity, title, detail) or None when not stuck."""
    step = snap.cold_start_step
    if step == 5 or dwell_s < HOMING_STUCK_SECS:
        return None
    phase, _desc, _ = cold_start_info(step)
    title = f"Homing stuck at step {step} ({phase}) for {int(dwell_s)}s"

    if step in (17, 18):
        bad = [i for i in range(1, (snap.max_nc or 1) + 1) if _nc_state(snap, i) != NC_OPERATIONAL]
        if bad:
            who = ", ".join(f"NC {i} ({NC_STATES.get(_nc_state(snap, i), ('?', ''))[0]})" for i in bad)
            cause = (f"Step 18 loops until EVERY Node Controller reports OPERATIONAL (state 3). "
                     f"Not operational: {who}. This is the Node Controller / HLC, not the cold-start "
                     f"routine — check NC power, the NCHost/config file, and motor communications.")
        else:
            cause = ("Step 17/18 waits for the Node Controllers. They now read operational, so this "
                     "is likely a brief transition; if it persists, re-check NC comms and the HLC.")
        return ("critical", title, cause)

    if step == 20:
        if not snap.hlc_link:
            cause = ("Step 20 needs hlc_link_status TRUE to send the RESET command, but the "
                     "hlc_link_monitor routine has dropped the link (HLC heartbeat not changing). "
                     "Fix the HLC PC / NCHost / Ethernet to 192.168.1.200.")
        elif getattr(snap, "msg_path_cmd_step", None) not in (None, 10):
            cause = (f"Step 20 is waiting for the path-command message service to be idle "
                     f"(msg_service_path_cmd_step should be 10; it is {snap.msg_path_cmd_step}). "
                     f"That MSG-service routine is stuck mid-command — a previous path MSG never "
                     f"completed. Check the path-command MSG instruction and the HLC.")
        else:
            cause = ("Step 20 should be sending the RESET command (gated on hlc_link_status and the "
                     "path-command MSG service being idle). Both look OK here — re-check the HLC.")
        return ("critical", title, cause)

    if step in (25, 30):
        return ("critical", title, _path_cmd_cause(snap, "RESET", 30))
    if step in (50, 55, 60):
        return ("critical", title, _path_cmd_cause(snap, "STARTUP", 60))
    if step in (70, 80):
        return ("warning", title,
                "Step 70/80 is a 1-second internal wait for the HLC to publish vehicle positions. "
                "If it is stuck here the cold-start timer itself is not advancing — unusual.")
    if step in (90, 100):
        return ("warning", title,
                "Step 90/100 scans MMI_vehicle_status and orders each discovered pallet to Home. "
                "If stuck, the HLC is reporting no vehicles (none discovered) or the vehicle manager "
                "is not accepting orders.")
    # any other step (10/15/16 are fast inits) — generic
    return ("warning", title,
            f"The cold-start routine has not advanced past step {step}. {cold_start_detail(step)}")


def analyze_status(snap, homing_dwell_s: float = 0.0) -> list[tuple[str, str, str]]:
    """Return a list of (severity, title, detail) describing active alarms and
    anything that may be preventing the MagneMotion system from homing out."""
    out: list[tuple[str, str, str]] = []
    step = snap.cold_start_step
    homing = step != 5

    # ── real MagneMotion fault bits (from the Alarms program) ───────────────
    if snap.vehicle_fault:
        out.append(("critical", "MagneMotion Vehicle Fault",
                    "The Alarms program has a MagneMotion_Vehicle_Fault active. A vehicle/pallet is "
                    "faulted (often an obstruction or lost vehicle). This blocks homing — clear it and reset."))
    if snap.motor_fault:
        out.append(("critical", "MagneMotion Motor Fault",
                    "The Alarms program has a MagneMotion_Motor_Fault active. A motor/path has faulted. "
                    "Homing cannot complete startup until the motor fault is cleared."))

    # ── communications ──────────────────────────────────────────────────────
    if not snap.hlc_link:
        out.append(("critical", "HLC link DOWN",
                    "The PLC is not communicating with the MagneMotion High-Level Controller "
                    "(heartbeat not changing). Homing cannot proceed and pallets will not move. "
                    "Check the HLC PC, NCHost, and the Ethernet link to 192.168.1.200."))

    # ── node controllers (only the ones that exist) ─────────────────────────
    max_nc = snap.max_nc or 1
    bad_ncs = []
    for i in range(1, max_nc + 1):
        nc = snap.nc_status[i] if i < len(snap.nc_status) else None
        state = nc.get("state") if nc else None
        if state is not None and int(state) != NC_OPERATIONAL:   # 3 = OPERATIONAL
            label = NC_STATES.get(int(state), (f"state {state}", ""))[0]
            bad_ncs.append((i, label))
    if bad_ncs:
        names = ", ".join(f"NC {i} ({lbl})" for i, lbl in bad_ncs)
        sev = "critical" if homing else "warning"
        out.append((sev, "Node Controller not operational",
                    f"{names} is not OPERATIONAL. "
                    + ("Homing waits at step 17 until every Node Controller is operational. "
                       if step == 17 else "")
                    + "Check NC power, the configuration file, and motor communications."))

    # ── jammed / hindered / suspect pallets ─────────────────────────────────
    # "jammed" = HLC AlarmPresent bit set. Obstructed = normal queuing, not reported here.
    jammed, hindered, suspect, queued = [], [], [], []
    for i in range(1, len(snap.vehicle_alarms)):
        kind = vehicle_alarm_kind(snap.vehicle_alarms[i])
        if kind == "jammed":
            jammed.append(i)
        elif kind == "hindered":
            hindered.append(i)
        elif kind == "suspect":
            suspect.append(i)
        elif kind == "queued":
            queued.append(i)
    if jammed:
        out.append(("critical", f"Pallet JAMMED: {_ids(jammed)}",
                    "The HLC has raised an AlarmPresent fault on these pallets. "
                    "Something is physically wrong — check the Live Track tab (red carts), "
                    "clear any obstruction, then fault-reset or re-home."))
    if hindered:
        out.append(("warning", f"Pallet hindered: {_ids(hindered)}",
                    "These pallets are moving slower than commanded (drag, a tight spot, or crowding)."))
    if suspect:
        out.append(("info", f"Pallet suspect: {_ids(suspect)}",
                    "These pallets were manually moved out of position and the HLC is unsure of them."))
    if queued and not jammed:
        out.append(("info", f"{len(queued)} pallet(s) queued behind others",
                    "Normal traffic — these pallets are waiting for the unit ahead to move. Not a fault."))

    # ── explicit pallet-blocked flag ────────────────────────────────────────
    if snap.pallet_blocked:
        out.append(("warning", "MagneMotion_Pallet_Blocked is set",
                    "The PLC has flagged a blocked pallet condition. Often paired with an obstructed "
                    "pallet above — clear the blockage to continue."))

    # ── path health ─────────────────────────────────────────────────────────
    max_path = snap.max_path or 6
    bad_paths = []
    for i in range(1, max_path + 1):
        ps = snap.path_status[i] if i < len(snap.path_status) else None
        st = ps.get("state") if ps else None
        if st is not None and int(st) != PATH_OPERATIONAL:   # 2 = OPERATIONAL
            label = PATH_STATES.get(int(st), (f"state {st}", ""))[0]
            bad_paths.append((i, label))
    if bad_paths and not homing:
        names = ", ".join(f"Path {i} ({lbl})" for i, lbl in bad_paths)
        out.append(("warning", "Path not operational",
                    f"{names}. The track is idle but not all paths are running — a re-home (cold start) "
                    "may be needed, or a path/motor fault is present."))

    # ── motor / driver-board faults (MMI_path_ml_faults_status) ─────────────
    mfaults = getattr(snap, "motor_faults", None) or []
    serious = [f for f in mfaults if f.get("serious")]
    minor   = [f for f in mfaults if not f.get("serious")]
    if serious:
        shown = "; ".join(motor_fault_str(f) for f in serious[:6])
        more = f"  (+{len(serious) - 6} more)" if len(serious) > 6 else ""
        out.append(("critical", f"Motor/driver fault on {len(serious)} motor(s)",
                    f"{shown}{more}. A MagneMover motor is faulted (comms, driver board, FastStop, "
                    "or not responding). Homing/startup can be blocked until the motor is cleared."))
    if minor:
        shown = "; ".join(motor_fault_str(f) for f in minor[:6])
        more = f"  (+{len(minor) - 6} more)" if len(minor) > 6 else ""
        out.append(("info", f"{len(minor)} motor(s) in a non-running state",
                    f"{shown}{more}. Usually transient (config / diagnostic / suspended) during "
                    "startup or homing — not necessarily a fault."))

    # ── homing stuck (step-aware root-cause diagnosis) ──────────────────────
    if homing:
        diag = homing_diagnosis(snap, homing_dwell_s)
        if diag:
            out.append(diag)

    # ── all clear ───────────────────────────────────────────────────────────
    if not out:
        if homing:
            out.append(("info", "Homing in progress — no blockers detected",
                        "The cold-start routine is advancing normally. No alarms or blockers found."))
        else:
            out.append(("info", "No active alarms",
                        "System is running and no pallet/path/communication alarms are present."))
    return out


def _ids(nums: list[int]) -> str:
    return ", ".join(str(n) for n in nums)
