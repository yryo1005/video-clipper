from __future__ import annotations

from pathlib import Path
import os

APP_NAME = "VideoClipper"
WINDOW_TITLE = "Pro Video Clipper - Smart Preview Edition"
BASE_FONT_SIZE = 16
END_PREVIEW_OFFSET_SEC = 2.0
CLIP_VIDEO_EXTS = (".mp4",)


def _appdata_dir() -> Path:
    roaming = os.environ.get("APPDATA")
    base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def clips_dir() -> Path:
    path = Path.home() / "Videos" / "MyClips"
    path.mkdir(parents=True, exist_ok=True)
    return path


def downloads_dir() -> Path:
    path = Path.home() / "Videos" / APP_NAME / "downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return _appdata_dir() / "settings.json"
