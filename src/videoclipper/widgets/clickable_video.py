from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtMultimediaWidgets import QVideoWidget


class ClickableVideoWidget(QVideoWidget):
    """Video surface that reports left-clicks so the window can toggle playback."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
