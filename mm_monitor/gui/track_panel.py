"""Live Track View — renders the real S7000 MagneMover LITE loop geometry and
places each cart at its true (path, position) read live from the PLC.

Geometry comes from track_geometry.build_track() (parsed from TrackFile.mmtrk).
Station markers come from system_data.STATION_LOCATIONS (node_configuration.xml).

Cart motion smoothing: raw PLC samples arrive in discrete jumps (every ~0.75s
live, or once per recorded frame in playback), which reads as clunky/teleporting
on screen. Two independent smoothing paths handle this — see CartAnimator and
interpolate_carts() below:
  - LIVE: dead-reckon each cart forward from its last known (position, velocity)
    using elapsed wall-clock time, so it appears to keep moving at its last
    reported speed between polls. A short blend corrects the display toward the
    truth whenever a new sample disagrees with the prediction.
  - PLAYBACK: both the current and next recorded frame are already known, so
    positions are interpolated exactly between them — no prediction needed.
"""
from __future__ import annotations
import time
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QProgressBar,
)
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QPixmap

from ..plc_reader import SystemSnapshot
from ..system_data import (
    MAX_VEHICLES, MAX_PATHS, STATION_LOCATIONS, path_name, station_name,
    vehicle_alarm_kind, current_operation, PATH_STATES,
)
from ..track_geometry import build_track
from ..track_photo import PHOTO_SIZE, build_photo_track_model, PATH_WAYPOINTS_PX

# Real photo of the physical S7000 track. When present, this replaces the
# auto-generated schematic as the Live Track background (see track_photo.py for
# how station/cart positions are calibrated onto it). If it's missing or fails
# to load for any reason, the canvas falls back to the schematic automatically —
# nothing about live/playback behavior depends on the photo being present.
_PHOTO_PATH = Path(__file__).resolve().parent.parent / "data" / "track_photo.png"


class _ClickBar(QProgressBar):
    """QProgressBar that emits clicked() on left-mouse-press."""
    clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


_MOVING_THRESH = 0.01

# alarm kind → (fill color, short label). "queued" is intentionally NOT here —
# it is normal traffic (waiting behind another unit) and is drawn calmly.
_ALARM_STYLE = {
    "jammed":   ("#e74c3c", "JAMMED"),    # AlarmPresent from HLC
    "hindered": ("#e67e22", "HINDERED"),
    "suspect":  ("#9b59b6", "SUSPECT"),
}

# per-path track line color
_PATH_COLORS = {
    1: "#5b6b8c", 2: "#2980b9", 3: "#7f8c8d",
    4: "#8e44ad", 5: "#5b6b8c", 6: "#16a085",
}
# stations that always get a text label (rest are dots only)
_KEY_STATIONS = {6, 12, 13, 14, 16, 18, 26, 29, 30, 33, 34}


class _Cart:
    __slots__ = ("id", "path", "pos", "vel", "dest", "alarm", "held")

    def __init__(self, cid, path, pos, vel, dest, alarm=None, held=False):
        self.id, self.path, self.pos, self.vel, self.dest = cid, path, pos, vel, dest
        self.alarm = alarm   # None | "jammed" | "hindered" | "alarm" | "suspect"
        # True when this cart isn't in the PLC's current telemetry and we're
        # showing its last known position anyway — see CartPresenceGuard.
        self.held = held


def path_states_from_snapshot(snap: SystemSnapshot) -> dict[int, int]:
    """Extract each path's live MMI_path_status state (INIT/STARTUP/OPERATIONAL/
    RESET/PROGRAMMING) as {path_id: state_value}. Same field lookup as
    path_nc_panel.py's Paths & NCs table, so the color drawn over the photo
    always agrees with what that tab reports."""
    states: dict[int, int] = {}
    for pid in range(1, MAX_PATHS + 1):
        data = snap.path_status[pid] if pid < len(snap.path_status) else None
        if isinstance(data, dict):
            state_val = data.get("state") or data.get("State")
            if state_val is not None:
                states[pid] = int(state_val)
    return states


def carts_from_snapshot(snap: SystemSnapshot) -> list[_Cart]:
    """Extract the active carts (Path_ID != 0) from one PLC snapshot. Shared by
    every consumer (live feed, playback, playback interpolation) so there is one
    place that defines what a cart's raw position/velocity/alarm are."""
    carts = []
    for i in range(1, MAX_VEHICLES + 1):
        vs = snap.vehicle_status[i]
        if not vs or not (vs.get("Path_ID") or 0):
            continue
        alarm = vehicle_alarm_kind(
            snap.vehicle_alarms[i] if i < len(snap.vehicle_alarms) else None)
        carts.append(_Cart(
            cid=i,
            path=vs.get("Path_ID") or 0,
            pos=float(vs.get("Position") or 0.0),
            vel=float(vs.get("Velocity") or 0.0),
            dest=vs.get("Dest_Station_ID") or 0,
            alarm=alarm,
        ))
    return carts


def interpolate_carts(cur: list[_Cart], nxt: list[_Cart] | None, frac: float) -> list[_Cart]:
    """Exact interpolation between two known recorded frames — used during
    playback, where (unlike live) the "future" sample is already on disk, so
    there is no need to predict: just blend straight to the ground truth."""
    if not nxt or frac <= 0.0:
        return cur
    nxt_by_id = {c.id: c for c in nxt}
    out = []
    for c in cur:
        n = nxt_by_id.get(c.id)
        if n is None or n.path != c.path:
            out.append(c)   # cart left, or jumped to a different path — snap, don't smear
        else:
            pos = c.pos + (n.pos - c.pos) * frac
            out.append(_Cart(c.id, c.path, pos, n.vel, n.dest, n.alarm))
    return out


def _operation_active(snap: SystemSnapshot) -> bool:
    """True during Homing (cold start), Cleaning (cleanout), or Recovering —
    the operator-commanded operations where the HLC is known to temporarily
    stop reporting valid Path_ID for physically-present pallets (see
    CartPresenceGuard). Reuses system_data.current_operation's own notion of
    "an operation is active" rather than re-deriving it."""
    return bool(current_operation(snap).get("active"))


class CartPresenceGuard:
    """Keeps a cart visible at its last known position if it drops out of the
    PLC's reported telemetry WHILE Homing or Cleaning is in progress.

    During RESET/STARTUP (cold-start steps 20-60) and during cleanout, the HLC
    genuinely stops reporting a valid Path_ID for pallets it hasn't re-localized
    yet — the vehicle is still physically on the track, but MMI_vehicle_status
    momentarily looks like it isn't there. Without this, those carts would
    blink out of the Live Track for the duration of the operation. This holds
    them at their last confirmed (path, position) until either real telemetry
    for that cart returns, or the operation ends — at which point a cart that
    is genuinely gone (not just mid-operation) is dropped for real.
    """

    def __init__(self):
        self._last_seen: dict[int, _Cart] = {}

    def reset(self):
        self._last_seen.clear()

    def apply(self, raw_carts: list[_Cart], operation_active: bool) -> list[_Cart]:
        seen_ids = {c.id for c in raw_carts}
        for c in raw_carts:
            self._last_seen[c.id] = c
        if not operation_active:
            # Outside an active operation, a missing cart really did leave —
            # trust the PLC and stop remembering it.
            for cid in list(self._last_seen):
                if cid not in seen_ids:
                    del self._last_seen[cid]
            return raw_carts
        held = [
            _Cart(c.id, c.path, c.pos, 0.0, c.dest, c.alarm, held=True)
            for cid, c in self._last_seen.items() if cid not in seen_ids
        ]
        return raw_carts + held


class CartAnimator:
    """Smooths LIVE cart motion between discrete PLC polls.

    Each poll only tells us where a cart WAS at that instant. Rather than snap
    the display to that point and hold it until the next poll (which reads as
    a jerky teleport, worse the slower the poll rate), this dead-reckons the
    cart forward using its last reported velocity — "assume it kept moving the
    way we last saw it moving" — so the display advances continuously between
    polls. When the next real sample arrives, if the reckoned position missed
    (the cart stopped, changed speed, or a poll was slow), the display blends
    to the truth over CORRECTION_SEC instead of jumping.
    """
    CORRECTION_SEC = 0.15
    # Stop extrapolating after this long without a new sample (e.g. the poll
    # thread stalled) so a cart doesn't drift indefinitely off its last fix.
    MAX_EXTRAPOLATE_SEC = 3.0

    def __init__(self):
        self._state: dict[int, dict] = {}   # cart id -> animation state

    def on_live_snapshot(self, raw_carts: list[_Cart], now: float):
        seen = set()
        for rc in raw_carts:
            seen.add(rc.id)
            st = self._state.get(rc.id)
            if st is None or st["path"] != rc.path:
                # New cart, or it's now on a different path (junction/loop
                # transition) — there's no meaningful way to smooth a position
                # across different track geometry, so accept the new value as-is.
                self._state[rc.id] = {
                    "path": rc.path, "dest": rc.dest, "alarm": rc.alarm, "held": rc.held,
                    "basis_pos": rc.pos, "basis_time": now, "basis_vel": rc.vel,
                    "display_pos": rc.pos,
                    "correcting": False, "correct_from": rc.pos, "correct_start": now,
                }
                continue
            predicted = st["basis_pos"] + st["basis_vel"] * (now - st["basis_time"])
            st["dest"], st["alarm"], st["held"] = rc.dest, rc.alarm, rc.held
            if abs(predicted - rc.pos) > 0.03 and not st["correcting"]:
                st["correcting"] = True
                st["correct_from"] = st["display_pos"]
                st["correct_start"] = now
            st["basis_pos"], st["basis_time"], st["basis_vel"] = rc.pos, now, rc.vel
        for cid in list(self._state):
            if cid not in seen:
                del self._state[cid]   # cart no longer tracked — just stop drawing it

    def tick(self, now: float) -> list[_Cart]:
        """Called every animation frame; returns each cart at its current
        smoothed position (dead-reckoned, with any in-progress correction blend)."""
        out = []
        for cid, st in self._state.items():
            dt = min(now - st["basis_time"], self.MAX_EXTRAPOLATE_SEC)
            target = st["basis_pos"] + st["basis_vel"] * dt
            if st["correcting"]:
                t = (now - st["correct_start"]) / self.CORRECTION_SEC
                if t >= 1.0:
                    st["correcting"] = False
                    pos = target
                else:
                    pos = st["correct_from"] + (target - st["correct_from"]) * t
            else:
                pos = target
            st["display_pos"] = pos
            out.append(_Cart(cid, st["path"], pos, st["basis_vel"], st["dest"], st["alarm"],
                             held=st["held"]))
        return out


class TrackCanvas(QWidget):
    _ANIM_INTERVAL_MS = 33   # ~30 fps repaint while a live cart is dead-reckoning

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(420)
        self._carts: list[_Cart] = []      # what paintEvent actually draws
        self._animator = CartAnimator()
        # True while carts are being dead-reckoned from live polls (the anim
        # timer drives paintEvent). False for playback/any caller that already
        # computed the exact position to show — the anim timer is a no-op then.
        self._live_mode = False
        self._show_labels = True
        self._show_path_status = True
        self._path_states: dict[int, int] = {}   # path_id -> MMI_path_status state
        try:
            self._track = build_track()
        except Exception:
            self._track = None

        # Real track photo — the default view when available. Falls back to the
        # schematic automatically (self._photo_pixmap stays None) if the file is
        # missing or fails to decode; nothing else needs to change for that case.
        self._photo_pixmap: QPixmap | None = None
        self._photo_model = None
        try:
            if _PHOTO_PATH.exists():
                pix = QPixmap(str(_PHOTO_PATH))
                if not pix.isNull():
                    self._photo_pixmap = pix
                    self._photo_model = build_photo_track_model()
        except Exception:
            self._photo_pixmap = None
            self._photo_model = None

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(self._ANIM_INTERVAL_MS)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start()

    def feed_live(self, carts: list[_Cart]):
        """A live PLC poll arrived. Hand the true samples to the dead-reckoning
        animator; the animation timer smoothly carries the display toward them
        instead of snapping (see CartAnimator)."""
        self._live_mode = True
        self._animator.on_live_snapshot(carts, time.monotonic())

    def set_carts_exact(self, carts: list[_Cart]):
        """Draw these positions directly, no animation — used for playback
        (which supplies its own frame-to-frame interpolation) and any discrete
        jump (seek/skip) where the exact answer is already known."""
        self._live_mode = False
        self._carts = carts
        self.update()

    def _on_anim_tick(self):
        if not self._live_mode:
            return   # playback/static mode supplies its own frames each call
        self._carts = self._animator.tick(time.monotonic())
        self.update()

    def set_path_states(self, states: dict[int, int]):
        """Live MMI_path_status per path (see path_states_from_snapshot) — drawn
        as a colored line over the photo when show_path_status is on. Not part
        of any animation/smoothing path since a discrete state doesn't need it."""
        self._path_states = states
        self.update()

    def set_show_path_status(self, show: bool):
        self._show_path_status = show
        self.update()

    def set_show_labels(self, show: bool):
        self._show_labels = show
        self.update()

    # ── coordinate transform (track meters → screen px) ─────────────────────
    def _make_transform(self, w: int, h: int):
        minx, miny, maxx, maxy = self._track.bounds
        W, H = max(maxx - minx, 0.1), max(maxy - miny, 0.1)
        m_left, m_right, m_top, m_bot = 30, 30, 56, 30
        s = min((w - m_left - m_right) / W, (h - m_top - m_bot) / H)
        offx = m_left + ((w - m_left - m_right) - W * s) / 2
        offy = m_top + ((h - m_top - m_bot) - H * s) / 2

        def T(x, y):
            return QPointF(offx + (maxx - x) * s, offy + (y - miny) * s)
        return T, s

    # ── photo transform (photo pixel → screen px, uniform scale + letterbox) ──
    def _make_photo_transform(self, w: int, h: int):
        pw, ph = PHOTO_SIZE
        s = min(w / pw, h / ph)
        offx = (w - pw * s) / 2
        offy = (h - ph * s) / 2

        def T(x, y):
            return QPointF(offx + x * s, offy + y * s)
        return T, s, offx, offy

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#f0f4ff"))

        photo_mode = self._photo_pixmap is not None and self._photo_model is not None
        if not photo_mode and self._track is None:
            p.setPen(QColor("#8888aa"))
            p.setFont(QFont("Segoe UI", 12))
            p.drawText(self.rect(), Qt.AlignCenter, "Track geometry unavailable")
            p.end()
            return

        w, h = self.width(), self.height()

        if photo_mode:
            T, scale, offx, offy = self._make_photo_transform(w, h)
            pw, ph = PHOTO_SIZE
            p.drawPixmap(QRectF(offx, offy, pw * scale, ph * scale), self._photo_pixmap,
                        QRectF(0, 0, pw, ph))
            point_at = self._photo_model.point_at

            # ── path status overlay: each path traced in its live MMI_path_status
            # color (INIT/STARTUP/OPERATIONAL/RESET/PROGRAMMING) — the photo has
            # no colored lines of its own, so this is the only way to see path
            # health at a glance without switching to the Paths & NCs tab.
            if self._show_path_status:
                for pid, waypoints in PATH_WAYPOINTS_PX.items():
                    state = self._path_states.get(pid)
                    _label, color = PATH_STATES.get(state, ("", "#9aa5c0"))
                    line_color = QColor(color)
                    line_color.setAlpha(150)
                    poly = QPolygonF([T(x, y) for (x, y) in waypoints])
                    p.setPen(QPen(line_color, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    p.drawPolyline(poly)
        else:
            T, scale = self._make_transform(w, h)
            point_at = self._track.point_at

            # ── track paths (schematic only — the photo IS the track) ────────
            for pid, pg in self._track.paths.items():
                if not pg.abs_pts:
                    continue
                poly = QPolygonF([T(x, y) for (x, y) in pg.abs_pts])
                p.setPen(QPen(QColor(_PATH_COLORS.get(pid, "#556")), 8,
                              Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline(poly)

            # ── junction markers (bridge small closure gaps visually) ────────
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor("#ccccdd")))
            for pid, pg in self._track.paths.items():
                if pg.abs_pts:
                    e = pg.abs_pts[-1]
                    p.drawEllipse(T(e[0], e[1]), 5, 5)

        # ── stations (dots only — labels placed later) ───────────────────────
        station_anchors: list[tuple[QPointF, str]] = []   # (screen_pt, label_text)
        for sid, (pth, loc, name) in STATION_LOCATIONS.items():
            pt = point_at(pth, loc)
            if pt is None:
                continue
            sp = T(pt[0], pt[1])
            is_key = sid in _KEY_STATIONS
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor("#d4a017" if is_key else "#8899aa")))
            r = 4 if is_key else 2.5
            p.drawEllipse(sp, r, r)
            if self._show_labels and is_key:
                station_anchors.append((sp, f"{sid} {name}"))

        # ── carts (body only — labels placed later) ───────────────────────────
        _CART_R = 11
        cart_labels: list[tuple[QPointF, str, str, bool]] = []  # (anchor, text, color, bold)
        for c in self._carts:
            pt = point_at(c.path, c.pos)
            if pt is None:
                continue
            sp = T(pt[0], pt[1])
            self._draw_cart_body(p, sp, c)
            # Collect label for the placement pass. A held cart's velocity is
            # frozen/stale (see CartPresenceGuard), so "assumed position" takes
            # priority over showing a speed or alarm that may no longer be true.
            alarm_style = _ALARM_STYLE.get(c.alarm)
            if c.held:
                cart_labels.append((
                    QPointF(sp.x(), sp.y() + _CART_R),
                    "assumed position", "#8899aa", False))
            elif alarm_style:
                prefix = "!" if c.alarm == "jammed" else "⚠"
                cart_labels.append((
                    QPointF(sp.x(), sp.y() + _CART_R),
                    f"{prefix} {alarm_style[1]}", alarm_style[0], True))
            elif c.alarm == "queued":
                cart_labels.append((
                    QPointF(sp.x(), sp.y() + _CART_R),
                    "queued", "#7777aa", False))
            elif abs(c.vel) > _MOVING_THRESH:
                cart_labels.append((
                    QPointF(sp.x(), sp.y() + _CART_R),
                    f"{c.vel:.2f} m/s", "#1a5a99", False))

        # ── label placement pass (all labels, collision-aware) ────────────────
        all_labels: list[tuple[QPointF, str, str, bool]] = (
            [(a, t, "#333355", False) for a, t in station_anchors] + cart_labels
        )
        self._draw_labels(p, all_labels, w, h)

        # ── legend (bottom) + count (bottom-right) ───────────────────────────
        if photo_mode:
            if self._show_path_status:
                self._draw_path_status_legend(p, 12, h - 20)
            else:
                p.setPen(QColor("#8899aa"))
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(12, h - 12, "Live photo view — station/cart positions calibrated onto the real track.")
        else:
            self._draw_legend(p, 12, h - 20)
        p.setPen(QColor("#1a7a40"))
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        p.drawText(QRectF(0, h - 22, w - 12, 16), Qt.AlignRight,
                   f"{len(self._carts)} carts on track")
        p.end()

    def _draw_cart_body(self, p: QPainter, sp: QPointF, cart: _Cart):
        """Draw the cart square + ID only. Labels are placed separately."""
        r = 11

        if cart.held:
            # Assumed position (PLC isn't currently reporting this cart, but
            # Homing/Cleaning is in progress — see CartPresenceGuard). Drawn
            # muted with a dashed outline so it reads as "last known", not live.
            fill = QColor("#9aa5c0")
            p.setBrush(QBrush(fill))
            pen = QPen(QColor("#5b6b8c"), 2, Qt.DashLine)
            p.setPen(pen)
            p.drawRect(QRectF(sp.x() - r, sp.y() - r, 2 * r, 2 * r))
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.drawText(QRectF(sp.x() - r, sp.y() - r, 2 * r, 2 * r),
                       Qt.AlignCenter, str(cart.id))
            return

        moving = abs(cart.vel) > _MOVING_THRESH
        alarm_style = _ALARM_STYLE.get(cart.alarm)
        fill = QColor(alarm_style[0]) if alarm_style else (
            QColor("#2980b9") if moving else QColor("#27ae60"))

        if alarm_style:
            halo = QColor(fill); halo.setAlpha(60)
            p.setPen(QPen(QColor(alarm_style[0]), 3))
            p.setBrush(QBrush(halo))
            hr = r + 7
            p.drawRect(QRectF(sp.x() - hr, sp.y() - hr, 2 * hr, 2 * hr))
        elif moving:
            trail = QColor(fill); trail.setAlpha(70)
            p.setPen(Qt.NoPen); p.setBrush(QBrush(trail))
            tr = r + 4
            p.drawRect(QRectF(sp.x() - tr, sp.y() - tr, 2 * tr, 2 * tr))

        p.setBrush(QBrush(fill))
        p.setPen(QPen(QColor("#0b1020"), 2))
        p.drawRect(QRectF(sp.x() - r, sp.y() - r, 2 * r, 2 * r))
        p.setPen(QColor("#ffffff"))
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.drawText(QRectF(sp.x() - r, sp.y() - r, 2 * r, 2 * r),
                   Qt.AlignCenter, str(cart.id))

    def _draw_labels(self, p: QPainter,
                     items: list[tuple[QPointF, str, str, bool]],
                     w: int, h: int):
        """Place all labels with collision avoidance.
        Each item: (anchor_pt, text, color, bold).
        anchor_pt is where the leader arrow points (station dot or cart bottom edge).
        When a label is displaced from its default position, a dotted leader line
        and a small arrowhead dot are drawn back to the anchor."""
        LW, LH, PAD = 110, 14, 4

        placed: list[QRectF] = []

        for anchor, text, color, bold in items:
            ax, ay = anchor.x(), anchor.y()
            hw = LW / 2

            # Candidate positions in priority order
            candidates = [
                QRectF(ax - hw,      ay + 4,       LW, LH),   # below (default)
                QRectF(ax - hw,      ay - LH - 4,  LW, LH),   # above
                QRectF(ax + 6,       ay - LH / 2,  LW, LH),   # right
                QRectF(ax - LW - 6,  ay - LH / 2,  LW, LH),   # left
                QRectF(ax - hw,      ay + 20,       LW, LH),   # further below
                QRectF(ax - hw,      ay - LH - 20,  LW, LH),   # further above
                QRectF(ax + 6,       ay + 4,        LW, LH),   # lower-right
                QRectF(ax - LW - 6,  ay + 4,        LW, LH),   # lower-left
                QRectF(ax + 6,       ay - LH - 4,   LW, LH),   # upper-right
                QRectF(ax - LW - 6,  ay - LH - 4,   LW, LH),   # upper-left
            ]

            chosen = None
            for rect in candidates:
                # Discard rects that go off-canvas
                if rect.left() < 2 or rect.right() > w - 2:
                    continue
                if rect.top() < 2 or rect.bottom() > h - 24:   # leave room for legend
                    continue
                expanded = rect.adjusted(-PAD, -PAD, PAD, PAD)
                if not any(expanded.intersects(r.adjusted(-PAD, -PAD, PAD, PAD))
                           for r in placed):
                    chosen = rect
                    break

            if chosen is None:
                chosen = candidates[0]   # fall back; accept overlap rather than no label
            placed.append(chosen)

            default = candidates[0]
            displaced = (abs(chosen.center().x() - default.center().x()) > 2 or
                         abs(chosen.center().y() - default.center().y()) > 2)

            if displaced:
                lc = chosen.center()
                # Dotted leader line from label center to anchor
                pen = QPen(QColor("#9999bb"), 1, Qt.DotLine)
                pen.setDashPattern([2, 3])
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawLine(lc, anchor)
                # Small filled dot at the anchor (arrowhead substitute)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor("#9999bb")))
                p.drawEllipse(anchor, 3, 3)

            p.setFont(QFont("Segoe UI", 7, QFont.Bold if bold else QFont.Normal))
            p.setPen(QColor(color))
            p.setBrush(Qt.NoBrush)
            p.drawText(chosen, Qt.AlignHCenter | Qt.AlignVCenter, text)

    def _draw_legend(self, p: QPainter, x: int, y: int):
        p.setFont(QFont("Segoe UI", 8))
        for pid in sorted(self._track.paths):
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(_PATH_COLORS.get(pid, "#556"))))
            p.drawRect(x, y, 16, 8)
            p.setPen(QColor("#333355"))
            label = f"P{pid} {path_name(pid)}"
            p.drawText(x + 22, y + 8, label)
            x += 22 + p.fontMetrics().horizontalAdvance(label) + 18

    def _draw_path_status_legend(self, p: QPainter, x: int, y: int):
        """Legend for the live path-status colors drawn over the photo (see
        paintEvent's path status overlay) — same states/colors as the Paths &
        NCs tab's table, just shown as a color key instead of text per row."""
        p.setFont(QFont("Segoe UI", 8))
        for state in sorted(PATH_STATES):
            label, color = PATH_STATES[state]
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(color)))
            p.drawRect(x, y, 16, 8)
            p.setPen(QColor("#333355"))
            p.drawText(x + 22, y + 8, label)
            x += 22 + p.fontMetrics().horizontalAdvance(label) + 18


class TrackPanel(QWidget):
    open_system_detail = Signal()   # emitted when the progress bar is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        # Shared between the live feed and playback-tick paths (not used for a
        # discrete seek/skip jump, which should show exactly what's recorded at
        # that instant) — see CartPresenceGuard.
        self._presence_guard = CartPresenceGuard()
        self._build_ui()

    def reset_smoothing(self):
        """Forget all held/animated cart state — call on disconnect so a new
        connection never shows carts left over from a previous session."""
        self._presence_guard.reset()
        self._canvas._animator = CartAnimator()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # ── top row: checkbox + info text ────────────────────────────────────
        bar = QHBoxLayout()
        self._chk_labels = QCheckBox("Show station labels")
        self._chk_labels.setChecked(True)
        self._chk_labels.toggled.connect(lambda v: self._canvas.set_show_labels(v))
        self._chk_path_status = QCheckBox("Show path status")
        self._chk_path_status.setChecked(True)
        self._chk_path_status.setToolTip(
            "Color each path by its live MMI_path_status state "
            "(INIT/STARTUP/OPERATIONAL/RESET/PROGRAMMING)")
        self._chk_path_status.toggled.connect(lambda v: self._canvas.set_show_path_status(v))
        info = QLabel("Live view — Yellow dots = key stations.")
        info.setStyleSheet("color:#8888aa;font-size:9pt;")
        bar.addWidget(self._chk_labels)
        bar.addSpacing(12)
        bar.addWidget(self._chk_path_status)
        bar.addSpacing(12)
        bar.addWidget(info)
        bar.addStretch()
        layout.addLayout(bar)

        # ── homing / cleaning progress bar (click → System detail page) ──────
        self._prog_bar = _ClickBar()
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setValue(100)
        self._prog_bar.setFixedHeight(18)
        self._prog_bar.setCursor(Qt.PointingHandCursor)
        self._prog_bar.setToolTip("Click for full homing / cleaning detail")
        self._prog_bar.clicked.connect(self.open_system_detail)
        self._prog_bar.setFormat("SYSTEM RUNNING  100%")
        self._prog_bar.setTextVisible(True)
        self._prog_bar.setStyleSheet(
            "QProgressBar{background:#e0e3f0;border:1px solid #b0b3d0;"
            "border-radius:4px;text-align:center;font-size:8pt;color:#333355;}"
            "QProgressBar::chunk{background:#27ae60;border-radius:3px;}")
        layout.addWidget(self._prog_bar)

        self._canvas = TrackCanvas()
        layout.addWidget(self._canvas, 1)

    def _update_progress_bar(self, snap: SystemSnapshot):
        op = current_operation(snap)
        pct = int(op["pct"])
        self._prog_bar.setValue(pct)
        label = op["name"] if op["active"] else "SYSTEM RUNNING"
        self._prog_bar.setFormat(f"{label}  {pct}%")
        chunk_color = op["color"] if op["active"] else "#27ae60"
        self._prog_bar.setStyleSheet(
            "QProgressBar{background:#e0e3f0;border:1px solid #b0b3d0;"
            "border-radius:4px;text-align:center;font-size:8pt;color:#333355;}"
            f"QProgressBar::chunk{{background:{chunk_color};border-radius:3px;}}")

    def update(self, snap: SystemSnapshot):
        """Show this snapshot's exact cart positions — no animation. Used for
        playback's discrete jumps (seek/skip/pause) where the exact position is
        already the answer; for live connections, see feed_live_snapshot()."""
        self._update_progress_bar(snap)
        self._canvas.set_carts_exact(carts_from_snapshot(snap))
        self._canvas.set_path_states(path_states_from_snapshot(snap))

    def feed_live_snapshot(self, snap: SystemSnapshot):
        """A fresh poll arrived from the live PLC connection. Feeds the dead-
        reckoning animator so the display keeps moving smoothly between polls
        instead of jumping once per poll (see CartAnimator). Carts the HLC
        temporarily stops reporting during Homing/Cleaning are held at their
        last known position rather than disappearing (see CartPresenceGuard)."""
        self._update_progress_bar(snap)
        raw = carts_from_snapshot(snap)
        guarded = self._presence_guard.apply(raw, _operation_active(snap))
        self._canvas.feed_live(guarded)
        self._canvas.set_path_states(path_states_from_snapshot(snap))

    def update_playback(self, cur_snap: SystemSnapshot,
                        next_snap: SystemSnapshot | None, frac: float):
        """Called every playback tick (not just when the recorded frame index
        advances) with the two frames straddling the playhead, so cart motion
        interpolates smoothly between known, exact recorded positions rather
        than jumping once per recorded frame. Same Homing/Cleaning hold-in-place
        behavior as feed_live_snapshot applies here too, since normal forward
        playback ticking is just as sequential as live polling."""
        self._update_progress_bar(cur_snap)
        cur = self._presence_guard.apply(carts_from_snapshot(cur_snap), _operation_active(cur_snap))
        nxt = carts_from_snapshot(next_snap) if next_snap is not None else None
        self._canvas.set_carts_exact(interpolate_carts(cur, nxt, frac))
        # Path status doesn't need interpolation (it's a discrete state, not a
        # continuous position) — just show whichever frame the playhead is on.
        self._canvas.set_path_states(path_states_from_snapshot(cur_snap))
