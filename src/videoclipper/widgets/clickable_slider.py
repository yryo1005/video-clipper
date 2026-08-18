from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QSlider, QStyle


class ClickableSlider(QSlider):
    """Horizontal slider that seeks on left-click and emits rightClicked."""

    rightClicked = pyqtSignal()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider,
                None,
                QStyle.SubControl.SC_SliderHandle,
                self,
            )
            slider_length = self.width() - handle.width()
            if slider_length > 0:
                ratio = (event.position().x() - handle.width() / 2) / slider_length
                new_value = self.minimum() + ((self.maximum() - self.minimum()) * ratio)
                self.setValue(int(new_value))
                self.sliderMoved.emit(self.value())
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit()
            event.accept()
        super().mousePressEvent(event)
