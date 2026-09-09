from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from videoclipper.config import CLIP_VIDEO_EXTS, TRASH_RETENTION_DAYS

_CLIP_NUMBER_RE = re.compile(r"^(\d+)")
_TRAILING_NUMBER_RE = re.compile(r"^(.*?)[_ ]?\d+$")
_TRASH_DIR_NAME = ".trash"


def _group_base_name(stem: str) -> str:
    match = _TRAILING_NUMBER_RE.match(stem)
    return match.group(1) if match and match.group(1) else stem


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}__{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


class ClipLibrary:
    """Manages exported clips, grouped into one folder per source video, with a trash bin."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self._migrate_flat_clips()
        self.purge_trash_older_than(TRASH_RETENTION_DAYS)

    def _migrate_flat_clips(self) -> None:
        stray = [
            path
            for path in self.folder.iterdir()
            if path.is_file() and path.suffix.lower() in CLIP_VIDEO_EXTS
        ]
        for path in stray:
            target_dir = self.folder / _group_base_name(path.stem)
            target_dir.mkdir(parents=True, exist_ok=True)
            path.rename(target_dir / path.name)

    def _trash_dir(self) -> Path:
        path = self.folder / _TRASH_DIR_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_videos(self) -> list[str]:
        folders = [
            path
            for path in self.folder.iterdir()
            if path.is_dir() and path.name != _TRASH_DIR_NAME
        ]

        def latest_activity(path: Path) -> float:
            times = [path.stat().st_mtime]
            times.extend(child.stat().st_mtime for child in path.iterdir() if child.is_file())
            return max(times)

        folders.sort(key=latest_activity, reverse=True)
        return [path.name for path in folders]

    def list_clips(self, video_name: str) -> list[str]:
        video_dir = self._video_dir(video_name)
        if not video_dir.is_dir():
            return []
        files = [
            path
            for path in video_dir.iterdir()
            if path.is_file() and path.suffix.lower() in CLIP_VIDEO_EXTS
        ]
        files.sort(key=lambda path: path.name)
        return [path.name for path in files]

    def next_clip_number(self, video_name: str) -> int:
        highest = 0
        for name in self.list_clips(video_name):
            match = _CLIP_NUMBER_RE.match(name)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest + 1

    def _video_dir(self, video_name: str) -> Path:
        candidate = (self.folder / Path(video_name).name).resolve()
        folder = self.folder.resolve()
        if folder not in candidate.parents and candidate != folder:
            raise ValueError("Invalid video name.")
        return candidate

    def path_for(self, video_name: str, clip_name: str) -> Path:
        video_dir = self._video_dir(video_name)
        candidate = (video_dir / Path(clip_name).name).resolve()
        if video_dir not in candidate.parents and candidate != video_dir:
            raise ValueError("Invalid clip name.")
        return candidate

    def rename_video(self, old_name: str, new_name: str) -> str:
        old_dir = self._video_dir(old_name)
        new_dir = self._video_dir(new_name)
        if not old_dir.is_dir():
            raise ValueError("Video folder not found.")
        if old_dir == new_dir:
            return new_dir.name
        if new_dir.exists():
            raise ValueError(f"'{new_dir.name}' already exists.")
        old_dir.rename(new_dir)
        return new_dir.name

    def rename_clip(self, video_name: str, old_clip_name: str, new_clip_name: str) -> str:
        old_path = self.path_for(video_name, old_clip_name)
        if not old_path.exists():
            raise ValueError("Clip not found.")
        if not Path(new_clip_name).suffix:
            new_clip_name = f"{new_clip_name}{old_path.suffix}"
        new_path = self.path_for(video_name, new_clip_name)
        if old_path == new_path:
            return new_path.name
        if new_path.exists():
            raise ValueError(f"'{new_path.name}' already exists.")
        old_path.rename(new_path)
        return new_path.name

    def trash_clip(self, video_name: str, clip_name: str) -> None:
        path = self.path_for(video_name, clip_name)
        if path.exists():
            target_dir = self._trash_dir() / video_name
            target_dir.mkdir(parents=True, exist_ok=True)
            path.rename(_unique_path(target_dir / path.name))
        video_dir = self._video_dir(video_name)
        if video_dir.is_dir() and not any(video_dir.iterdir()):
            video_dir.rmdir()

    def trash_video(self, video_name: str) -> None:
        video_dir = self._video_dir(video_name)
        if not video_dir.is_dir():
            return
        target_dir = self._trash_dir() / video_name
        if target_dir.exists():
            for path in video_dir.iterdir():
                path.rename(_unique_path(target_dir / path.name))
            video_dir.rmdir()
        else:
            video_dir.rename(target_dir)

    def list_trash_videos(self) -> list[str]:
        trash = self._trash_dir()
        folders = [path for path in trash.iterdir() if path.is_dir()]
        folders.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return [path.name for path in folders]

    def list_trash_clips(self, video_name: str) -> list[str]:
        video_dir = self._trash_dir() / Path(video_name).name
        if not video_dir.is_dir():
            return []
        files = [path for path in video_dir.iterdir() if path.is_file()]
        files.sort(key=lambda path: path.name)
        return [path.name for path in files]

    def _trash_path_for(self, video_name: str, clip_name: str) -> Path:
        trash_root = self._trash_dir().resolve()
        video_dir = (trash_root / Path(video_name).name).resolve()
        if trash_root not in video_dir.parents and video_dir != trash_root:
            raise ValueError("Invalid video name.")
        candidate = (video_dir / Path(clip_name).name).resolve()
        if video_dir not in candidate.parents and candidate != video_dir:
            raise ValueError("Invalid clip name.")
        return candidate

    def restore_clip(self, video_name: str, clip_name: str) -> None:
        path = self._trash_path_for(video_name, clip_name)
        if not path.exists():
            return
        target_dir = self._video_dir(video_name)
        target_dir.mkdir(parents=True, exist_ok=True)
        path.rename(_unique_path(target_dir / path.name))
        video_dir = path.parent
        if video_dir.is_dir() and not any(video_dir.iterdir()):
            video_dir.rmdir()

    def restore_video(self, video_name: str) -> None:
        trash_video_dir = self._trash_dir() / Path(video_name).name
        if not trash_video_dir.is_dir():
            return
        target_dir = self._video_dir(video_name)
        if target_dir.exists():
            for path in trash_video_dir.iterdir():
                path.rename(_unique_path(target_dir / path.name))
            trash_video_dir.rmdir()
        else:
            trash_video_dir.rename(target_dir)

    def permanently_delete_trash_clip(self, video_name: str, clip_name: str) -> None:
        path = self._trash_path_for(video_name, clip_name)
        if path.exists():
            path.unlink()
        video_dir = path.parent
        if video_dir.is_dir() and not any(video_dir.iterdir()):
            video_dir.rmdir()

    def permanently_delete_trash_video(self, video_name: str) -> None:
        video_dir = self._trash_dir() / Path(video_name).name
        if video_dir.is_dir():
            shutil.rmtree(video_dir)

    def empty_trash(self) -> None:
        trash = self._trash_dir()
        for path in trash.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    def purge_trash_older_than(self, days: int) -> None:
        cutoff = time.time() - days * 86400
        trash = self._trash_dir()
        for video_dir in list(trash.iterdir()):
            if not video_dir.is_dir():
                continue
            for clip_path in list(video_dir.iterdir()):
                if clip_path.is_file() and clip_path.stat().st_mtime < cutoff:
                    clip_path.unlink()
            if not any(video_dir.iterdir()):
                video_dir.rmdir()
