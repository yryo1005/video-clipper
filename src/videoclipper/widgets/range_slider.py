from __future__ import annotations

from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PyQt6.QtWidgets import QWidget

_HANDLE_WIDTH = 10
_TRACK_HEIGHT = 6


class RangeSlider(QWidget):
    """A single track showing a waveform with a highlighted Start/End range.

    Left-click anywhere on the track requests Start be set to the current
    playback position (see MainWindow's Current bar); right-click requests
    End the same way. The clicked x-position is not used for the value -
    only which button was pressed.
    """

    startRequested = pyqtSignal()
    endRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 1000
        self._start = 0
        self._end = 1000
        self._playhead: int | None = None
        self._peaks: list[float] = []
        self.setFixedHeight(56)
        self.setMouseTracking(True)

    def setWaveform(self, peaks: list[float]) -> None:
        self._peaks = peaks
        self.update()

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = minimum
        self._maximum = max(maximum, minimum + 1)
        self._start = max(self._minimum, min(self._start, self._maximum))
        self._end = max(self._minimum, min(self._end, self._maximum))
        self.update()

    def setStart(self, value: int) -> None:
        self._start = max(self._minimum, min(value, self._end))
        self.update()

    def setEnd(self, value: int) -> None:
        self._end = min(self._maximum, max(value, self._start))
        self.update()

    def start(self) -> int:
        return self._start

    def end(self) -> int:
        return self._end

    def setPlayhead(self, value: int) -> None:
        self._playhead = value
        self.update()

    def _value_to_x(self, value: int) -> int:
        span = self._maximum - self._minimum
        usable = max(self.width() - _HANDLE_WIDTH, 1)
        ratio = (value - self._minimum) / span if span else 0
        return int(_HANDLE_WIDTH / 2 + ratio * usable)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.startRequested.emit()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.endRequested.emit()
            event.accept()
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track_y = self.height() // 2 - _TRACK_HEIGHT // 2
        track_rect = QRect(_HANDLE_WIDTH // 2, track_y, self.width() - _HANDLE_WIDTH, _TRACK_HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#3a3a3a"))
        painter.drawRoundedRect(track_rect, 3, 3)

        if self._peaks:
            self._draw_waveform(painter)

        start_x = self._value_to_x(self._start)
        end_x = self._value_to_x(self._end)
        selected_rect = QRect(start_x, 2, max(end_x - start_x, 0), self.height() - 4)
        painter.setBrush(QColor(76, 175, 80, 60 if self._peaks else 140))
        painter.drawRect(selected_rect)

        if self._playhead is not None:
            px = self._value_to_x(self._playhead)
            painter.setPen(QColor(220, 220, 220, 200))
            painter.drawLine(px, 2, px, self.height() - 2)

        painter.setPen(Qt.PenStyle.NoPen)
        handle_rect = QRect(start_x - _HANDLE_WIDTH // 2, 2, _HANDLE_WIDTH, self.height() - 4)
        painter.setBrush(QColor("#4CAF50"))
        painter.drawRoundedRect(handle_rect, 3, 3)

        handle_rect = QRect(end_x - _HANDLE_WIDTH // 2, 2, _HANDLE_WIDTH, self.height() - 4)
        painter.setBrush(QColor("#F44336"))
        painter.drawRoundedRect(handle_rect, 3, 3)

    def _draw_waveform(self, painter: QPainter) -> None:
        usable = max(self.width() - _HANDLE_WIDTH, 1)
        center_y = self.height() // 2
        max_bar_half_height = self.height() // 2 - 4
        count = len(self._peaks)
        bar_width = max(1.0, usable / count)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(120, 170, 220, 130))
        for i, peak in enumerate(self._peaks):
            x = _HANDLE_WIDTH / 2 + i * bar_width
            half_height = max(1, int(peak * max_bar_half_height))
            painter.drawRect(QRect(int(x), center_y - half_height, max(1, int(bar_width) + 1), half_height * 2))
