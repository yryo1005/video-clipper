from __future__ import annotations

import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from videoclipper.config import BASE_FONT_SIZE, WINDOW_TITLE
from videoclipper.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("VideoClipper")
    app.setApplicationDisplayName(WINDOW_TITLE)
    app.setFont(QFont("Arial", BASE_FONT_SIZE))
    window = MainWindow()
    window.showMaximized()
    return app.exec()
