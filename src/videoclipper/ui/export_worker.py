from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from videoclipper.services.clip_exporter import ClipExporter, ExportError


class ExportWorker(QObject):
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)
    progress = pyqtSignal(float)

    def __init__(self, exporter: ClipExporter, source: Path, start_sec: str, end_sec: str, destination: Path):
        super().__init__()
        self._exporter = exporter
        self._source = source
        self._start_sec = start_sec
        self._end_sec = end_sec
        self._destination = destination

    def run(self) -> None:
        try:
            path = self._exporter.export(
                self._source,
                self._start_sec,
                self._end_sec,
                self._destination,
                progress_callback=self.progress.emit,
            )
            self.succeeded.emit(str(path))
        except ExportError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))


def start_export(
    parent,
    exporter: ClipExporter,
    source: Path,
    start_sec: str,
    end_sec: str,
    destination: Path,
    on_ok,
    on_err,
    on_progress=None,
) -> tuple[QThread, ExportWorker]:
    thread = QThread(parent)
    worker = ExportWorker(exporter, source, start_sec, end_sec, destination)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.succeeded.connect(on_ok)
    worker.failed.connect(on_err)
    if on_progress:
        worker.progress.connect(on_progress)
    worker.succeeded.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    return thread, worker
