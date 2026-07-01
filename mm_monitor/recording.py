"""Record live SystemSnapshots to a file and play them back when offline.

Format: JSON-lines. First line is a header; each subsequent line is
{"t": <seconds-since-record-start>, "snap": {<SystemSnapshot fields>}}.
"""
from __future__ import annotations
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from .plc_reader import SystemSnapshot
from .system_data import APP_VERSION

RECORDINGS_DIR = Path(os.environ.get("APPDATA", Path.home())) / "MagneMotionMonitor" / "recordings"


class Recorder:
    """Appends snapshots to a .mmrec file while live."""

    def __init__(self):
        self._file = None
        self._t0 = 0.0
        self.count = 0
        self.path: Path | None = None

    @property
    def active(self) -> bool:
        return self._file is not None

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._t0 if self._file else 0.0

    def start(self, path: str | Path) -> bool:
        try:
            RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
            self._file = open(path, "w", encoding="utf-8")
            self._t0 = time.monotonic()
            self.count = 0
            self.path = Path(path)
            self._file.write(json.dumps({
                "header": "MagneMotionMonitor recording",
                "version": APP_VERSION,
                "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            }) + "\n")
            return True
        except Exception:
            self._file = None
            return False

    def add(self, snap: SystemSnapshot):
        if not self._file:
            return
        try:
            rec = {"t": round(time.monotonic() - self._t0, 3), "snap": asdict(snap)}
            self._file.write(json.dumps(rec) + "\n")
            self.count += 1
        except Exception:
            pass

    def stop(self):
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None


class Recording:
    """A loaded recording: a list of (timestamp, SystemSnapshot) frames."""

    def __init__(self, frames: list[tuple[float, SystemSnapshot]], path: Path | None = None):
        self.frames = frames
        self.path = path

    def __len__(self) -> int:
        return len(self.frames)

    @property
    def duration(self) -> float:
        return self.frames[-1][0] if self.frames else 0.0

    def snapshot(self, idx: int) -> SystemSnapshot:
        return self.frames[idx][1]

    def time_at(self, idx: int) -> float:
        return self.frames[idx][0]

    def index_for_time(self, t: float) -> int:
        """Last frame whose timestamp <= t."""
        idx = 0
        for i, (ft, _) in enumerate(self.frames):
            if ft <= t:
                idx = i
            else:
                break
        return idx

    @classmethod
    def load(cls, path: str | Path) -> "Recording":
        frames: list[tuple[float, SystemSnapshot]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if "snap" not in d:
                    continue  # header / metadata line
                try:
                    snap = SystemSnapshot(**d["snap"])
                except TypeError:
                    # tolerate older recordings missing newer fields
                    fields = SystemSnapshot().__dict__.keys()
                    snap = SystemSnapshot(**{k: v for k, v in d["snap"].items() if k in fields})
                frames.append((float(d.get("t", 0.0)), snap))
        return cls(frames, Path(path))
