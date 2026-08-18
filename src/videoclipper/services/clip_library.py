from __future__ import annotations

from pathlib import Path

from videoclipper.config import CLIP_VIDEO_EXTS


class ClipLibrary:
    """Manages exported clip files in the history folder."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)

    def list_names(self) -> list[str]:
        files = [
            path
            for path in self.folder.iterdir()
            if path.is_file() and path.suffix.lower() in CLIP_VIDEO_EXTS
        ]
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return [path.name for path in files]

    def path_for(self, name: str) -> Path:
        candidate = (self.folder / Path(name).name).resolve()
        folder = self.folder.resolve()
        if folder not in candidate.parents and candidate != folder:
            raise ValueError("Invalid clip name.")
        return candidate

    def delete(self, name: str) -> None:
        path = self.path_for(name)
        if path.exists():
            path.unlink()
