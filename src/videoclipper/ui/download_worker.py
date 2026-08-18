from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from videoclipper.services.youtube_downloader import DownloadError, YouTubeDownloader


class DownloadWorker(QObject):
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, downloader: YouTubeDownloader, url: str):
        super().__init__()
        self._downloader = downloader
        self._url = url

    def run(self) -> None:
        try:
            path = self._downloader.download(self._url)
            self.succeeded.emit(str(path))
        except DownloadError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))


def start_download(parent, downloader: YouTubeDownloader, url: str, on_ok, on_err) -> tuple[QThread, DownloadWorker]:
    thread = QThread(parent)
    worker = DownloadWorker(downloader, url)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.succeeded.connect(on_ok)
    worker.failed.connect(on_err)
    worker.succeeded.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    return thread, worker
