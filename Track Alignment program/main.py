"""MagneMotion Track Alignment Tool.

A simple, focused editor for dragging track waypoints onto the rail photo.
- Loads track_photo.png and track_photo.py automatically.
- Loads track_points.csv as reference station markers.
- Zoom with mouse wheel, drag with middle/right button.
- Drag points to correct position.
- Save writes the new PATH_WAYPOINTS_PX back to track_photo.py.
- Backups are saved to ../track_path_history/ every time you save.
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
    QAction, QColor, QFont, QIcon, QKeyEvent, QMouseEvent, QPainter,
    QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFormLayout, QGraphicsEllipseItem,
    QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene,
    QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

# ── Paths ──────────────────────────────────────────────────────────────────
# Windows-native absolute paths so the tool works from any launch directory.
PROJECT_DIR = Path(r"C:\AI Projects\MagneMotionMonitor")
DEFAULT_TRACK_PHOTO = Path(r"C:\AI Projects\MagneMotionMonitor\mm_monitor\data\track_photo.png")
DEFAULT_TRACK_PY = Path(r"C:\AI Projects\MagneMotionMonitor\mm_monitor\track_photo.py")
DEFAULT_CSV = Path(__file__).parent / "track_points.csv"
HISTORY_DIR = Path(r"C:\AI Projects\MagneMotionMonitor\track_path_history")

# ── Colors ─────────────────────────────────────────────────────────────────
PATH_COLORS = {
    1: QColor(255, 0, 0),      # red
    2: QColor(0, 120, 255),    # blue
    3: QColor(0, 180, 0),      # green
    4: QColor(160, 0, 220),    # purple
    5: QColor(255, 140, 0),    # orange
    6: QColor(0, 200, 200),    # cyan
}

# Best-guess legend labels for each path ID.  User can correct these later.
PATH_LABELS: dict[int, str] = {
    1: "Right Vertical Loop (Mold 1)",
    2: "Right-to-Top connector",
    3: "Top Main Rail (preload / inspect / test / offload)",
    4: "Top-to-Left connector",
    5: "Left Vertical Loop (Mold 2)",
    6: "Bottom Return Rail (home / cleanout / return)",
}


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_waypoints(path: Path) -> dict[int, list[tuple[float, float]]]:
    """Read PATH_WAYPOINTS_PX from a module file."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("track_photo", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.PATH_WAYPOINTS_PX)


def save_waypoints(path: Path, waypoints: dict[int, list[tuple[float, float]]]) -> None:
    """Replace only the PATH_WAYPOINTS_PX block, preserve everything else."""
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
        for i in range(0, len(pts), 4):
            chunk = pts[i : i + 4]
            lines.append("        " + ", ".join(f"({x}, {y})" for x, y in chunk) + ",")
        lines.append("    ],")
    lines.append("}")

    new_text = text[:start] + "\n".join(lines) + "\n" + text[end:]
    path.write_text(new_text, encoding="utf-8")


def load_csv_points(path: Path) -> list[dict]:
    """Load reference station points from CSV."""
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


# ── Canvas items ───────────────────────────────────────────────────────────
class Handle(QGraphicsEllipseItem):
    """Draggable waypoint handle. Uses plain Python callbacks (not QObject signals)."""

    def __init__(self, path_id: int, idx: int, x: float, y: float, color: QColor):
        super().__init__(-7, -7, 14, 14)
        self.path_id = path_id
        self.idx = idx
        self._color = color
        self.setPos(x, y)
        self.setPen(QPen(Qt.black, 1))
        self.setBrush(color)
        self.setFlags(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(20)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        # Plain Python callbacks assigned by the canvas
        self.on_moved: Callable[[int, int, float, float], None] | None = None
        self.on_selected: Callable[[int, int], None] | None = None
        self.on_deleted: Callable[[int, int], None] | None = None

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
                self.on_moved(self.path_id, self.idx, pos.x(), pos.y())
        return super().itemChange(change, value)

    def mousePressEvent(self, event: QMouseEvent):
        self.setSelected(True)
        if self.on_selected:
            self.on_selected(self.path_id, self.idx)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.on_deleted:
            self.on_deleted(self.path_id, self.idx)

    def set_highlight(self, active: bool):
        self.setPen(QPen(QColor("yellow") if active else Qt.black, 3 if active else 1))
        self.setZValue(30 if active else 20)


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


class TrackView(QGraphicsView):
    """Pannable/zoomable canvas with waypoints and reference markers."""

    point_selected = Signal(int, int)
    point_moved = Signal(int, int, float, float)
    point_added = Signal(int, float, float)
    point_deleted = Signal(int, int)

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
        self._path_lines: dict[int, QGraphicsPathItem] = {}
        self._handles: list[Handle] = []
        self._waypoints: dict[int, list[tuple[float, float]]] = {}
        self._active_path: int | None = None
        self._add_mode = False

    def load_image(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            print(f"ERROR: could not load image {path}")
            return
        self._scene.clear()
        self._path_lines.clear()
        self._handles.clear()
        self._photo = QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self._photo)
        self._scene.setSceneRect(pixmap.rect())

    def add_reference_markers(self, markers: list[tuple[float, float, str]]) -> None:
        for x, y, label in markers:
            self._scene.addItem(ReferenceMarker(x, y, label))

    def set_waypoints(self, waypoints: dict[int, list[tuple[float, float]]]) -> None:
        self._waypoints = waypoints
        self.refresh()

    def refresh(self):
        for item in list(self._scene.items()):
            if isinstance(item, (Handle, QGraphicsPathItem)):
                self._scene.removeItem(item)
        self._path_lines.clear()
        self._handles.clear()
        if not self._photo:
            return

        for pid, pts in self._waypoints.items():
            color = PATH_COLORS.get(pid, QColor("yellow"))
            line = QGraphicsPathItem()
            line.setPen(QPen(color, 2))
            line.setZValue(5)
            self._scene.addItem(line)
            self._path_lines[pid] = line

            for i, (x, y) in enumerate(pts):
                h = Handle(pid, i, x, y, color)
                h.on_moved = self.point_moved.emit
                h.on_selected = self.point_selected.emit
                h.on_deleted = self.point_deleted.emit
                self._scene.addItem(h)
                self._handles.append(h)

        self._redraw_lines()

    def _redraw_lines(self):
        for pid, pts in self._waypoints.items():
            if not pts or pid not in self._path_lines:
                continue
            path = QPainterPath()
            path.moveTo(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                path.lineTo(x, y)
            self._path_lines[pid].setPath(path)

    def update_point(self, path_id: int, idx: int, x: float, y: float) -> None:
        pts = self._waypoints.setdefault(path_id, [])
        if 0 <= idx < len(pts):
            pts[idx] = (x, y)
            self._redraw_lines()

    def add_point(self, path_id: int, x: float, y: float) -> int:
        pts = self._waypoints.setdefault(path_id, [])
        pts.append((x, y))
        self.refresh()
        return len(pts) - 1

    def delete_point(self, path_id: int, idx: int) -> None:
        pts = self._waypoints.get(path_id, [])
        if 0 <= idx < len(pts):
            pts.pop(idx)
            self.refresh()

    def set_active_path(self, path_id: int | None) -> None:
        self._active_path = path_id

    def set_add_mode(self, enabled: bool) -> None:
        self._add_mode = enabled
        self.setDragMode(QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.ScrollHandDrag)

    def highlight(self, path_id: int, idx: int) -> None:
        for h in self._handles:
            h.set_highlight(h.path_id == path_id and h.idx == idx)

    def mousePressEvent(self, event: QMouseEvent):
        if self._add_mode and event.button() == Qt.MouseButton.LeftButton:
            if self._active_path is not None:
                pos = self.mapToScene(event.pos())
                self.point_added.emit(self._active_path, pos.x(), pos.y())
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 0.83
        self.scale(factor, factor)


# ── Main window ────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MagneMotion Track Alignment")
        self.resize(1500, 950)
        self.setWindowIcon(QIcon(str(DEFAULT_TRACK_PHOTO)))

        self._img_path = DEFAULT_TRACK_PHOTO
        self._py_path = DEFAULT_TRACK_PY
        self._csv_path = DEFAULT_CSV
        self._waypoints: dict[int, list[tuple[float, float]]] = {}
        self._current_path: int | None = None
        self._current_idx: int | None = None

        self._build_ui()
        self._build_menu()
        self._load_all()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        # Canvas
        self._view = TrackView()
        self._view.point_selected.connect(self._on_selected)
        self._view.point_moved.connect(self._on_moved)
        self._view.point_added.connect(self._on_added)
        self._view.point_deleted.connect(self._on_deleted)

        # Sidebar
        sidebar = QWidget()
        sidebar.setMaximumWidth(340)
        v = QVBoxLayout(sidebar)
        v.setSpacing(8)

        v.addWidget(QLabel("<b>Paths</b>"))
        self._path_list = QListWidget()
        self._path_list.currentRowChanged.connect(self._on_path_changed)
        v.addWidget(self._path_list)

        hb = QHBoxLayout()
        self._btn_add_path = QPushButton("Add Path")
        self._btn_add_path.clicked.connect(self._add_path)
        self._btn_del_path = QPushButton("Delete Path")
        self._btn_del_path.clicked.connect(self._delete_path)
        hb.addWidget(self._btn_add_path)
        hb.addWidget(self._btn_del_path)
        v.addLayout(hb)

        v.addWidget(QLabel("<b>Selected Point</b>"))
        form = QFormLayout()
        self._spin_x = QSpinBox()
        self._spin_x.setRange(0, 5000)
        self._spin_x.setSingleStep(1)
        self._spin_x.valueChanged.connect(self._on_spin_changed)
        self._spin_y = QSpinBox()
        self._spin_y.setRange(0, 5000)
        self._spin_y.setSingleStep(1)
        self._spin_y.valueChanged.connect(self._on_spin_changed)
        form.addRow("X:", self._spin_x)
        form.addRow("Y:", self._spin_y)
        v.addLayout(form)

        self._btn_del_point = QPushButton("Delete Selected Point")
        self._btn_del_point.clicked.connect(self._delete_selected_point)
        v.addWidget(self._btn_del_point)

        self._chk_add = QCheckBox("Add Point Mode (click on image)")
        self._chk_add.stateChanged.connect(lambda s: self._view.set_add_mode(s == Qt.CheckState.Checked.value))
        v.addWidget(self._chk_add)

        v.addSpacing(10)
        self._lbl_info = QLabel("Ready")
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet("background: #f0f0f0; padding: 6px; border: 1px solid #ccc;")
        v.addWidget(self._lbl_info)

        v.addStretch()

        self._btn_save = QPushButton("Save to track_photo.py")
        self._btn_save.setStyleSheet("background: #2980b9; color: white; font-weight: bold; padding: 8px;")
        self._btn_save.clicked.connect(self._save)
        v.addWidget(self._btn_save)

        self._btn_export = QPushButton("Export waypoints to JSON...")
        self._btn_export.clicked.connect(self._export_json)
        v.addWidget(self._btn_export)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._view)
        splitter.addWidget(sidebar)
        splitter.setSizes([1150, 300])
        layout.addWidget(splitter)

    def _build_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("File")
        fm.addAction("Open Track Image...", self._open_image)
        fm.addAction("Open track_photo.py...", self._open_py)
        fm.addAction("Reload", self._load_all)
        fm.addSeparator()
        fm.addAction("Save", self._save, "Ctrl+S")
        hm = mb.addMenu("Help")
        hm.addAction("Path Legend", self._show_legend)

    def _load_all(self):
        errors = []
        if not self._img_path.exists():
            errors.append(f"Image not found: {self._img_path}")
        if not self._py_path.exists():
            errors.append(f"Waypoints file not found: {self._py_path}")

        if errors:
            self._lbl_info.setText("\n".join(errors) + "\n\nUse File > Open to select correct files.")
            QMessageBox.critical(self, "Load Error", "\n".join(errors))
            return

        try:
            self._waypoints = load_waypoints(self._py_path)
        except Exception as e:
            self._lbl_info.setText(f"Failed to load waypoints:\n{e}")
            QMessageBox.critical(self, "Load Error", f"Could not read {self._py_path}:\n{e}")
            return

        self._view.load_image(self._img_path)
        self._view.set_waypoints(self._waypoints)

        csv_points = load_csv_points(self._csv_path)
        self._lbl_info.setText(
            f"Loaded: {self._py_path.name}\n"
            f"Image: {self._img_path.name}\n"
            f"CSV: {self._csv_path.name} ({len(csv_points)} stations)\n"
            f"Paths: {len(self._waypoints)}\n"
            f"Total points: {sum(len(v) for v in self._waypoints.values())}\n\n"
            f"Zoom: mouse wheel\n"
            f"Pan: middle/right drag\n"
            f"Select/drag point: left click\n"
            f"Add point: enable Add Point Mode\n"
            f"Delete point: double-click or button"
        )

        self._refresh_path_list()
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
        for pid in sorted(self._waypoints.keys()):
            label = PATH_LABELS.get(pid, "")
            text = f"Path {pid}  ({len(self._waypoints[pid])} points)"
            if label:
                text += f" — {label}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, pid)
            item.setToolTip(f"Best-guess: {label}" if label else f"Path {pid}")
            color = PATH_COLORS.get(pid, QColor("yellow"))
            item.setForeground(color)
            self._path_list.addItem(item)
        if self._path_list.count():
            self._path_list.setCurrentRow(0)

    def _on_path_changed(self, row: int):
        item = self._path_list.item(row)
        if item:
            self._current_path = item.data(Qt.ItemDataRole.UserRole)
            self._view.set_active_path(self._current_path)
            self._chk_add.setChecked(False)
            label = PATH_LABELS.get(self._current_path, "")
            if label:
                self._lbl_info.setText(f"Selected Path {self._current_path}: {label}\n\n{self._lbl_info.text()}")

    def _show_legend(self):
        lines = ["<b>Path Legend (best guess)</b><br>"]
        for pid in sorted(PATH_LABELS.keys()):
            color = PATH_COLORS.get(pid, QColor("yellow")).name()
            lines.append(f"<span style='color:{color};'>●</span> Path {pid}: {PATH_LABELS[pid]}<br>")
        lines.append("<br>Verify against the actual track photo and correct as needed.")
        QMessageBox.information(self, "Track Path Legend", "".join(lines))

    def _on_selected(self, path_id: int, idx: int):
        self._current_path = path_id
        self._current_idx = idx
        self._view.highlight(path_id, idx)
        x, y = self._waypoints[path_id][idx]
        self._spin_x.blockSignals(True)
        self._spin_y.blockSignals(True)
        self._spin_x.setValue(int(round(x)))
        self._spin_y.setValue(int(round(y)))
        self._spin_x.blockSignals(False)
        self._spin_y.blockSignals(False)
        self._lbl_info.setText(f"Path {path_id}, point {idx}: ({x:.1f}, {y:.1f})")

    def _on_moved(self, path_id: int, idx: int, x: float, y: float):
        self._waypoints[path_id][idx] = (x, y)
        self._view.update_point(path_id, idx, x, y)
        if self._current_path == path_id and self._current_idx == idx:
            self._spin_x.blockSignals(True)
            self._spin_y.blockSignals(True)
            self._spin_x.setValue(int(round(x)))
            self._spin_y.setValue(int(round(y)))
            self._spin_x.blockSignals(False)
            self._spin_y.blockSignals(False)
            self._lbl_info.setText(f"Path {path_id}, point {idx}: ({x:.1f}, {y:.1f})")

    def _on_spin_changed(self):
        if self._current_path is None or self._current_idx is None:
            return
        x = float(self._spin_x.value())
        y = float(self._spin_y.value())
        self._waypoints[self._current_path][self._current_idx] = (x, y)
        self._view.update_point(self._current_path, self._current_idx, x, y)
        self._view.refresh()

    def _on_added(self, path_id: int, x: float, y: float):
        self._waypoints[path_id].append((x, y))
        self._view.set_waypoints(self._waypoints)
        new_idx = len(self._waypoints[path_id]) - 1
        self._view.highlight(path_id, new_idx)
        self._refresh_path_list()
        self._lbl_info.setText(f"Added point {new_idx} to Path {path_id}")

    def _on_deleted(self, path_id: int, idx: int):
        self._waypoints[path_id].pop(idx)
        self._view.set_waypoints(self._waypoints)
        self._refresh_path_list()
        self._lbl_info.setText(f"Deleted point {idx} from Path {path_id}")

    def _delete_selected_point(self):
        if self._current_path is not None and self._current_idx is not None:
            self._on_deleted(self._current_path, self._current_idx)

    def _add_path(self):
        new_pid = max(self._waypoints.keys(), default=0) + 1
        self._waypoints[new_pid] = []
        self._refresh_path_list()
        for i in range(self._path_list.count()):
            if self._path_list.item(i).data(Qt.ItemDataRole.UserRole) == new_pid:
                self._path_list.setCurrentRow(i)
                break
        self._lbl_info.setText(f"Added Path {new_pid}")

    def _delete_path(self):
        if self._current_path is None:
            return
        reply = QMessageBox.question(
            self, "Delete Path",
            f"Delete Path {self._current_path} and all its points?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            del self._waypoints[self._current_path]
            self._view.set_waypoints(self._waypoints)
            self._refresh_path_list()

    def _open_image(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Open Track Image", str(self._img_path.parent),
            "Images (*.png *.jpg *.jpeg)"
        )
        if p:
            self._img_path = Path(p)
            self._view.load_image(self._img_path)
            self._view.set_waypoints(self._waypoints)

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
            backup = HISTORY_DIR / f"waypoints_{_now()}.json"
            with open(backup, "w") as f:
                json.dump({str(k): v for k, v in self._waypoints.items()}, f, indent=2)
            save_waypoints(self._py_path, self._waypoints)
            total = sum(len(v) for v in self._waypoints.values())
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
            with open(p, "w") as f:
                json.dump({str(k): v for k, v in self._waypoints.items()}, f, indent=2)
            self._lbl_info.setText(f"Exported to {Path(p).name}")


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
