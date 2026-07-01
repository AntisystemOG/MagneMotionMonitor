STYLESHEET = """
QMainWindow, QDialog {
    background-color: #f0f2f8;
}
QWidget {
    background-color: #f0f2f8;
    color: #1a1a2e;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}
QSplitter::handle {
    background-color: #b0b3d0;
}
QSplitter::handle:horizontal { width: 2px; }
QSplitter::handle:vertical   { height: 2px; }
QLineEdit {
    background-color: #ffffff;
    border: 1px solid #aaaacc;
    border-radius: 4px;
    padding: 4px 8px;
    color: #1a1a2e;
    font-family: "Consolas", monospace;
    font-size: 10pt;
}
QLineEdit:focus { border-color: #e94560; }
QPushButton {
    background-color: #c5cae9;
    color: #1a1a2e;
    border: 1px solid #9999bb;
    border-radius: 4px;
    padding: 5px 16px;
    font-size: 10pt;
    min-width: 80px;
}
QPushButton:hover  { background-color: #a7aed4; border-color: #6666aa; }
QPushButton:pressed { background-color: #e94560; color: #fff; }
QPushButton:disabled { color: #999999; background-color: #e0e0e0; }
QPushButton[connected="true"] {
    background-color: #ffcccc;
    border-color: #c0392b;
    color: #7b0000;
}
QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f0f2f8;
    gridline-color: #ccccdd;
    border: 1px solid #b0b3d0;
    font-family: "Consolas", monospace;
    font-size: 9pt;
    color: #1a1a2e;
}
QTableWidget::item:selected { background-color: #c5cae9; color: #1a1a2e; }
QHeaderView::section {
    background-color: #c5cae9;
    color: #333366;
    padding: 5px;
    border: 1px solid #b0b3d0;
    font-weight: bold;
    font-size: 9pt;
}
QScrollBar:vertical { background-color: #e8eaf6; width: 10px; }
QScrollBar::handle:vertical { background-color: #9999bb; border-radius: 5px; min-height: 20px; }
QScrollBar:horizontal { background-color: #e8eaf6; height: 10px; }
QScrollBar::handle:horizontal { background-color: #9999bb; border-radius: 5px; min-width: 20px; }
QProgressBar {
    background-color: #e0e3f0;
    border: 1px solid #aaaacc;
    border-radius: 4px;
    text-align: center;
    color: #1a1a2e;
    font-weight: bold;
    font-size: 10pt;
    height: 24px;
}
QProgressBar::chunk { background-color: #27ae60; border-radius: 3px; }
QLabel { background-color: transparent; }
QGroupBox {
    border: 1px solid #b0b3d0;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 6px;
    font-weight: bold;
    color: #555588;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QSpinBox, QComboBox {
    background-color: #ffffff;
    border: 1px solid #aaaacc;
    border-radius: 4px;
    padding: 3px 6px;
    color: #1a1a2e;
    min-width: 60px;
}
QTextEdit {
    background-color: #ffffff;
    border: 1px solid #aaaacc;
    color: #1a1a2e;
    font-family: "Consolas", monospace;
    font-size: 9pt;
}
QMenuBar { background-color: #e0e3f0; color: #1a1a2e; border-bottom: 1px solid #b0b3d0; }
QMenuBar::item:selected { background-color: #c5cae9; }
QMenu { background-color: #f0f2f8; border: 1px solid #b0b3d0; }
QMenu::item:selected { background-color: #c5cae9; }
QStatusBar { background-color: #e0e3f0; color: #555577; border-top: 1px solid #b0b3d0; font-size: 9pt; }
"""
