import sys
from PySide6.QtWidgets import QApplication

from mm_monitor import crash_handler
from mm_monitor.system_data import APP_VERSION


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MagneMotion Monitor")

    # Install global crash capture BEFORE building any UI.
    crash_handler.install(APP_VERSION)

    from mm_monitor.gui.main_window import MainWindow
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
