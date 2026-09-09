from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QUrl
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QIcon, QKeyEvent
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from videoclipper.config import (
    END_PREVIEW_OFFSET_SEC,
    FINE_STEP_MS,
    FRAME_STEP_MS,
    OPEN_VIDEO_EXTS,
    SEEK_STEP_MS,
    WINDOW_TITLE,
    clips_dir,
    downloads_dir,
    settings_file,
    thumbnails_dir,
    waveforms_dir,
)
from videoclipper.services.clip_exporter import ClipExporter
from videoclipper.services.clip_library import ClipLibrary
from videoclipper.services.settings_store import SettingsStore
from videoclipper.services.thumbnailer import get_thumbnail
from videoclipper.services.youtube_downloader import YouTubeDownloader
from videoclipper.ui.download_worker import start_download
from videoclipper.ui.export_worker import start_export
from videoclipper.ui.waveform_worker import start_waveform
from videoclipper.widgets.clickable_slider import ClickableSlider
from videoclipper.widgets.clickable_video import ClickableVideoWidget
from videoclipper.widgets.range_slider import RangeSlider

PLAYBACK_RATES = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]


def _safe_clip_stem(name: str) -> str:
    cleaned = name.strip()
    for char in '<>:"/\\|?*':
        cleaned = cleaned.replace(char, "_")
    return cleaned


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setAcceptDrops(True)
        self.end_preview_offset = END_PREVIEW_OFFSET_SEC
        self.input_path = ""
        self._download_thread = None
        self._download_worker = None
        self._download_queue: list[str] = []
        self._export_thread = None
        self._export_worker = None
        self._last_export_end_ms = 0
        self._waveform_thread = None
        self._waveform_worker = None

        self.settings = SettingsStore(settings_file())
        self.library = ClipLibrary(clips_dir())
        self.exporter = ClipExporter()
        self.downloader = YouTubeDownloader(downloads_dir())

        self._build_player()
        self._build_ui()
        self.refresh_history()
        self._restore_volume()
        self._restore_playback_rate()

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
        left.setSpacing(2)
        controls = QVBoxLayout()

        settings = QVBoxLayout()

        self.timeline_scale = QHBoxLayout()
        self.scale_labels = []
        for _ in range(11):
            label = QLabel("")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 11px;")
            self.timeline_scale.addWidget(label)
            self.scale_labels.append(label)
        controls.addLayout(self.timeline_scale)

        self.slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.sliderMoved.connect(self._seek)
        controls.addWidget(self.slider)

        self.range_slider = RangeSlider()
        self.range_slider.startRequested.connect(self._sync_start_to_current)
        self.range_slider.endRequested.connect(self._sync_end_to_current)
        controls.addWidget(self.range_slider)

        actions_row = QHBoxLayout()
        btn_download = QPushButton("⬇ Download")
        btn_download.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_download.clicked.connect(self._download_video)
        actions_row.addWidget(btn_download)

        btn_reset_range = QPushButton("⟲ Reset")
        btn_reset_range.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_reset_range.setToolTip("Reset Start/End to the full video")
        btn_reset_range.clicked.connect(self._reset_range_to_full)
        actions_row.addWidget(btn_reset_range)

        actions_row.addStretch()
        actions_row.addWidget(QLabel("Start:"))
        actions_row.addWidget(self._make_nudge_button("-1s", self._nudge_start, -SEEK_STEP_MS))
        actions_row.addWidget(self._make_nudge_button("-0.1s", self._nudge_start, -FINE_STEP_MS))
        actions_row.addWidget(self._make_nudge_button("+0.1s", self._nudge_start, FINE_STEP_MS))
        actions_row.addWidget(self._make_nudge_button("+1s", self._nudge_start, SEEK_STEP_MS))
        actions_row.addSpacing(16)
        actions_row.addWidget(QLabel("End:"))
        actions_row.addWidget(self._make_nudge_button("-1s", self._nudge_end, -SEEK_STEP_MS))
        actions_row.addWidget(self._make_nudge_button("-0.1s", self._nudge_end, -FINE_STEP_MS))
        actions_row.addWidget(self._make_nudge_button("+0.1s", self._nudge_end, FINE_STEP_MS))
        actions_row.addWidget(self._make_nudge_button("+1s", self._nudge_end, SEEK_STEP_MS))
        actions_row.addStretch()

        self.vol_icon = QLabel("🔊")
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(50)
        self.vol_slider.setFixedWidth(90)
        self.vol_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol_slider.valueChanged.connect(self._set_volume)
        self.vol_label = QLabel("50%")
        self.vol_label.setFixedWidth(36)
        actions_row.addWidget(self.vol_icon)
        actions_row.addWidget(self.vol_slider)
        actions_row.addWidget(self.vol_label)

        actions_row.addWidget(QLabel("⏱"))
        self.speed_combo = QComboBox()
        self.speed_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for rate in PLAYBACK_RATES:
            self.speed_combo.addItem(f"{rate:g}x", rate)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        actions_row.addWidget(self.speed_combo)

        controls.addLayout(actions_row)

        self.queue_list = QListWidget()
        self.queue_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.queue_list.setFixedHeight(48)
        self.queue_list.setVisible(False)
        settings.addWidget(self.queue_list)

        export_row = QHBoxLayout()
        self.video_name_input = QLineEdit()
        self.video_name_input.setPlaceholderText("Video name (folder)...")

        export_row.addWidget(QLabel("Video:"))
        export_row.addWidget(self.video_name_input, 1)

        self.btn_cut = QPushButton("✨ EXPORT")
        self.btn_cut.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_cut.setMinimumWidth(100)
        self.btn_cut.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.btn_cut.clicked.connect(self._cut_video)
        export_row.addWidget(self.btn_cut)
        settings.addLayout(export_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
        settings.addWidget(self.progress_bar)

        controls.addLayout(settings)

        left.addWidget(self.video_widget, 1)
        left.addLayout(controls)

        right = QVBoxLayout()
        self.clip_tree = QTreeWidget()
        self.clip_tree.setHeaderHidden(True)
        self.clip_tree.setIconSize(QSize(80, 45))
        self.clip_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clip_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.clip_tree.customContextMenuRequested.connect(self._show_context_menu)
        self.clip_tree.itemClicked.connect(self._play_clip)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_refresh.clicked.connect(self.refresh_history)

        right.addWidget(QLabel("Clips"))
        right.addWidget(self.clip_tree)
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

    def _restore_playback_rate(self) -> None:
        rate = self.settings.load_playback_rate(1.0)
        closest = min(PLAYBACK_RATES, key=lambda r: abs(r - rate))
        self.speed_combo.setCurrentIndex(PLAYBACK_RATES.index(closest))
        self.media_player.setPlaybackRate(closest)

    def _on_speed_changed(self, index: int) -> None:
        rate = self.speed_combo.itemData(index)
        if rate is None:
            return
        self.media_player.setPlaybackRate(rate)
        self.settings.save_playback_rate(rate)

    def _download_video(self) -> None:
        url, ok = QInputDialog.getText(self, "Download from YouTube", "URL:")
        if not ok or not url.strip():
            return
        url = url.strip()
        if self._download_thread and self._download_thread.isRunning():
            self._download_queue.append(url)
            self._refresh_queue_display()
            return
        self._start_download(url)

    def _start_download(self, url: str) -> None:
        self.setWindowTitle("Downloading... Please wait")
        self.progress_bar.setFormat("Downloading %p%")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self._download_thread, self._download_worker = start_download(
            self,
            self.downloader,
            url,
            self._on_download_ok,
            self._on_download_err,
            self._on_download_progress,
        )
        self._refresh_queue_display()

    def _on_download_progress(self, percent: float) -> None:
        self.progress_bar.setValue(int(percent))

    def _refresh_queue_display(self) -> None:
        self.queue_list.clear()
        self.queue_list.addItems(self._download_queue)
        self.queue_list.setVisible(bool(self._download_queue))

    def _advance_download_queue(self) -> None:
        if self._download_queue:
            self._start_download(self._download_queue.pop(0))
        else:
            self._refresh_queue_display()

    def _on_download_ok(self, file_path: str) -> None:
        self.setWindowTitle(WINDOW_TITLE)
        self.progress_bar.setVisible(False)
        self.load_source(file_path)
        QMessageBox.information(self, "Success", f"Downloaded and loaded:\n{file_path}")
        self._advance_download_queue()

    def _on_download_err(self, message: str) -> None:
        self.setWindowTitle(WINDOW_TITLE)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Download Error", f"Failed to download:\n{message}")
        self._advance_download_queue()

    def load_source(self, path: str) -> None:
        source = Path(path)
        if not source.exists():
            return
        self.input_path = str(source)
        self.video_name_input.setText(_safe_clip_stem(source.stem))
        self.range_slider.setWaveform([])
        self.media_player.setSource(QUrl.fromLocalFile(str(source)))
        self.media_player.setPlaybackRate(self.speed_combo.currentData())
        self.media_player.play()
        self._waveform_thread, self._waveform_worker = start_waveform(
            self, source, waveforms_dir(), self._on_waveform_ready
        )

    def _on_waveform_ready(self, source_path: str, peaks: list) -> None:
        if source_path == self.input_path:
            self.range_slider.setWaveform(peaks)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in OPEN_VIDEO_EXTS:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in OPEN_VIDEO_EXTS:
                self.load_source(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()

    def _show_context_menu(self, position) -> None:
        item = self.clip_tree.itemAt(position)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        menu = QMenu(self)
        kind = data[0]
        if kind == "clip":
            _, video_name, clip_name = data
            rename_action = QAction("✏ Rename", self)
            rename_action.triggered.connect(lambda: self._rename_clip(video_name, clip_name))
            menu.addAction(rename_action)
            trash_action = QAction("🗑 Move to Trash", self)
            trash_action.triggered.connect(lambda: self._trash_clip(video_name, clip_name))
            menu.addAction(trash_action)
        elif kind == "video":
            _, video_name = data
            rename_action = QAction("✏ Rename", self)
            rename_action.triggered.connect(lambda: self._rename_video(video_name))
            menu.addAction(rename_action)
            trash_action = QAction("🗑 Move to Trash", self)
            trash_action.triggered.connect(lambda: self._trash_video(video_name))
            menu.addAction(trash_action)
        elif kind == "trash_clip":
            _, video_name, clip_name = data
            restore_action = QAction("Restore", self)
            restore_action.triggered.connect(lambda: self._restore_clip(video_name, clip_name))
            menu.addAction(restore_action)
            delete_action = QAction("Delete Permanently", self)
            delete_action.triggered.connect(lambda: self._delete_trash_clip(video_name, clip_name))
            menu.addAction(delete_action)
        elif kind == "trash_video":
            _, video_name = data
            restore_action = QAction("Restore All", self)
            restore_action.triggered.connect(lambda: self._restore_video(video_name))
            menu.addAction(restore_action)
            delete_action = QAction("Delete Permanently", self)
            delete_action.triggered.connect(lambda: self._delete_trash_video(video_name))
            menu.addAction(delete_action)
        elif kind == "trash_root":
            empty_action = QAction("Empty Trash", self)
            empty_action.triggered.connect(self._empty_trash)
            menu.addAction(empty_action)
        menu.exec(self.clip_tree.mapToGlobal(position))

    def _is_active_in_video(self, video_name: str) -> bool:
        if not self.input_path:
            return False
        video_dir = (self.library.folder / video_name).resolve()
        return video_dir in Path(self.input_path).resolve().parents

    def _rename_clip(self, video_name: str, clip_name: str) -> None:
        new_name, ok = QInputDialog.getText(self, "Rename Clip", "New name:", text=clip_name)
        if not ok or not new_name.strip():
            return
        try:
            full_path = self.library.path_for(video_name, clip_name)
            was_active = self.media_player.source().toLocalFile() == str(full_path)
            if was_active:
                self.media_player.stop()
                self.media_player.setSource(QUrl(""))
                self.input_path = ""
            new_clip_name = self.library.rename_clip(video_name, clip_name, new_name.strip())
            if was_active:
                self.load_source(str(self.library.path_for(video_name, new_clip_name)))
            self.refresh_history()
        except ValueError as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _rename_video(self, video_name: str) -> None:
        new_name, ok = QInputDialog.getText(self, "Rename Video", "New name:", text=video_name)
        if not ok or not new_name.strip():
            return
        try:
            was_active = self._is_active_in_video(video_name)
            active_clip_name = Path(self.input_path).name if was_active else None
            if was_active:
                self.media_player.stop()
                self.media_player.setSource(QUrl(""))
                self.input_path = ""
            new_video_name = self.library.rename_video(video_name, _safe_clip_stem(new_name))
            if was_active and active_clip_name:
                self.load_source(str(self.library.path_for(new_video_name, active_clip_name)))
            self.refresh_history()
        except ValueError as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _trash_clip(self, video_name: str, clip_name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Move to Trash",
            f"Move {clip_name} to trash?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            full_path = self.library.path_for(video_name, clip_name)
            if self.media_player.source().toLocalFile() == str(full_path):
                self.media_player.stop()
                self.media_player.setSource(QUrl(""))
                self.input_path = ""
            self.library.trash_clip(video_name, clip_name)
            self.refresh_history()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _trash_video(self, video_name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Move to Trash",
            f"Move the entire folder '{video_name}' to trash?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if self._is_active_in_video(video_name):
                self.media_player.stop()
                self.media_player.setSource(QUrl(""))
                self.input_path = ""
            self.library.trash_video(video_name)
            self.refresh_history()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _restore_clip(self, video_name: str, clip_name: str) -> None:
        try:
            self.library.restore_clip(video_name, clip_name)
            self.refresh_history()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _restore_video(self, video_name: str) -> None:
        try:
            self.library.restore_video(video_name)
            self.refresh_history()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _delete_trash_clip(self, video_name: str, clip_name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Permanently",
            f"Permanently delete {clip_name}? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.library.permanently_delete_trash_clip(video_name, clip_name)
            self.refresh_history()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _delete_trash_video(self, video_name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Permanently",
            f"Permanently delete the trashed folder '{video_name}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.library.permanently_delete_trash_video(video_name)
            self.refresh_history()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _empty_trash(self) -> None:
        reply = QMessageBox.question(
            self,
            "Empty Trash",
            "Permanently delete everything in the trash? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.library.empty_trash()
            self.refresh_history()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def toggle_playback(self) -> None:
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _sync_start_to_current(self) -> None:
        pos = self.media_player.position()
        self.range_slider.setStart(pos)
        self._set_start_from_range(pos)

    def _sync_end_to_current(self) -> None:
        pos = self.media_player.position()
        self.range_slider.setEnd(pos)
        self._set_end_from_range(pos)

    def _make_nudge_button(self, text: str, handler, delta_ms: int) -> QPushButton:
        button = QPushButton(text)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        color = "#AEDFF7" if delta_ms < 0 else "#F7B8B8"
        button.setStyleSheet(f"background-color: {color}; color: #202124;")
        button.clicked.connect(lambda: handler(delta_ms))
        return button

    def _nudge_start(self, delta_ms: int) -> None:
        self.range_slider.setStart(self.range_slider.start() + delta_ms)
        self._set_start_from_range(self.range_slider.start())

    def _nudge_end(self, delta_ms: int) -> None:
        self.range_slider.setEnd(self.range_slider.end() + delta_ms)
        self._set_end_from_range(self.range_slider.end())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        focused = self.focusWidget()
        if focused is self.video_name_input:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Space:
            self.toggle_playback()
            event.accept()
            return
        if event.key() == Qt.Key.Key_I:
            self._sync_start_to_current()
            event.accept()
            return
        if event.key() == Qt.Key.Key_O:
            self._sync_end_to_current()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = SEEK_STEP_MS if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else FRAME_STEP_MS
            direction = -1 if event.key() == Qt.Key.Key_Left else 1
            self.media_player.pause()
            new_pos = max(0, self.media_player.position() + direction * step)
            self.media_player.setPosition(new_pos)
            event.accept()
            return
        super().keyPressEvent(event)

    def _set_start_from_range(self, value: int) -> None:
        self.media_player.setPosition(value)

    def _set_end_from_range(self, value: int) -> None:
        preview_pos = max(0, int(value - (self.end_preview_offset * 1000)))
        self.media_player.setPosition(preview_pos)

    def _on_duration_changed(self, duration: int) -> None:
        self.slider.setRange(0, duration)
        self.range_slider.setRange(0, duration)
        self.range_slider.setEnd(duration)
        dur_s = duration / 1000.0
        for i, label in enumerate(self.scale_labels):
            label.setText(f"{(dur_s * i) / 10.0:.1f}s")

    def _seek(self, position: int) -> None:
        self.media_player.setPosition(position)

    def _on_position_changed(self, position: int) -> None:
        self.slider.setValue(position)
        self.range_slider.setPlayhead(position)
        start_ms = self.range_slider.start()
        end_ms = self.range_slider.end()
        if position >= end_ms and end_ms > start_ms:
            self.media_player.setPosition(start_ms)

    def _on_media_status_changed(self, status) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        self.media_player.setPosition(self.range_slider.start())
        self.media_player.play()

    def _reset_range_to_full(self) -> None:
        dur_ms = self.media_player.duration()
        self.range_slider.setStart(0)
        self._set_start_from_range(0)
        self.range_slider.setEnd(dur_ms)
        self._set_end_from_range(dur_ms)

    def _cut_video(self) -> None:
        video_name = _safe_clip_stem(self.video_name_input.text())
        if not self.input_path or not video_name:
            QMessageBox.warning(self, "Alert", "Missing info.")
            return
        if self._export_thread and self._export_thread.isRunning():
            QMessageBox.information(self, "Export", "An export is already running.")
            return

        number = self.library.next_clip_number(video_name)
        filename = f"{number:03d}.mp4"
        output_path = self.library.path_for(video_name, filename)

        start_sec = f"{self.range_slider.start() / 1000.0:.3f}"
        end_sec = f"{self.range_slider.end() / 1000.0:.3f}"
        self._last_export_end_ms = self.range_slider.end()

        self.btn_cut.setEnabled(False)
        self.setWindowTitle("Exporting... Please wait")
        self.progress_bar.setFormat("Exporting %p%")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self._export_thread, self._export_worker = start_export(
            self,
            self.exporter,
            Path(self.input_path),
            start_sec,
            end_sec,
            output_path,
            self._on_export_ok,
            self._on_export_err,
            self._on_export_progress,
        )

    def _on_export_progress(self, percent: float) -> None:
        self.progress_bar.setValue(int(percent))

    def _on_export_ok(self, output_path: str) -> None:
        self.setWindowTitle(WINDOW_TITLE)
        self.btn_cut.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.refresh_history()
        dur_ms = self.media_player.duration()
        self.range_slider.setStart(self._last_export_end_ms)
        self._set_start_from_range(self.range_slider.start())
        self.range_slider.setEnd(dur_ms)
        self._set_end_from_range(dur_ms)

    def _on_export_err(self, message: str) -> None:
        self.setWindowTitle(WINDOW_TITLE)
        self.btn_cut.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Error", message)

    def _collect_expanded(self) -> set[tuple]:
        expanded: set[tuple] = set()

        def walk(item: QTreeWidgetItem) -> None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and item.isExpanded():
                expanded.add(tuple(data))
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.clip_tree.topLevelItemCount()):
            walk(self.clip_tree.topLevelItem(i))
        return expanded

    def _restore_expanded(self, expanded: set[tuple]) -> None:
        def walk(item: QTreeWidgetItem) -> None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and tuple(data) in expanded:
                item.setExpanded(True)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.clip_tree.topLevelItemCount()):
            walk(self.clip_tree.topLevelItem(i))

    def refresh_history(self) -> None:
        expanded = self._collect_expanded()
        self.clip_tree.clear()

        for video_name in self.library.list_videos():
            clip_names = self.library.list_clips(video_name)
            folder_item = QTreeWidgetItem([f"{video_name} ({len(clip_names)})"])
            font = folder_item.font(0)
            font.setBold(True)
            folder_item.setFont(0, font)
            folder_item.setData(0, Qt.ItemDataRole.UserRole, ("video", video_name))
            for clip_name in clip_names:
                clip_path = self.library.path_for(video_name, clip_name)
                clip_item = QTreeWidgetItem([Path(clip_name).stem])
                thumb = get_thumbnail(clip_path, thumbnails_dir())
                if thumb:
                    clip_item.setIcon(0, QIcon(str(thumb)))
                clip_item.setData(0, Qt.ItemDataRole.UserRole, ("clip", video_name, clip_name))
                folder_item.addChild(clip_item)
            self.clip_tree.addTopLevelItem(folder_item)

        trash_videos = self.library.list_trash_videos()
        trash_total = sum(len(self.library.list_trash_clips(v)) for v in trash_videos)
        trash_root = QTreeWidgetItem([f"🗑 Trash ({trash_total})"])
        font = trash_root.font(0)
        font.setBold(True)
        trash_root.setFont(0, font)
        trash_root.setData(0, Qt.ItemDataRole.UserRole, ("trash_root",))
        for video_name in trash_videos:
            clip_names = self.library.list_trash_clips(video_name)
            video_item = QTreeWidgetItem([f"{video_name} ({len(clip_names)})"])
            video_item.setData(0, Qt.ItemDataRole.UserRole, ("trash_video", video_name))
            for clip_name in clip_names:
                clip_item = QTreeWidgetItem([clip_name])
                clip_item.setData(0, Qt.ItemDataRole.UserRole, ("trash_clip", video_name, clip_name))
                video_item.addChild(clip_item)
            trash_root.addChild(video_item)
        self.clip_tree.addTopLevelItem(trash_root)

        self._restore_expanded(expanded)

    def _play_clip(self, item, column: int = 0) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != "clip":
            return
        _, video_name, clip_name = data
        self.load_source(str(self.library.path_for(video_name, clip_name)))
