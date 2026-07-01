import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from mm_monitor import crash_handler
from mm_monitor.system_data import APP_VERSION


def _resource_path(*parts) -> Path:
    """Resolve a bundled resource both when running from source and when
    frozen by PyInstaller (sys._MEIPASS is the onefile extraction root)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MagneMotion Monitor")

    # Window/taskbar icon while running — separate from the .exe file's own
    # icon (set via MagneMotionMonitor.spec's icon= param at build time).
    icon_path = _resource_path("assets", "app_icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Install global crash capture BEFORE building any UI.
    crash_handler.install(APP_VERSION)

    from mm_monitor.gui.main_window import MainWindow
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
