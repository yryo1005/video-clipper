from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from videoclipper.services.waveform import get_waveform


class WaveformWorker(QObject):
    finished = pyqtSignal(str, list)

    def __init__(self, video_path: Path, cache_dir: Path):
        super().__init__()
        self._video_path = video_path
        self._cache_dir = cache_dir

    def run(self) -> None:
        try:
            peaks = get_waveform(self._video_path, self._cache_dir)
        except Exception:
            peaks = None
        self.finished.emit(str(self._video_path), peaks or [])


def start_waveform(parent, video_path: Path, cache_dir: Path, on_ready) -> tuple[QThread, WaveformWorker]:
    thread = QThread(parent)
    worker = WaveformWorker(video_path, cache_dir)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(on_ready)
    worker.finished.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    return thread, worker
