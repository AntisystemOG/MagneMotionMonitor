"""Thread-safe EtherNet/IP reader for the Boxing Station MagneMotion PLC."""
from __future__ import annotations
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pycomm3 import LogixDriver

from .system_data import (
    MAX_VEHICLES, MAX_PATHS, MAX_NC, MAX_STATIONS, MAX_MOTOR,
    T_HEARTBEAT, T_VEHICLE_ST, T_PATH_ST, T_NC_ST, T_VEH_MGR,
    T_GLOBAL_VEL, T_GLOBAL_ACC, T_VEHICLE_ALARMS, T_PATH_CMD_ST, T_PATH_ML_FAULTS,
    PT_COLD_STEP, PT_RECOVERING, PT_HLC_LINK, PT_NC_OPER, PT_VEH_ID,
    PT_PALLETS_SYS, PT_MM_READY, PT_BLOCKED, PT_VEH_MOLDS,
    PT_STATIONS, PT_VEH_IN_PATH, PT_MAX_NC, PT_MAX_VEH, PT_MAX_PATH, PT_MAX_MOTOR,
    PT_HOMING_CNT, PT_DEST_MOLD1, PT_DEST_MOLD2, PT_CLEANOUT,
    PT_MODULES_AUTO, PT_CMD_COUNT, T_PROP_POWER, decode_vehicle_alarm, decode_motor_fault,
    PT_PALLETS_AT_CLEANOUT, PT_CONFIRM_CLEANOUT, AL_VEHICLE_FAULT, AL_MOTOR_FAULT,
    PT_MSG_PATH_CMD_STEP, PT_CS_CMD_COUNT, PT_CS_TIMER_ACC, PT_CS_TIMER_PRE,
)

# Motor/driver-board faults are read on a slower cadence than the main poll —
# the 2D MMI_path_ml_faults_status array is large and these faults change slowly.
ML_FAULT_INTERVAL = 5.0   # seconds between full motor-fault scans


@dataclass
class SystemSnapshot:
    """All data read in one poll cycle."""
    # Program-scope scalars
    cold_start_step:   int  = 5
    recovering:        bool = False
    hlc_link:          bool = False
    nc_operational:    int  = 0
    vehicles_id:       int  = 0
    pallets_in_system: int  = 0
    mm_ready:          bool = False
    pallet_blocked:    bool = False
    vehicles_at_molds: int  = 0
    homing_count:      int  = 0
    dest_mold1:        bool = False
    dest_mold2:        bool = False
    cleanout:          bool = False
    modules_in_auto:   int  = 0
    cmd_count:         int  = 0
    max_nc:            int  = 1
    max_path:          int  = 6
    max_veh:           int  = 64
    max_motor:         int  = 13
    pallets_at_cleanout: bool = False
    confirm_cleanout:    bool = False
    vehicle_fault:       bool = False
    motor_fault:         bool = False

    # Controller-scope scalars
    heartbeat:    int  = 0
    global_vel:   float = 0.0
    global_acc:   float = 0.0
    propulsion_power: Optional[bool] = None   # None = couldn't read

    # Arrays — index 0 unused (1-based from MagneMotion)
    vehicle_status: list[Optional[dict]] = field(default_factory=lambda: [None] * (MAX_VEHICLES + 1))
    path_status:    list[Optional[dict]] = field(default_factory=lambda: [None] * (MAX_PATHS    + 1))
    nc_status:      list[Optional[dict]] = field(default_factory=lambda: [None] * (MAX_NC       + 1))
    vehicle_mgr:    list[Optional[dict]] = field(default_factory=lambda: [None] * (MAX_VEHICLES + 1))
    stations:       list[Optional[dict]] = field(default_factory=lambda: [None] * (MAX_STATIONS + 1))
    vehicles_in_path: list[int]          = field(default_factory=lambda: [0] * 10)
    vehicle_alarms: list[Optional[dict]] = field(default_factory=lambda: [None] * (MAX_VEHICLES + 1))
    # Per-motor faults: only motors WITH a fault appear, each as
    # {path, motor, motor_states[], comm[], boards[], serious}.
    motor_faults:   list[dict]           = field(default_factory=list)
    # Homing root-cause inputs (what the cold-start steps actually wait on)
    msg_path_cmd_step: Optional[int]     = None   # path-command MSG service step (idle = 10)
    # Per-path last-accepted RESET/STARTUP completion status (index 1-based; 0x80 = COMPLETE)
    path_cmd_status: list[Optional[int]] = field(default_factory=lambda: [None] * (MAX_PATHS + 1))
    # Per-path last-accepted command count (matched against cs_cmd_count for progress)
    path_cmd_count:  list[Optional[int]] = field(default_factory=lambda: [None] * (MAX_PATHS + 1))
    # Cold-start command count + RESET/STARTUP timeout timer (ms) — for progress + countdown
    cs_cmd_count:   Optional[int]        = None
    cs_timer_acc:   int                  = 0
    cs_timer_pre:   int                  = 0


class PLCReader:
    """Reads the Boxing Station MagneMotion controller over EtherNet/IP."""

    def __init__(self):
        self._plc: Optional[LogixDriver] = None
        self._lock = threading.RLock()
        self._obstruct_since: dict[int, float] = {}   # vehicle_id → monotonic time obstruction began
        self._ml_last: float = 0.0                    # last motor-fault scan (monotonic)
        self._ml_cache: list[dict] = []               # cached motor faults between scans

    # ── lifecycle ────────────────────────────────────────────────────────────

    def connect(self, ip: str) -> Tuple[bool, str]:
        with self._lock:
            try:
                if self._plc:
                    try:
                        self._plc.close()
                    except Exception:
                        pass
                self._plc = LogixDriver(ip)
                self._plc.open()
                self._obstruct_since.clear()   # stale timers from before this session are invalid
                self._ml_last = 0.0            # force a motor-fault scan on the first poll
                self._ml_cache = []
                return (True, f"Connected to {ip}") if self._plc.connected else (False, "No connection established")
            except Exception as e:
                self._plc = None
                return False, str(e)

    def disconnect(self):
        with self._lock:
            if self._plc:
                try:
                    self._plc.close()
                except Exception:
                    pass
                self._plc = None

    @property
    def connected(self) -> bool:
        return self._plc is not None and self._plc.connected

    # ── low-level read ───────────────────────────────────────────────────────

    def _read(self, *tags: str) -> Dict[str, Any]:
        if not tags:
            return {}
        with self._lock:
            if not self.connected:
                return {}
            try:
                results = self._plc.read(*tags)
                if not isinstance(results, (list, tuple)):
                    results = [results]
                return {r.tag: r.value for r in results if r is not None and not r.error}
            except Exception:
                return {}

    def _read_array(self, base: str, start: int, count: int) -> List[Optional[Any]]:
        tags = [f"{base}[{i}]" for i in range(start, start + count)]
        raw = self._read(*tags)
        return [raw.get(f"{base}[{i}]") for i in range(start, start + count)]

    # ── full poll ────────────────────────────────────────────────────────────

    def poll(self) -> SystemSnapshot:
        snap = SystemSnapshot()
        if not self.connected:
            return snap

        # ── scalar tags (one batch) ──────────────────────────────────────────
        scalar_tags = [
            PT_COLD_STEP, PT_RECOVERING, PT_HLC_LINK, PT_NC_OPER, PT_VEH_ID,
            PT_PALLETS_SYS, PT_MM_READY, PT_BLOCKED, PT_VEH_MOLDS,
            PT_HOMING_CNT, PT_DEST_MOLD1, PT_DEST_MOLD2, PT_CLEANOUT,
            PT_MODULES_AUTO, PT_CMD_COUNT, PT_MAX_NC, PT_MAX_PATH, PT_MAX_VEH, PT_MAX_MOTOR,
            PT_PALLETS_AT_CLEANOUT, PT_CONFIRM_CLEANOUT, AL_VEHICLE_FAULT, AL_MOTOR_FAULT,
            PT_MSG_PATH_CMD_STEP, PT_CS_CMD_COUNT, PT_CS_TIMER_ACC, PT_CS_TIMER_PRE,
            T_HEARTBEAT, T_GLOBAL_VEL, T_GLOBAL_ACC,
        ]
        s = self._read(*scalar_tags)

        snap.cold_start_step   = int(s.get(PT_COLD_STEP,   5)  or 5)
        snap.recovering        = bool(s.get(PT_RECOVERING,  False))
        snap.hlc_link          = bool(s.get(PT_HLC_LINK,    False))
        snap.nc_operational    = int(s.get(PT_NC_OPER,      0)  or 0)
        snap.vehicles_id       = int(s.get(PT_VEH_ID,       0)  or 0)
        snap.pallets_in_system = int(s.get(PT_PALLETS_SYS,  0)  or 0)
        snap.mm_ready          = bool(s.get(PT_MM_READY,    False))
        snap.pallet_blocked    = bool(s.get(PT_BLOCKED,     False))
        snap.vehicles_at_molds = int(s.get(PT_VEH_MOLDS,   0)  or 0)
        snap.homing_count      = int(s.get(PT_HOMING_CNT,   0)  or 0)
        snap.dest_mold1        = bool(s.get(PT_DEST_MOLD1,  False))
        snap.dest_mold2        = bool(s.get(PT_DEST_MOLD2,  False))
        snap.cleanout          = bool(s.get(PT_CLEANOUT,    False))
        snap.modules_in_auto   = int(s.get(PT_MODULES_AUTO, 0)  or 0)
        snap.cmd_count         = int(s.get(PT_CMD_COUNT,    0)  or 0)
        snap.max_nc            = int(s.get(PT_MAX_NC,       1)  or 1)
        snap.max_path          = int(s.get(PT_MAX_PATH,     6)  or 6)
        snap.max_veh           = int(s.get(PT_MAX_VEH,     64)  or 64)
        snap.max_motor         = int(s.get(PT_MAX_MOTOR,   MAX_MOTOR) or MAX_MOTOR)
        snap.pallets_at_cleanout = bool(s.get(PT_PALLETS_AT_CLEANOUT, False))
        snap.confirm_cleanout    = bool(s.get(PT_CONFIRM_CLEANOUT,    False))
        snap.vehicle_fault       = bool(s.get(AL_VEHICLE_FAULT,       False))
        snap.motor_fault         = bool(s.get(AL_MOTOR_FAULT,         False))
        snap.heartbeat         = int(s.get(T_HEARTBEAT,     0)  or 0)
        snap.global_vel        = float(s.get(T_GLOBAL_VEL,  0)  or 0)
        snap.global_acc        = float(s.get(T_GLOBAL_ACC,  0)  or 0)
        snap.msg_path_cmd_step = (int(s[PT_MSG_PATH_CMD_STEP])
                                  if PT_MSG_PATH_CMD_STEP in s and s[PT_MSG_PATH_CMD_STEP] is not None
                                  else None)
        snap.cs_cmd_count      = (int(s[PT_CS_CMD_COUNT])
                                  if PT_CS_CMD_COUNT in s and s[PT_CS_CMD_COUNT] is not None else None)
        snap.cs_timer_acc      = int(s.get(PT_CS_TIMER_ACC, 0) or 0)
        snap.cs_timer_pre      = int(s.get(PT_CS_TIMER_PRE, 0) or 0)

        # propulsion power — best-effort; absent from dict if it didn't read
        pp = self._read(T_PROP_POWER)
        snap.propulsion_power = bool(pp[T_PROP_POWER]) if T_PROP_POWER in pp else None

        # ── vehicles_in_path[0..9] ───────────────────────────────────────────
        vip_tags = [f"{PT_VEH_IN_PATH}[{i}]" for i in range(10)]
        vip_raw = self._read(*vip_tags)
        snap.vehicles_in_path = [
            int(vip_raw.get(f"{PT_VEH_IN_PATH}[{i}]") or 0) for i in range(10)
        ]

        # ── MMI_vehicle_status[1..64] ────────────────────────────────────────
        veh_raw = self._read_array(T_VEHICLE_ST, 1, MAX_VEHICLES)
        snap.vehicle_status = [None] + veh_raw   # index 0 = None (unused)

        # active carts = those the HLC is tracking (Path_ID non-zero). Only read
        # per-vehicle detail/alarms for these — avoids ~320 wasted tag reads/poll.
        active_ids = [
            i for i in range(1, MAX_VEHICLES + 1)
            if snap.vehicle_status[i] and (snap.vehicle_status[i].get("Path_ID") or 0)
        ]

        # ── MMI_vehicle_alarms — active carts only ───────────────────────────
        snap.vehicle_alarms = [None] * (MAX_VEHICLES + 1)
        if active_ids:
            ar = self._read(*[f"{T_VEHICLE_ALARMS}[{i}]" for i in active_ids])
            for i in active_ids:
                raw = ar.get(f"{T_VEHICLE_ALARMS}[{i}]")
                snap.vehicle_alarms[i] = decode_vehicle_alarm(raw) if raw is not None else None
        # Track continuous-obstruction duration (queuing vs real stall).
        # A truly stalled cart has Obstructed=True AND velocity ≈ 0.  If the cart
        # is still moving (even slowly through a queue) the timer resets so normal
        # production queuing never accumulates into a false jam alarm.
        _MOVING = 0.01   # m/s — same threshold as the track display
        now = time.monotonic()
        for vid in range(1, MAX_VEHICLES + 1):
            a = snap.vehicle_alarms[vid]
            vs = snap.vehicle_status[vid]
            vel = abs(float((vs or {}).get("Velocity", 0) or 0))
            if a and a.get("obstructed") and vel < _MOVING:
                self._obstruct_since.setdefault(vid, now)
                a["obstructed_secs"] = now - self._obstruct_since[vid]
            else:
                self._obstruct_since.pop(vid, None)
                if a:
                    a["obstructed_secs"] = 0.0

        # ── MMI_path_status[1..8] ────────────────────────────────────────────
        path_raw = self._read_array(T_PATH_ST, 1, MAX_PATHS)
        snap.path_status = [None] + path_raw

        # ── MMI_path_command_status[1..8] — RESET/STARTUP completion per path ─
        # This is what cold-start steps 30 & 60 wait on; lets us pinpoint which
        # path is blocking a home-out (completion status != 0x80).
        pcs_raw = self._read_array(T_PATH_CMD_ST, 1, MAX_PATHS)
        snap.path_cmd_status = [None]
        snap.path_cmd_count = [None]
        for d in pcs_raw:
            if isinstance(d, dict):
                snap.path_cmd_status.append(d.get("last_command_accepted_completion_status"))
                snap.path_cmd_count.append(d.get("last_command_accepted_count"))
            else:
                snap.path_cmd_status.append(None)
                snap.path_cmd_count.append(None)

        # ── MMI_node_controller_status[1..8] ────────────────────────────────
        nc_raw = self._read_array(T_NC_ST, 1, MAX_NC)
        snap.nc_status = [None] + nc_raw

        # ── vehicle_mgr_array — active carts only ────────────────────────────
        snap.vehicle_mgr = [None] * (MAX_VEHICLES + 1)
        if active_ids:
            mgr_tags = []
            for i in active_ids:
                mgr_tags += [
                    f"{T_VEH_MGR}[{i}].dest_station_id",
                    f"{T_VEH_MGR}[{i}].arrived_station_id",
                    f"{T_VEH_MGR}[{i}].state",
                    f"{T_VEH_MGR}[{i}].order_number",
                ]
            mgr_raw = self._read(*mgr_tags)
            for i in active_ids:
                snap.vehicle_mgr[i] = {
                    "dest_station_id":    mgr_raw.get(f"{T_VEH_MGR}[{i}].dest_station_id"),
                    "arrived_station_id": mgr_raw.get(f"{T_VEH_MGR}[{i}].arrived_station_id"),
                    "state":              mgr_raw.get(f"{T_VEH_MGR}[{i}].state"),
                    "order_number":       mgr_raw.get(f"{T_VEH_MGR}[{i}].order_number"),
                }

        # ── stations_array[1..34] — read whole elements (34 reads, not 170) ──
        st_raw = self._read(*[f"{PT_STATIONS}[{i}]" for i in range(1, MAX_STATIONS)])
        snap.stations = [None]   # index 0 unused
        for i in range(1, MAX_STATIONS):
            d = st_raw.get(f"{PT_STATIONS}[{i}]")
            if isinstance(d, dict):
                snap.stations.append({
                    "state":            d.get("state"),
                    "active_vehicle_id":d.get("active_vehicle_id"),
                    "occupied":         d.get("occupied"),
                    "process_complete": d.get("process_complete"),
                    "station_hold_flag":d.get("station_hold_flag"),
                })
            else:
                snap.stations.append(None)

        # ── motor / driver-board faults (throttled, cached between scans) ────
        snap.motor_faults = self._read_motor_faults(snap.max_path or MAX_PATHS,
                                                    snap.max_motor or MAX_MOTOR)

        return snap

    def _read_motor_faults(self, max_path: int, max_motor: int) -> list[dict]:
        """Scan MMI_path_ml_faults_status[path, motor] for any motor with a fault.

        Large 2D array that changes slowly, so it is only re-read every
        ML_FAULT_INTERVAL seconds; in between, the cached result is returned."""
        now = time.monotonic()
        if now - self._ml_last < ML_FAULT_INTERVAL:
            return self._ml_cache
        self._ml_last = now

        max_path  = min(max_path,  MAX_PATHS)
        max_motor = min(max_motor, MAX_MOTOR)
        tags = [f"{T_PATH_ML_FAULTS}[{p},{m}]"
                for p in range(1, max_path + 1)
                for m in range(1, max_motor + 1)]
        raw = self._read(*tags)
        if not raw:                       # read failed / tag absent — keep last known
            return self._ml_cache

        faults: list[dict] = []
        for p in range(1, max_path + 1):
            for m in range(1, max_motor + 1):
                f = decode_motor_fault(raw.get(f"{T_PATH_ML_FAULTS}[{p},{m}]"))
                if f:
                    f["path"], f["motor"] = p, m
                    faults.append(f)
        self._ml_cache = faults
        return faults
