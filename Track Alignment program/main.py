"""MagneMotion Track Alignment Tool — single-master-path edition.

Instead of dragging hundreds of points across six separate PLC paths, you edit
one continuous master loop with a minimal set of anchor points. The tool
interpolates between anchors and splits the result back into the six PLC
paths (1-6) at the known rail junctions, then writes the result to
mm_monitor/track_photo.py.

Key ideas:
- The master path follows the rail in travel order: 6 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6.
- Yellow dots are anchor points; larger black-ringed dots are the 6 PLC path
  junctions (split points).
- Drag any anchor to reshape the loop. Junctions can also move.
- Add anchors between existing ones for more curve control.
- Delete non-junction anchors to simplify.
- "Regenerate" interpolates a smooth path between anchors and updates the 6 PLC
  path displays.
"""
from __future__ import annotations
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QMouseEvent, QPainter,
    QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFormLayout, QGraphicsEllipseItem,
    QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene,
    QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QSpinBox, QSplitter, QVBoxLayout, QWidget, QGroupBox, QDoubleSpinBox,
)

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(r"C:\AI Projects\MagneMotionMonitor")
DEFAULT_TRACK_PHOTO = Path(r"C:\AI Projects\MagneMotionMonitor\mm_monitor\data\track_photo.png")
DEFAULT_TRACK_PY = Path(r"C:\AI Projects\MagneMotionMonitor\mm_monitor\track_photo.py")
DEFAULT_CSV = Path(__file__).parent / "track_points.csv"
HISTORY_DIR = Path(r"C:\AI Projects\MagneMotionMonitor\track_path_history")

# ── Colors ─────────────────────────────────────────────────────────────────
PATH_COLORS = {
    1: QColor(255, 0, 0),
    2: QColor(0, 120, 255),
    3: QColor(0, 180, 0),
    4: QColor(160, 0, 220),
    5: QColor(255, 140, 0),
    6: QColor(0, 200, 200),
}
MASTER_COLOR = QColor("yellow")
SPLIT_FILL = QColor("yellow")

PATH_LABELS: dict[int, str] = {
    1: "Mold 1 Entry/Exit (right junction stub)",
    2: "Mold 1 Spur — right vertical loop",
    3: "Lower connector (HOME / Cleanout / return)",
    4: "Mold 2 Spur — left vertical loop",
    5: "Mold 2 Entry/Exit (left junction stub)",
    6: "Top main rail (Pre-Load / Inspection / Roller Test / Offload)",
}

# Map CSV TrackLocation values to PLC path IDs. These match the *code* semantics
# used by mm_monitor/track_photo.py and track_geometry.py.
TRACK_LOCATION_TO_PATH: dict[str, int] = {
    "Top Main Rail": 6,
    "Right Vertical Loop": 2,
    "Left Vertical Loop": 4,
    "Middle Connector": 3,
}

# Travel order of the 6 PLC paths around the master loop.
PATH_ORDER = [6, 1, 2, 3, 4, 5]


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_waypoints(path: Path) -> dict[int, list[tuple[float, float]]]:
    import importlib.util
    spec = importlib.util.spec_from_file_location("track_photo", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.PATH_WAYPOINTS_PX)


def save_waypoints(path: Path, waypoints: dict[int, list[tuple[float, float]]]) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "PATH_WAYPOINTS_PX: dict[int, list[tuple[float, float]]] = {"
    start = text.find(marker)
    if start == -1:
        raise ValueError("Could not find PATH_WAYPOINTS_PX block")
    rest = text[start:]
    match = re.search(r"\n\ndef ", rest)
    end = start + match.start() if match else len(text)

    lines = ["PATH_WAYPOINTS_PX: dict[int, list[tuple[float, float]]] = {"]
    for pid in sorted(waypoints.keys()):
        pts = waypoints[pid]
        lines.append(f"    {pid}: [")
        for i in range(0, len(pts), 3):
            chunk = pts[i : i + 3]
            lines.append("        " + ", ".join(f"({x:.1f}, {y:.1f})" for x, y in chunk) + ",")
        lines.append("    ],")
    lines.append("}")

    new_text = text[:start] + "\n".join(lines) + "\n" + text[end:]
    path.write_text(new_text, encoding="utf-8")


def load_csv_points(path: Path) -> list[dict]:
    points = []
    if not path.exists():
        return points
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                points.append({
                    "station": row.get("Station", "").strip(),
                    "command": float(row.get("Command", 0) or 0),
                    "actual": float(row.get("Actual", 0) or 0),
                    "location": row.get("TrackLocation", "").strip(),
                })
            except ValueError:
                continue
    return points


# ── Geometry helpers ─────────────────────────────────────────────────────────
def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _poly_length(pts: list[tuple[float, float]]) -> float:
    s = 0.0
    for a, b in zip(pts, pts[1:]):
        s += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
    return s


def _rdp(pts: list[tuple[float, float]], epsilon: float) -> list[int]:
    """Ramer-Douglas-Peucker: return indices to keep."""
    if len(pts) < 3:
        return list(range(len(pts)))

    def _rec(start, end, keep):
        if end <= start + 1:
            return
        x1, y1 = pts[start]
        x2, y2 = pts[end]
        dx, dy = x2 - x1, y2 - y1
        seg_len2 = dx * dx + dy * dy
        max_idx = -1
        max_dist2 = -1.0
        for i in range(start + 1, end):
            x0, y0 = pts[i]
            if seg_len2 == 0:
                d2 = (x0 - x1) ** 2 + (y0 - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((x0 - x1) * dx + (y0 - y1) * dy) / seg_len2))
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                d2 = (x0 - proj_x) ** 2 + (y0 - proj_y) ** 2
            if d2 > max_dist2:
                max_dist2 = d2
                max_idx = i
        if max_idx != -1 and max_dist2 > epsilon * epsilon:
            keep.add(max_idx)
            _rec(start, max_idx, keep)
            _rec(max_idx, end, keep)

    keep = {0, len(pts) - 1}
    _rec(0, len(pts) - 1, keep)
    return sorted(keep)


def _interpolate(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _catmull_rom(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    """Catmull-Rom spline interpolation between p1 and p2."""
    t2 = t * t
    t3 = t2 * t
    x = 0.5 * (
        2 * p1[0]
        + (-p0[0] + p2[0]) * t
        + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
        + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
    )
    y = 0.5 * (
        2 * p1[1]
        + (-p0[1] + p2[1]) * t
        + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
        + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
    )
    return (x, y)


def _dense_segment(
    anchors: list[tuple[float, float]],
    start_idx: int,
    end_idx: int,
    spacing: float,
    smooth: bool = True,
) -> list[tuple[float, float]]:
    """Generate dense points along the anchor chain from start_idx to end_idx
    (wrapping around). Spacing is approximate pixel distance between output points."""
    n = len(anchors)
    if n < 2:
        return list(anchors)

    # Collect ordered anchor indices for this segment
    idxs = []
    i = start_idx
    while True:
        idxs.append(i)
        if i == end_idx:
            break
        i = (i + 1) % n
    if len(idxs) < 2:
        return [anchors[start_idx]]

    # Build a fine polyline through the anchors. If smoothing enabled and we have
    # enough points, use Catmull-Rom; otherwise linear.
    poly: list[tuple[float, float]] = []
    if smooth and len(anchors) >= 4 and len(idxs) >= 3:
        # Pre-sample each span with many points so resampling is accurate
        samples_per_span = 20
        for k in range(len(idxs) - 1):
            i1 = idxs[k]
            i2 = idxs[k + 1]
            i0 = idxs[k - 1] if k > 0 else (idxs[0] - 1) % n
            i3 = idxs[k + 2] if k + 2 < len(idxs) else (idxs[-1] + 1) % n
            p0, p1, p2, p3 = anchors[i0], anchors[i1], anchors[i2], anchors[i3]
            if k == 0:
                poly.append(p1)
            for step in range(1, samples_per_span + 1):
                t = step / samples_per_span
                poly.append(_catmull_rom(p0, p1, p2, p3, t))
    else:
        for k in range(len(idxs)):
            poly.append(anchors[idxs[k]])

    # Resample evenly at `spacing`
    if len(poly) < 2:
        return poly
    out = [poly[0]]
    remain = 0.0
    for a, b in zip(poly, poly[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg_len = (dx * dx + dy * dy) ** 0.5
        if seg_len == 0:
            continue
        ux, uy = dx / seg_len, dy / seg_len
        d = remain
        while d < seg_len:
            out.append((a[0] + ux * d, a[1] + uy * d))
            d += spacing
        remain = d - seg_len
    if _dist2(out[-1], poly[-1]) > 1.0:
        out.append(poly[-1])
    return out


def _station_pixel_positions(
    csv_rows: list[dict],
    track_py_path: Path,
) -> list[dict]:
    """Convert CSV station positions (meters) to pixel (x, y) using current waypoints."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("track_photo_module", str(track_py_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Need real path lengths to build the model; import project track_geometry
    sys.path.insert(0, str(PROJECT_DIR))
    try:
        from mm_monitor.track_geometry import build_track
        track = build_track()
        real_lengths = {pid: pg.length for pid, pg in track.paths.items()}
    finally:
        sys.path.pop(0)

    model = mod.PhotoTrackModel(real_lengths)

    results = []
    for row in csv_rows:
        loc = row.get("location", "").strip()
        path_id = TRACK_LOCATION_TO_PATH.get(loc)
        if path_id is None:
            continue
        try:
            pos_m = float(row.get("actual", row.get("command", 0)) or 0)
        except ValueError:
            continue
        pt = model.point_at(path_id, pos_m)
        if pt is None:
            continue
        results.append({
            "station": row.get("station", "").strip(),
            "path_id": path_id,
            "location": loc,
            "pos_m": pos_m,
            "x": pt[0],
            "y": pt[1],
        })
    return results


def _build_anchors_from_paths(
    waypoints: dict[int, list[tuple[float, float]]],
    epsilon: float = 8.0,
) -> tuple[list[tuple[float, float]], list[int]]:
    """Convert 6 PLC paths into a minimal anchor loop + 6 junction indices."""
    # Concatenate paths in travel order
    master: list[tuple[float, float]] = []
    junction_indices: list[int] = []
    for pid in PATH_ORDER:
        pts = waypoints.get(pid, [])
        if not pts:
            junction_indices.append(len(master))
            continue
        if master and _dist2(master[-1], pts[0]) < 1.0:
            # Skip shared junction point
            master.extend(pts[1:])
        else:
            master.extend(pts)
        # Junction is at the start of this path in the master
        junction_indices.append(len(master) - len(pts) + (1 if master and _dist2(master[-1], pts[-1]) < 1.0 else 0))

    # Recompute junction indices by exact point lookup
    junction_indices = []
    for pid in PATH_ORDER:
        pts = waypoints.get(pid, [])
        if not pts:
            junction_indices.append(0)
        else:
            start_pt = pts[0]
            idx = min(range(len(master)), key=lambda i: _dist2(master[i], start_pt))
            junction_indices.append(idx)

    # Reduce each inter-junction segment independently, always keeping junctions
    keep = set(junction_indices)
    n = len(master)
    for i in range(len(junction_indices)):
        a = junction_indices[i]
        b = junction_indices[(i + 1) % len(junction_indices)]
        if b > a:
            seg = master[a : b + 1]
        else:
            seg = master[a:] + master[: b + 1]
        seg_keep = _rdp(seg, epsilon)
        for k in seg_keep:
            real_idx = (a + k) % n
            keep.add(real_idx)

    anchors = [master[i] for i in sorted(keep)]
    # Map old junction indices to new anchor indices
    old_to_new = {old: sorted(keep).index(old) for old in junction_indices}
    new_junctions = [old_to_new[j] for j in junction_indices]
    return anchors, new_junctions


def _generate_plc_paths(
    anchors: list[tuple[float, float]],
    junction_indices: list[int],
    spacing: float,
    smooth: bool = True,
) -> dict[int, list[tuple[float, float]]]:
    """Interpolate between anchors and split into the 6 PLC paths."""
    out: dict[int, list[tuple[float, float]]] = {}
    n = len(junction_indices)
    for i, pid in enumerate(PATH_ORDER):
        start = junction_indices[i]
        end = junction_indices[(i + 1) % n]
        out[pid] = _dense_segment(anchors, start, end, spacing, smooth)
    return out


# ── Canvas items ───────────────────────────────────────────────────────────
class ReferenceMarker(QGraphicsEllipseItem):
    """Small static marker showing where a station should be."""

    def __init__(self, x: float, y: float, label: str):
        super().__init__(-4, -4, 8, 8)
        self.setPos(x, y)
        self.setPen(QPen(QColor("black"), 1))
        self.setBrush(QColor("yellow"))
        self.setZValue(15)
        text = QGraphicsSimpleTextItem(label, self)
        text.setBrush(QColor("black"))
        text.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        text.setPos(8, -8)


class StationMarker(QGraphicsEllipseItem):
    """Labeled station/pallet-stop marker from track_points.csv."""

    def __init__(self, x: float, y: float, label: str, path_id: int, pos_m: float):
        super().__init__(-6, -6, 12, 12)
        self.setPos(x, y)
        self.setPen(QPen(Qt.black, 2))
        color = PATH_COLORS.get(path_id, QColor("yellow"))
        self.setBrush(color)
        self.setZValue(20)
        self.label = label
        self.path_id = path_id
        self.pos_m = pos_m
        text = QGraphicsSimpleTextItem(label, self)
        text.setBrush(QColor("black"))
        text.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        text.setPos(10, -10)
        # White halo behind text for readability
        halo = QGraphicsSimpleTextItem(label, self)
        halo.setBrush(QColor("white"))
        halo.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        halo.setPos(11, -9)
        halo.setZValue(-1)
        text.setZValue(0)

    def set_highlighted(self, highlighted: bool):
        pen = QPen(QColor("red") if highlighted else Qt.black, 4 if highlighted else 2)
        self.setPen(pen)
        self.setZValue(40 if highlighted else 20)


class AnchorHandle(QGraphicsEllipseItem):
    """Draggable master-path anchor."""

    def __init__(self, idx: int, x: float, y: float, is_split: bool = False):
        size = 18 if is_split else 12
        super().__init__(-size / 2, -size / 2, size, size)
        self.idx = idx
        self.is_split = is_split
        self.setPos(x, y)
        self.setPen(QPen(Qt.black, 2))
        self.setBrush(SPLIT_FILL if is_split else MASTER_COLOR)
        self.setFlags(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(30 if is_split else 25)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.on_moved = None
        self.on_selected = None

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            p = QPointF(value)
            r = self.scene().sceneRect()
            p.setX(max(0, min(p.x(), r.width())))
            p.setY(max(0, min(p.y(), r.height())))
            return p
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            pos = self.pos()
            if self.on_moved:
                self.on_moved(self.idx, pos.x(), pos.y())
        return super().itemChange(change, value)

    def mousePressEvent(self, event: QMouseEvent):
        self.setSelected(True)
        if self.on_selected:
            self.on_selected(self.idx)
        super().mousePressEvent(event)


class StopHandle(QGraphicsEllipseItem):
    """Draggable labeled station/pallet-stop handle."""

    def __init__(self, name: str, x: float, y: float, path_id: int, pos_m: float):
        super().__init__(-8, -8, 16, 16)
        self.name = name
        self.path_id = path_id
        self.pos_m = pos_m
        self.setPos(x, y)
        self.setPen(QPen(Qt.black, 2))
        self.setBrush(QColor("white"))
        self.setFlags(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(35)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.on_moved = None
        self.on_selected = None
        self.on_move_finished = None
        # Label text
        text = QGraphicsSimpleTextItem(name, self)
        text.setBrush(QColor("black"))
        text.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        text.setPos(10, -10)
        halo = QGraphicsSimpleTextItem(name, self)
        halo.setBrush(QColor("white"))
        halo.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        halo.setPos(11, -9)
        halo.setZValue(-1)
        text.setZValue(0)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            p = QPointF(value)
            r = self.scene().sceneRect()
            p.setX(max(0, min(p.x(), r.width())))
            p.setY(max(0, min(p.y(), r.height())))
            return p
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            pos = self.pos()
            if self.on_moved:
                self.on_moved(self.name, pos.x(), pos.y())
        return super().itemChange(change, value)

    def set_highlighted(self, highlighted: bool):
        pen = QPen(QColor("red") if highlighted else Qt.black, 4 if highlighted else 2)
        self.setPen(pen)
        self.setZValue(55 if highlighted else 35)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.on_moved:
            # Notify that dragging is finished so the UI can refresh safely
            self.on_move_finished(self.name)
        super().mouseReleaseEvent(event)


class TrackView(QGraphicsView):
    anchor_selected = Signal(int)
    anchor_moved = Signal(int, float, float)
    anchor_added = Signal(float, float)
    station_selected = Signal(str, int, float)
    stop_moved = Signal(str, float, float)
    stop_move_finished = Signal(str)
    stop_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setStyleSheet("border: 2px solid #444; background: #e0e0e0;")
        self.setBackgroundBrush(QColor(224, 224, 224))

        self._photo: QGraphicsPixmapItem | None = None
        self._master_line: QGraphicsPathItem | None = None
        self._path_lines: dict[int, QGraphicsPathItem] = {}
        self._handles: list[AnchorHandle] = []
        self._anchor_indices: list[int] = []
        self._split_indices: set[int] = set()
        self._master_points: list[tuple[float, float]] = []
        self._add_mode = False

    def load_image(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            print(f"ERROR: could not load image {path}")
            return
        self._scene.clear()
        self._path_lines.clear()
        self._handles.clear()
        self._photo = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(pixmap.rect())

    def add_reference_markers(self, markers: list[tuple[float, float, str]]) -> None:
        for x, y, label in markers:
            self._scene.addItem(ReferenceMarker(x, y, label))

    def set_station_markers(self, stations: list[dict]) -> None:
        # Clear old station markers
        for item in list(self._scene.items()):
            if isinstance(item, (StationMarker, StopHandle)):
                self._scene.removeItem(item)
        self._station_markers = []
        for s in stations:
            m = StopHandle(s["station"], s["x"], s["y"], s["path_id"], s["pos_m"])
            m.on_moved = lambda n, nx, ny: self.stop_moved.emit(n, nx, ny)
            m.on_move_finished = lambda n: self.stop_move_finished.emit(n)
            m.on_selected = lambda n: self.stop_selected.emit(n)
            self._scene.addItem(m)
            self._station_markers.append(m)

    def station_marker_clicked(self, scene_pos) -> dict | None:
        """Find the nearest station marker to a scene click."""
        best = None
        best_d2 = 400.0  # 20px threshold
        for m in getattr(self, "_station_markers", []):
            dx = m.pos().x() - scene_pos.x()
            dy = m.pos().y() - scene_pos.y()
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                best = m
        return best

    def set_master(self, anchors: list[tuple[float, float]], junction_indices: list[int]):
        self._master_points = list(anchors)
        self._split_indices = set(junction_indices)
        self._anchor_indices = list(range(len(anchors)))
        self.refresh()

    def refresh(self):
        for item in list(self._scene.items()):
            if isinstance(item, (AnchorHandle, QGraphicsPathItem)):
                self._scene.removeItem(item)
        self._handles.clear()
        self._path_lines.clear()
        self._master_line = None
        if not self._photo:
            return

        # Draw PLC path lines
        plc = _generate_plc_paths(self._master_points, list(self._split_indices), spacing=6.0, smooth=False)
        for pid, pts in plc.items():
            color = PATH_COLORS.get(pid, QColor("yellow"))
            line = QGraphicsPathItem()
            line.setPen(QPen(color, 2))
            line.setZValue(5)
            self._scene.addItem(line)
            self._path_lines[pid] = line
            if pts:
                path = QPainterPath()
                path.moveTo(pts[0][0], pts[0][1])
                for x, y in pts[1:]:
                    path.lineTo(x, y)
                line.setPath(path)

        # Draw master path as thin yellow line
        if self._master_points:
            line = QGraphicsPathItem()
            line.setPen(QPen(MASTER_COLOR, 1, Qt.PenStyle.DashLine))
            line.setZValue(4)
            self._scene.addItem(line)
            self._master_line = line
            path = QPainterPath()
            path.moveTo(self._master_points[0][0], self._master_points[0][1])
            for x, y in self._master_points[1:]:
                path.lineTo(x, y)
            path.closeSubpath()
            line.setPath(path)

        # Draw anchors
        for idx in self._anchor_indices:
            x, y = self._master_points[idx]
            h = AnchorHandle(idx, x, y, is_split=(idx in self._split_indices))
            h.on_moved = lambda i, nx, ny: self.anchor_moved.emit(i, nx, ny)
            h.on_selected = lambda i: self.anchor_selected.emit(i)
            self._scene.addItem(h)
            self._handles.append(h)

    def _redraw_lines(self):
        """Redraw master and PLC path lines without destroying handles."""
        # Update PLC path lines
        plc = _generate_plc_paths(self._master_points, list(self._split_indices), spacing=6.0, smooth=False)
        for pid, line in self._path_lines.items():
            pts = plc.get(pid, [])
            if pts:
                path = QPainterPath()
                path.moveTo(pts[0][0], pts[0][1])
                for x, y in pts[1:]:
                    path.lineTo(x, y)
                line.setPath(path)
            else:
                line.setPath(QPainterPath())
        # Update master line
        if self._master_line and self._master_points:
            path = QPainterPath()
            path.moveTo(self._master_points[0][0], self._master_points[0][1])
            for x, y in self._master_points[1:]:
                path.lineTo(x, y)
            path.closeSubpath()
            self._master_line.setPath(path)

    def update_anchor_pos(self, idx: int, x: float, y: float):
        """Update a single anchor coordinate and redraw lines without recreating handles."""
        if 0 <= idx < len(self._master_points):
            self._master_points[idx] = (x, y)
            self._redraw_lines()

    def set_add_mode(self, enabled: bool):
        self._add_mode = enabled
        self.setDragMode(QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.ScrollHandDrag)

    def highlight(self, idx: int):
        for h in self._handles:
            h.setPen(QPen(QColor("red") if h.idx == idx else Qt.black, 3 if h.idx == idx else 2))
            h.setZValue(35 if h.idx == idx else (30 if h.is_split else 25))

    def mousePressEvent(self, event: QMouseEvent):
        if self._add_mode and event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.pos())
            self.anchor_added.emit(pos.x(), pos.y())
            return
        # Stop handles are real items and will receive clicks naturally; no special hit test needed.
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 0.83
        self.scale(factor, factor)


# ── Main window ────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MagneMotion Track Stop Placement")
        self.resize(1800, 1000)
        self.setWindowIcon(QIcon(str(DEFAULT_TRACK_PHOTO)))

        self._img_path = DEFAULT_TRACK_PHOTO
        self._py_path = DEFAULT_TRACK_PY
        self._csv_path = DEFAULT_CSV
        self._anchors: list[tuple[float, float]] = []
        self._junction_indices: list[int] = []
        self._current_idx: int | None = None
        self._spacing = 6.0
        self._stations: list[dict] = []
        self._current_stop_name: str | None = None

        self._build_ui()
        self._build_menu()
        self._load_all()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        self._view = TrackView()
        self._view.anchor_selected.connect(self._on_selected)
        self._view.anchor_moved.connect(self._on_moved)
        self._view.anchor_added.connect(self._on_added)
        self._view.station_selected.connect(self._on_station_from_image)
        self._view.stop_moved.connect(self._on_stop_moved)
        self._view.stop_move_finished.connect(self._on_stop_move_finished)
        self._view.stop_selected.connect(self._on_stop_selected)

        # ── Sidebar: stop-centric navigation ─────────────────────────────────
        sidebar = QWidget()
        sidebar.setMaximumWidth(380)
        v = QVBoxLayout(sidebar)
        v.setSpacing(6)

        title = QLabel("<h2>MagneMotion Stop Placement</h2>")
        v.addWidget(title)

        info = QLabel(
            "Drag each white dot onto the exact rail stop position. "
            "The list shows every named pallet stop from the machine. "
            "Click a list item to jump to it. Save when done."
        )
        info.setWordWrap(True)
        v.addWidget(info)

        # Search/filter
        self._station_filter = QLineEdit()
        self._station_filter.setPlaceholderText("Search stops...")
        self._station_filter.textChanged.connect(self._refresh_station_list)
        v.addWidget(self._station_filter)

        # Stop list
        v.addWidget(QLabel("<b>All Stopping Points</b>"))
        self._station_list = QListWidget()
        self._station_list.setMaximumHeight(600)
        self._station_list.itemClicked.connect(self._on_station_clicked)
        v.addWidget(self._station_list)

        # Selected stop edit
        v.addWidget(QLabel("<b>Selected Stop</b>"))
        form = QFormLayout()
        self._spin_stop_x = QSpinBox()
        self._spin_stop_x.setRange(0, 5000)
        self._spin_stop_x.valueChanged.connect(self._on_stop_spin_changed)
        self._spin_stop_y = QSpinBox()
        self._spin_stop_y.setRange(0, 5000)
        self._spin_stop_y.valueChanged.connect(self._on_stop_spin_changed)
        form.addRow("Pixel X:", self._spin_stop_x)
        form.addRow("Pixel Y:", self._spin_stop_y)
        v.addLayout(form)

        self._btn_save_stops = QPushButton("Save Stop Positions")
        self._btn_save_stops.setStyleSheet("background: #27ae60; color: white; font-weight: bold; padding: 8px;")
        self._btn_save_stops.setToolTip("Write adjusted pixel positions to track_points_adjusted.csv")
        self._btn_save_stops.clicked.connect(self._save_stops)
        v.addWidget(self._btn_save_stops)

        # Anchor/path section (collapsible)
        self._gb_anchors = QGroupBox("Rail Path Anchors (advanced)")
        gb_v = QVBoxLayout(self._gb_anchors)

        self._btn_regen = QPushButton("Regenerate PLC Paths")
        self._btn_regen.setToolTip("Interpolate between current anchors and resample the 6 PLC paths")
        self._btn_regen.clicked.connect(self._regenerate)
        gb_v.addWidget(self._btn_regen)

        self._btn_reduce = QPushButton("Reduce Anchors")
        self._btn_reduce.setToolTip("Run RDP simplification between junctions to remove unnecessary anchors")
        self._btn_reduce.clicked.connect(self._reduce_now)
        gb_v.addWidget(self._btn_reduce)

        self._btn_reset = QPushButton("Reset to Loaded 6 Paths")
        self._btn_reset.clicked.connect(self._reset_to_loaded)
        gb_v.addWidget(self._btn_reset)

        self._btn_del_anchor = QPushButton("Delete Selected Anchor")
        self._btn_del_anchor.setToolTip("Junction points cannot be deleted")
        self._btn_del_anchor.clicked.connect(self._delete_selected_anchor)
        gb_v.addWidget(self._btn_del_anchor)

        self._chk_add = QCheckBox("Add Anchor Mode (click on image)")
        self._chk_add.stateChanged.connect(lambda s: self._view.set_add_mode(s == Qt.CheckState.Checked.value))
        gb_v.addWidget(self._chk_add)

        self._path_list = QListWidget()
        self._path_list.setMaximumHeight(100)
        gb_v.addWidget(self._path_list)

        self._gb_anchors.setCheckable(True)
        self._gb_anchors.setChecked(False)
        v.addWidget(self._gb_anchors)

        self._lbl_info = QLabel("Ready")
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet("background: #f0f0f0; padding: 6px; border: 1px solid #ccc;")
        v.addWidget(self._lbl_info)

        self._btn_save = QPushButton("Save Path to track_photo.py")
        self._btn_save.setStyleSheet("background: #2980b9; color: white; font-weight: bold; padding: 8px;")
        self._btn_save.clicked.connect(self._save)
        v.addWidget(self._btn_save)

        self._btn_export = QPushButton("Export waypoints to JSON...")
        self._btn_export.clicked.connect(self._export_json)
        v.addWidget(self._btn_export)

        v.addStretch()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._view)
        splitter.addWidget(sidebar)
        splitter.setSizes([1350, 360])
        layout.addWidget(splitter)

    def _build_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("File")
        fm.addAction("Open Track Image...", self._open_image)
        fm.addAction("Open track_photo.py...", self._open_py)
        fm.addAction("Reload", self._load_all)
        fm.addSeparator()
        fm.addAction("Save", self._save, "Ctrl+S")

    def _load_all(self):
        errors = []
        if not self._img_path.exists():
            errors.append(f"Image not found: {self._img_path}")
        if not self._py_path.exists():
            errors.append(f"Waypoints file not found: {self._py_path}")

        if errors:
            self._lbl_info.setText("\n".join(errors))
            QMessageBox.critical(self, "Load Error", "\n".join(errors))
            return

        try:
            wps = load_waypoints(self._py_path)
        except Exception as e:
            self._lbl_info.setText(f"Failed to load waypoints:\n{e}")
            QMessageBox.critical(self, "Load Error", f"Could not read {self._py_path}:\n{e}")
            return

        self._view.load_image(self._img_path)

        self._anchors, self._junction_indices = _build_anchors_from_paths(wps, epsilon=4.0)
        self._view.set_master(self._anchors, self._junction_indices)
        self._refresh_path_list()

        self._load_stations()
        self._update_info()

        QApplication.processEvents()
        if self._view.scene():
            self._view.fitInView(self._view.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, event):
        super().showEvent(event)
        QApplication.processEvents()
        if self._view.scene():
            self._view.fitInView(self._view.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _refresh_path_list(self):
        self._path_list.clear()
        plc = _generate_plc_paths(self._anchors, self._junction_indices, self._spacing, smooth=False)
        for pid in PATH_ORDER:
            pts = plc.get(pid, [])
            label = PATH_LABELS.get(pid, "")
            text = f"Path {pid}  ({len(pts)} points)"
            if label:
                text += f" — {label}"
            item = QListWidgetItem(text)
            color = PATH_COLORS.get(pid, QColor("yellow"))
            item.setForeground(color)
            self._path_list.addItem(item)

    def _update_info(self):
        plc = _generate_plc_paths(self._anchors, self._junction_indices, self._spacing, smooth=False)
        total = sum(len(v) for v in plc.values())
        self._lbl_info.setText(
            f"Stops: {len(self._stations)}\n"
            f"Anchors: {len(self._anchors)} (junctions: {len(self._junction_indices)})\n"
            f"PLC path points: {total}\n\n"
            "1. Drag white stop dots onto exact rail positions.\n"
            "2. Save Stop Positions writes track_points_adjusted.csv.\n"
            "3. If the rail path itself is off, expand Rail Path Anchors."
        )

    def _on_selected(self, idx: int):
        self._current_idx = idx
        self._view.highlight(idx)
        x, y = self._anchors[idx]
        self._spin_x.blockSignals(True)
        self._spin_y.blockSignals(True)
        self._spin_x.setValue(int(round(x)))
        self._spin_y.setValue(int(round(y)))
        self._spin_x.blockSignals(False)
        self._spin_y.blockSignals(False)
        is_split = "JUNCTION" if idx in self._junction_indices else "anchor"
        self._lbl_info.setText(f"Selected {is_split} {idx}: ({x:.1f}, {y:.1f})")

    def _on_moved(self, idx: int, x: float, y: float):
        self._anchors[idx] = (x, y)
        self._view.update_anchor_pos(idx, x, y)
        if self._current_idx == idx:
            self._spin_x.blockSignals(True)
            self._spin_y.blockSignals(True)
            self._spin_x.setValue(int(round(x)))
            self._spin_y.setValue(int(round(y)))
            self._spin_x.blockSignals(False)
            self._spin_y.blockSignals(False)
            self._lbl_info.setText(f"Moving anchor {idx}: ({x:.1f}, {y:.1f})")

    def _on_spin_changed(self):
        if self._current_idx is None:
            return
        x = float(self._spin_x.value())
        y = float(self._spin_y.value())
        self._anchors[self._current_idx] = (x, y)
        self._view.set_master(self._anchors, self._junction_indices)

    def _load_stations(self):
        try:
            rows = load_csv_points(self._csv_path)
            self._stations = _station_pixel_positions(rows, self._py_path)
            self._view.set_station_markers(self._stations)
            self._refresh_station_list()
        except Exception as e:
            print(f"Could not load stations: {e}")
            self._stations = []

    def _refresh_station_list(self, text: str = ""):
        self._station_list.clear()
        filt = text.lower() if text else ""
        for s in self._stations:
            display = f"{s['station']}  — Path {s['path_id']} @ {s['pos_m']:.3f}m  ({s['x']:.0f},{s['y']:.0f})"
            if filt and filt not in display.lower():
                continue
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, s["station"])
            color = PATH_COLORS.get(s["path_id"], QColor("yellow"))
            item.setForeground(color)
            self._station_list.addItem(item)

    def _on_station_clicked(self, item: QListWidgetItem):
        name = item.data(Qt.ItemDataRole.UserRole)
        self._current_stop_name = name
        self._highlight_station(name)
        for s in self._stations:
            if s["station"] == name:
                self._spin_stop_x.blockSignals(True)
                self._spin_stop_y.blockSignals(True)
                self._spin_stop_x.setValue(int(round(s["x"])))
                self._spin_stop_y.setValue(int(round(s["y"])))
                self._spin_stop_x.blockSignals(False)
                self._spin_stop_y.blockSignals(False)
                break

    def _on_station_from_image(self, name: str, path_id: int, pos_m: float):
        self._highlight_station(name)

    def _on_stop_selected(self, name: str):
        self._current_stop_name = name
        self._highlight_station(name)
        for s in self._stations:
            if s["station"] == name:
                self._spin_stop_x.blockSignals(True)
                self._spin_stop_y.blockSignals(True)
                self._spin_stop_x.setValue(int(round(s["x"])))
                self._spin_stop_y.setValue(int(round(s["y"])))
                self._spin_stop_x.blockSignals(False)
                self._spin_stop_y.blockSignals(False)
                break

    def _on_stop_moved(self, name: str, x: float, y: float):
        # Update internal model and spin boxes only. Do NOT refresh the list or
        # center the view during a drag; those cause UI churn and crashes.
        for s in self._stations:
            if s["station"] == name:
                s["x"] = x
                s["y"] = y
                break
        if self._current_stop_name == name:
            self._spin_stop_x.blockSignals(True)
            self._spin_stop_y.blockSignals(True)
            self._spin_stop_x.setValue(int(round(x)))
            self._spin_stop_y.setValue(int(round(y)))
            self._spin_stop_x.blockSignals(False)
            self._spin_stop_y.blockSignals(False)

    def _on_stop_move_finished(self, name: str):
        # Safe to refresh list now that dragging is done
        self._refresh_station_list(self._station_filter.text())
        self._highlight_station(name, center=False)
        self._lbl_info.setText(f"Placed stop: {name}  ({self._stations[[i for i,s in enumerate(self._stations) if s['station']==name][0]]['x']:.1f}, {self._stations[[i for i,s in enumerate(self._stations) if s['station']==name][0]]['y']:.1f})")

    def _on_stop_spin_changed(self):
        if not getattr(self, "_current_stop_name", None):
            return
        name = self._current_stop_name
        x = float(self._spin_stop_x.value())
        y = float(self._spin_stop_y.value())
        for s in self._stations:
            if s["station"] == name:
                s["x"] = x
                s["y"] = y
                break
        # Move marker without recreating all markers
        for m in getattr(self._view, "_station_markers", []):
            if m.name == name:
                m.setPos(x, y)
                break
        self._refresh_station_list(self._station_filter.text())
        self._view.centerOn(x, y)

    def _highlight_station(self, name: str, center: bool = True):
        # Select in list
        for i in range(self._station_list.count()):
            item = self._station_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                self._station_list.setCurrentItem(item)
                self._station_list.scrollToItem(item)
                break
        # Highlight marker
        for m in getattr(self._view, "_station_markers", []):
            m.set_highlighted(m.name == name)
        # Center view on station
        if center:
            for s in self._stations:
                if s["station"] == name:
                    self._view.centerOn(s["x"], s["y"])
                    break

    def _save_stops(self):
        """Write adjusted stop pixel positions to track_points_adjusted.csv."""
        try:
            out_path = self._csv_path.with_stem(self._csv_path.stem + "_adjusted")
            import csv
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Station", "Command", "Actual", "TrackLocation", "PixelX", "PixelY"])
                # Preserve original command/actual/location for each station
                orig = {r.get("station", "").strip(): r for r in load_csv_points(self._csv_path)}
                for s in self._stations:
                    r = orig.get(s["station"], {})
                    writer.writerow([
                        s["station"],
                        r.get("command", ""),
                        r.get("actual", ""),
                        r.get("location", ""),
                        f"{s['x']:.2f}",
                        f"{s['y']:.2f}",
                    ])
            self._lbl_info.setText(f"Saved adjusted stops to {out_path.name}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _on_added(self, x: float, y: float):
        # Find closest master segment and insert anchor there
        best_idx = 0
        best_dist = float("inf")
        n = len(self._anchors)
        for i in range(n):
            a = self._anchors[i]
            b = self._anchors[(i + 1) % n]
            dx, dy = b[0] - a[0], b[1] - a[1]
            seg_len2 = dx * dx + dy * dy
            if seg_len2 == 0:
                d2 = _dist2((x, y), a)
            else:
                t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / seg_len2))
                proj = (a[0] + t * dx, a[1] + t * dy)
                d2 = _dist2((x, y), proj)
            if d2 < best_dist:
                best_dist = d2
                best_idx = i
        insert_at = (best_idx + 1) % (n + 1)
        self._anchors.insert(insert_at, (x, y))
        # Update indices
        self._junction_indices = [i if i < insert_at else i + 1 for i in self._junction_indices]
        self._current_idx = insert_at
        self._view.set_master(self._anchors, self._junction_indices)
        self._view.highlight(insert_at)
        self._refresh_path_list()
        self._update_info()

    def _delete_selected_anchor(self):
        if self._current_idx is None:
            return
        if self._current_idx in self._junction_indices:
            QMessageBox.information(self, "Cannot Delete", "Junction points cannot be deleted.")
            return
        del self._anchors[self._current_idx]
        self._junction_indices = [i if i < self._current_idx else i - 1 for i in self._junction_indices]
        self._current_idx = None
        self._view.set_master(self._anchors, self._junction_indices)
        self._refresh_path_list()
        self._update_info()

    def _regenerate(self):
        # Just refresh the interpolated view from current anchors
        self._view.set_master(self._anchors, self._junction_indices)
        self._refresh_path_list()
        self._load_stations()
        self._update_info()

    def _reduce_now(self):
        # Build a master polyline from current anchors via linear interpolation
        dense = []
        n = len(self._anchors)
        for i in range(n):
            a = self._anchors[i]
            b = self._anchors[(i + 1) % n]
            dense.append(a)
            # Add intermediate points every few pixels so RDP has a good polyline
            seg_len = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            steps = max(1, int(seg_len / 4.0))
            for k in range(1, steps):
                t = k / steps
                dense.append(_interpolate(a, b, t))
        # Reduce per segment, keeping junctions
        keep = set(self._junction_indices)
        for i in range(len(self._junction_indices)):
            a = self._junction_indices[i]
            b = self._junction_indices[(i + 1) % len(self._junction_indices)]
            if b > a:
                seg = dense[a : b + 1]
            else:
                seg = dense[a:] + dense[: b + 1]
            seg_keep = _rdp(seg, 4.0)
            for k in seg_keep:
                real_idx = (a + k) % len(dense)
                keep.add(real_idx)
        new_anchors = [dense[i] for i in sorted(keep)]
        old_to_new = {old: sorted(keep).index(old) for old in self._junction_indices}
        self._junction_indices = [old_to_new[j] for j in self._junction_indices]
        self._anchors = new_anchors
        self._view.set_master(self._anchors, self._junction_indices)
        self._refresh_path_list()
        self._update_info()

    def _reset_to_loaded(self):
        self._load_all()

    def _spacing_changed(self, v: float):
        self._spacing = v
        self._view.set_master(self._anchors, self._junction_indices)
        self._refresh_path_list()

    def _open_image(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Open Track Image", str(self._img_path.parent),
            "Images (*.png *.jpg *.jpeg)"
        )
        if p:
            self._img_path = Path(p)
            self._view.load_image(self._img_path)
            self._view.set_master(self._anchors, self._junction_indices)
            self._load_stations()
            if self._view.scene():
                self._view.fitInView(self._view.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._lbl_info.setText(f"Opened image: {self._img_path.name}\\nRecompute stops from current path or drag them into place.")

    def _open_py(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Open track_photo.py", str(self._py_path.parent), "Python (*.py)"
        )
        if p:
            self._py_path = Path(p)
            self._load_all()

    def _save(self):
        try:
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            plc = _generate_plc_paths(self._anchors, self._junction_indices, self._spacing, smooth=False)
            backup = HISTORY_DIR / f"waypoints_{_now()}.json"
            with open(backup, "w") as f:
                json.dump({str(k): v for k, v in plc.items()}, f, indent=2)
            save_waypoints(self._py_path, plc)
            total = sum(len(v) for v in plc.values())
            self._lbl_info.setText(
                f"Saved {total} waypoints to {self._py_path.name}\n"
                f"Backup: {backup.name}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _export_json(self):
        p, _ = QFileDialog.getSaveFileName(
            self, "Export Waypoints", str(HISTORY_DIR / "waypoints.json"), "JSON (*.json)"
        )
        if p:
            plc = _generate_plc_paths(self._anchors, self._junction_indices, self._spacing, smooth=False)
            with open(p, "w") as f:
                json.dump({str(k): v for k, v in plc.items()}, f, indent=2)
            self._lbl_info.setText(f"Exported to {Path(p).name}")


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
