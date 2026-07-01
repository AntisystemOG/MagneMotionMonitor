"""Global crash capture: writes a crash log and shows a copyable popup.

Catches:
  - unhandled exceptions on the main thread (sys.excepthook)
  - unhandled exceptions on worker threads (threading.excepthook)
  - exceptions inside a guarded block (report_context, called from except:)
  - recent Qt/C++ warnings (qInstallMessageHandler) are attached to every report,
    which helps diagnose hard Qt crashes that Python itself cannot catch.

Crash logs: %APPDATA%\\MagneMotionMonitor\\crash_logs\\crash_YYYYMMDD_HHMMSS.log
"""
from __future__ import annotations
import os
import sys
import platform
import threading
import traceback
import faulthandler
from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Qt, qInstallMessageHandler
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
)
from PySide6.QtGui import QFont

CRASH_DIR = Path(os.environ.get("APPDATA", Path.home())) / "MagneMotionMonitor" / "crash_logs"

_qt_messages: "deque[str]" = deque(maxlen=60)
_app_version = "?"
_fault_file = None   # keep the faulthandler log file open for the process lifetime


class _CrashBridge(QObject):
    """Marshals a crash from any thread onto the GUI thread to show the dialog."""
    crashed = Signal(str, str)  # short_msg, full_details


_bridge = _CrashBridge()


# ── Qt message capture ───────────────────────────────────────────────────────

def _qt_message_handler(mode, context, message):
    try:
        _qt_messages.append(f"[Qt] {message}")
        sys.__stderr__.write(str(message) + "\n")
    except Exception:
        pass


# ── formatting & writing ─────────────────────────────────────────────────────

def _format(exc_type, exc_value, exc_tb, thread_name=None, context="") -> str:
    parts = [
        "================ MagneMotion Monitor — Crash Report ================",
        f"Time:    {datetime.now().isoformat(timespec='seconds')}",
        f"Version: {_app_version}",
        f"Python:  {platform.python_version()}",
        f"OS:      {platform.platform()}",
    ]
    if thread_name:
        parts.append(f"Thread:  {thread_name}")
    if context:
        parts.append(f"Context: {context}")
    parts.append("")
    parts.append("---- Traceback ----")
    parts.append("".join(traceback.format_exception(exc_type, exc_value, exc_tb)).rstrip())
    if _qt_messages:
        parts.append("")
        parts.append("---- Recent Qt messages (newest last) ----")
        parts.extend(_qt_messages)
    parts.append("===================================================================")
    return "\n".join(parts)


def _write_log(details: str) -> Path | None:
    try:
        CRASH_DIR.mkdir(parents=True, exist_ok=True)
        path = CRASH_DIR / f"crash_{datetime.now():%Y%m%d_%H%M%S}.log"
        path.write_text(details, encoding="utf-8")
        return path
    except Exception:
        return None


def _report(exc_type, exc_value, exc_tb, thread_name=None, context=""):
    details = _format(exc_type, exc_value, exc_tb, thread_name, context)
    path = _write_log(details)
    if path:
        details += f"\n\nLog saved to:\n{path}"
    short = f"{getattr(exc_type, '__name__', exc_type)}: {exc_value}"
    try:
        sys.__stderr__.write(details + "\n")
    except Exception:
        pass
    try:
        _bridge.crashed.emit(short, details)
    except Exception:
        pass


# ── hooks ────────────────────────────────────────────────────────────────────

def _sys_excepthook(exc_type, exc_value, exc_tb):
    _report(exc_type, exc_value, exc_tb, thread_name="MainThread")


def _thread_excepthook(args):
    _report(args.exc_type, args.exc_value, args.exc_traceback,
            thread_name=getattr(args.thread, "name", "?"))


def report_context(context: str):
    """Call from inside an `except:` block to log+popup the current exception
    without letting it propagate (keeps the app alive)."""
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type is not None:
        _report(exc_type, exc_value, exc_tb,
                thread_name=threading.current_thread().name, context=context)


def install(version: str = "?"):
    global _app_version, _fault_file
    _app_version = version
    sys.excepthook = _sys_excepthook
    try:
        threading.excepthook = _thread_excepthook  # py3.8+
    except Exception:
        pass
    qInstallMessageHandler(_qt_message_handler)
    _bridge.crashed.connect(_show_dialog, Qt.QueuedConnection)
    # faulthandler dumps a native C-level traceback on a hard crash (segfault /
    # Qt abort) that Python's excepthook cannot catch — our best evidence for
    # those silent crashes.
    try:
        CRASH_DIR.mkdir(parents=True, exist_ok=True)
        _fault_file = open(CRASH_DIR / "faulthandler.log", "a", buffering=1)
        _fault_file.write(f"\n===== session start {datetime.now().isoformat(timespec='seconds')} "
                          f"v{version} =====\n")
        faulthandler.enable(file=_fault_file, all_threads=True)
    except Exception:
        pass


# ── dialog ───────────────────────────────────────────────────────────────────

_dialog_open = False


def _show_dialog(short_msg: str, details: str):
    global _dialog_open
    if QApplication.instance() is None or _dialog_open:
        return
    _dialog_open = True
    try:
        CrashDialog(short_msg, details).exec()
    finally:
        _dialog_open = False


class CrashDialog(QDialog):
    def __init__(self, short_msg: str, details: str, parent=None):
        super().__init__(parent)
        self._details = details
        self.setWindowTitle("MagneMotion Monitor — Error")
        self.setMinimumSize(720, 480)
        self.setStyleSheet(
            "QDialog { background:#f0f2f8; } QLabel { color:#1a1a2e; }"
        )

        layout = QVBoxLayout(self)

        header = QLabel("⚠  An error occurred")
        header.setStyleSheet("color:#c0392b; font-size:15pt; font-weight:bold;")
        layout.addWidget(header)

        msg = QLabel(short_msg)
        msg.setWordWrap(True)
        msg.setStyleSheet("color:#841825; font-size:10pt;")
        layout.addWidget(msg)

        hint = QLabel("Copy this report and send it to diagnose the issue. "
                      "The app has stayed open if it was able to recover.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555577; font-size:9pt;")
        layout.addWidget(hint)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setPlainText(details)
        self._text.setFont(QFont("Consolas", 9))
        self._text.setStyleSheet(
            "background:#ffffff; color:#1a1a2e; border:1px solid #b0b3d0;"
        )
        layout.addWidget(self._text, 1)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("📋  Copy to Clipboard")
        btn_folder = QPushButton("📁  Open Log Folder")
        btn_close = QPushButton("Close")
        btn_copy.clicked.connect(self._copy)
        btn_folder.clicked.connect(self._open_folder)
        btn_close.clicked.connect(self.accept)
        for b in (btn_copy, btn_folder):
            b.setStyleSheet(
                "QPushButton{background:#c5cae9;color:#1a1a2e;border:1px solid #9999bb;"
                "border-radius:4px;padding:6px 14px;} QPushButton:hover{background:#a7aed4;}"
            )
        btn_close.setStyleSheet(
            "QPushButton{background:#ffcccc;color:#7b0000;border:1px solid #c0392b;"
            "border-radius:4px;padding:6px 14px;} QPushButton:hover{background:#ffb3b3;}"
        )
        self._btn_copy = btn_copy
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_folder)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _copy(self):
        QApplication.clipboard().setText(self._details)
        self._btn_copy.setText("✓  Copied!")

    def _open_folder(self):
        try:
            CRASH_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(CRASH_DIR))  # noqa: S606 (Windows-only, intended)
        except Exception:
            pass
