from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QKeyEvent
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from videoclipper.config import (
    END_PREVIEW_OFFSET_SEC,
    WINDOW_TITLE,
    clips_dir,
    downloads_dir,
    settings_file,
)
from videoclipper.services.clip_exporter import ClipExporter, ExportError
from videoclipper.services.clip_library import ClipLibrary
from videoclipper.services.settings_store import SettingsStore
from videoclipper.services.youtube_downloader import YouTubeDownloader
from videoclipper.ui.download_worker import start_download
from videoclipper.widgets.clickable_slider import ClickableSlider
from videoclipper.widgets.clickable_video import ClickableVideoWidget


def _format_clock(seconds: float) -> str:
    minutes = int(seconds) // 60
    return f"{minutes:02}:{seconds % 60:04.1f}"


def _safe_clip_stem(name: str) -> str:
    cleaned = name.strip()
    for char in '<>:"/\\|?*':
        cleaned = cleaned.replace(char, "_")
    return cleaned


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.end_preview_offset = END_PREVIEW_OFFSET_SEC
        self.input_path = ""
        self._download_thread = None
        self._download_worker = None

        self.settings = SettingsStore(settings_file())
        self.library = ClipLibrary(clips_dir())
        self.exporter = ClipExporter()
        self.downloader = YouTubeDownloader(downloads_dir())

        self._build_player()
        self._build_ui()
        self.refresh_clip_list()
        self._restore_volume()

    def _build_player(self) -> None:
        self.video_widget = ClickableVideoWidget()
        self.video_widget.setStyleSheet("background-color: black;")
        self.video_widget.clicked.connect(self.toggle_playback)

        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        left = QVBoxLayout()
        controls = QVBoxLayout()

        self.timeline_scale = QHBoxLayout()
        self.scale_labels = []
        for _ in range(11):
            label = QLabel("")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 11px;")
            self.timeline_scale.addWidget(label)
            self.scale_labels.append(label)
        controls.addLayout(self.timeline_scale)

        bars_and_volume = QHBoxLayout()
        bars = QVBoxLayout()

        curr_row = QHBoxLayout()
        self.curr_highlight = QLabel("Current: 0.0s")
        self.curr_highlight.setStyleSheet("color: white; font-weight: bold;")
        curr_row.addWidget(self.curr_highlight)
        curr_row.addStretch()
        self.time_display = QLabel("00:00.0 / 00:00.0")
        curr_row.addWidget(self.time_display)

        self.slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.sliderMoved.connect(self._seek)

        bars.addLayout(curr_row)
        bars.addWidget(self.slider)

        self.start_highlight = QLabel("Start: 0.0s")
        self.start_highlight.setStyleSheet("color: #4CAF50;")
        self.start_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.start_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.start_slider.setStyleSheet(
            "QSlider::handle:horizontal { background-color: #4CAF50; width: 25px; height: 25px; }"
        )
        self.start_slider.sliderMoved.connect(self._set_start_from_slider)
        self.start_slider.rightClicked.connect(self._sync_start_to_current)

        self.end_highlight = QLabel("End: 0.0s")
        self.end_highlight.setStyleSheet("color: #F44336;")
        self.end_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.end_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.end_slider.setStyleSheet(
            "QSlider::handle:horizontal { background-color: #F44336; width: 25px; height: 25px; }"
        )
        self.end_slider.sliderMoved.connect(self._set_end_from_slider)
        self.end_slider.rightClicked.connect(self._sync_end_to_current)

        bars.addWidget(self.start_highlight)
        bars.addWidget(self.start_slider)
        bars.addWidget(self.end_highlight)
        bars.addWidget(self.end_slider)

        volume_box = QVBoxLayout()
        self.vol_icon = QLabel("🔊")
        self.vol_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vol_slider = QSlider(Qt.Orientation.Vertical)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(50)
        self.vol_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol_slider.valueChanged.connect(self._set_volume)
        self.vol_label = QLabel("50%")
        self.vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        volume_box.addWidget(self.vol_icon)
        volume_box.addWidget(self.vol_slider)
        volume_box.addWidget(self.vol_label)

        bars_and_volume.addLayout(bars, 1)
        bars_and_volume.addLayout(volume_box)
        controls.addLayout(bars_and_volume)

        settings = QVBoxLayout()
        input_row = QHBoxLayout()

        btn_open = QPushButton("📁 Open")
        btn_open.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_open.clicked.connect(self._open_file)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("YouTube URL...")
        btn_download = QPushButton("⬇ Download")
        btn_download.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_download.clicked.connect(self._download_video)

        self.start_input = QLineEdit("0.0")
        self.start_input.setFixedWidth(60)
        self.end_input = QLineEdit("0.0")
        self.end_input.setFixedWidth(60)

        input_row.addWidget(btn_open)
        input_row.addWidget(self.url_input, 1)
        input_row.addWidget(btn_download)
        input_row.addWidget(QLabel("S:"))
        input_row.addWidget(self.start_input)
        input_row.addWidget(QLabel("E:"))
        input_row.addWidget(self.end_input)
        input_row.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Clip name...")
        input_row.addWidget(self.name_input, 1)

        self.btn_cut = QPushButton("✨ EXPORT")
        self.btn_cut.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_cut.setMinimumWidth(100)
        self.btn_cut.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.btn_cut.clicked.connect(self._cut_video)
        input_row.addWidget(self.btn_cut)

        self.file_label = QLabel("Source: None")
        self.file_label.setStyleSheet("color: #aaa; font-style: italic;")
        settings.addLayout(input_row)
        settings.addWidget(self.file_label)
        controls.addLayout(settings)

        left.addWidget(self.video_widget, 1)
        left.addLayout(controls)

        right = QVBoxLayout()
        self.clip_list = QListWidget()
        self.clip_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clip_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.clip_list.customContextMenuRequested.connect(self._show_context_menu)
        self.clip_list.itemClicked.connect(self._play_clip)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_refresh.clicked.connect(self.refresh_clip_list)

        right.addWidget(QLabel("History"))
        right.addWidget(self.clip_list)
        right.addWidget(btn_refresh)

        main_layout.addLayout(left, 82)
        main_layout.addLayout(right, 18)

    def _restore_volume(self) -> None:
        value = self.settings.load_volume(50)
        self.vol_slider.setValue(value)
        self._set_volume(value)

    def _set_volume(self, value: int) -> None:
        self.audio_output.setVolume(value / 100.0)
        self.vol_label.setText(f"{value}%")
        self.vol_icon.setText("🔇" if value == 0 else "🔊")
        self.settings.save_volume(value)

    def _download_video(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            return
        if self._download_thread and self._download_thread.isRunning():
            QMessageBox.information(self, "Download", "A download is already running.")
            return
        self.setWindowTitle("Downloading... Please wait")
        self._download_thread, self._download_worker = start_download(
            self,
            self.downloader,
            url,
            self._on_download_ok,
            self._on_download_err,
        )

    def _on_download_ok(self, file_path: str) -> None:
        self.setWindowTitle(WINDOW_TITLE)
        self.load_source(file_path)
        QMessageBox.information(self, "Success", f"Downloaded and loaded:\n{file_path}")

    def _on_download_err(self, message: str) -> None:
        self.setWindowTitle(WINDOW_TITLE)
        QMessageBox.critical(self, "Download Error", f"Failed to download:\n{message}")

    def load_source(self, path: str) -> None:
        source = Path(path)
        if not source.exists():
            return
        self.input_path = str(source)
        self.file_label.setText(f"Source: {source.name}")
        self.name_input.setText(f"{source.stem}_sub")
        self.media_player.setSource(QUrl.fromLocalFile(str(source)))
        self.media_player.play()

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov)",
        )
        if path:
            self.load_source(path)

    def _show_context_menu(self, position) -> None:
        item = self.clip_list.itemAt(position)
        if not item:
            return
        menu = QMenu(self)
        delete_action = QAction("Delete File", self)
        delete_action.triggered.connect(lambda: self._delete_file(item.text()))
        menu.addAction(delete_action)
        menu.exec(self.clip_list.mapToGlobal(position))

    def _delete_file(self, file_name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete {file_name} permanently?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            full_path = self.library.path_for(file_name)
            if self.media_player.source().toLocalFile() == str(full_path):
                self.media_player.stop()
                self.media_player.setSource(QUrl(""))
                self.input_path = ""
            self.library.delete(file_name)
            self.refresh_clip_list()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def toggle_playback(self) -> None:
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _sync_start_to_current(self) -> None:
        pos = self.media_player.position()
        self.start_slider.setValue(pos)
        self._set_start_from_slider(pos)

    def _sync_end_to_current(self) -> None:
        pos = self.media_player.position()
        self.end_slider.setValue(pos)
        self._set_end_from_slider(pos)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        focused = self.focusWidget()
        if focused in (self.start_input, self.end_input, self.name_input, self.url_input):
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Space:
            self.toggle_playback()
            event.accept()
            return
        super().keyPressEvent(event)

    def _set_start_from_slider(self, position: int) -> None:
        val = position / 1000.0
        self.start_input.setText(f"{val:.1f}")
        self.start_highlight.setText(f"Start: {val:.1f}s")
        self.media_player.setPosition(position)

    def _set_end_from_slider(self, position: int) -> None:
        val = position / 1000.0
        self.end_input.setText(f"{val:.1f}")
        self.end_highlight.setText(f"End: {val:.1f}s")
        preview_pos = max(0, int(position - (self.end_preview_offset * 1000)))
        self.media_player.setPosition(preview_pos)

    def _on_duration_changed(self, duration: int) -> None:
        self.slider.setRange(0, duration)
        self.start_slider.setRange(0, duration)
        self.end_slider.setRange(0, duration)
        self.end_slider.setValue(duration)
        self.end_input.setText(f"{duration / 1000.0:.1f}")
        self.end_highlight.setText(f"End: {duration / 1000.0:.1f}s")
        dur_s = duration / 1000.0
        for i, label in enumerate(self.scale_labels):
            label.setText(f"{(dur_s * i) / 10.0:.1f}s")

    def _seek(self, position: int) -> None:
        self.media_player.setPosition(position)

    def _on_position_changed(self, position: int) -> None:
        self.slider.setValue(position)
        curr_s = position / 1000.0
        dur_ms = self.media_player.duration()
        dur_s = dur_ms / 1000.0
        self.time_display.setText(f"{_format_clock(curr_s)} / {_format_clock(dur_s)}")
        self.curr_highlight.setText(f"Current: {curr_s:.1f}s")
        try:
            start_ms = float(self.start_input.text() or 0) * 1000
            end_ms = float(self.end_input.text() or (dur_ms / 1000.0)) * 1000
            if position >= end_ms and end_ms > start_ms:
                self.media_player.setPosition(int(start_ms))
        except ValueError:
            pass

    def _on_media_status_changed(self, status) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        try:
            start_ms = float(self.start_input.text() or 0) * 1000
            self.media_player.setPosition(int(start_ms))
            self.media_player.play()
        except ValueError:
            self.media_player.setPosition(0)

    def _reset_range_to_full(self) -> None:
        dur_ms = self.media_player.duration()
        self.start_slider.setValue(0)
        self._set_start_from_slider(0)
        self.end_slider.setValue(dur_ms)
        self._set_end_from_slider(dur_ms)

    def _cut_video(self) -> None:
        name = _safe_clip_stem(self.name_input.text())
        if not self.input_path or not name:
            QMessageBox.warning(self, "Alert", "Missing info.")
            return
        output_path = self.library.path_for(f"{name}.mp4")
        try:
            self.exporter.export(
                Path(self.input_path),
                self.start_input.text(),
                self.end_input.text(),
                output_path,
            )
            QMessageBox.information(self, "Success", "Saved!")
            self.refresh_clip_list()
            self._reset_range_to_full()
        except ExportError as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def refresh_clip_list(self) -> None:
        self.clip_list.clear()
        self.clip_list.addItems(self.library.list_names())

    def _play_clip(self, item) -> None:
        self.load_source(str(self.library.path_for(item.text())))
