from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class ExportError(RuntimeError):
    pass


class ClipExporter:
    """Cuts a source video to a named clip with ffmpeg."""

    def __init__(self, ffmpeg_path: str | None = None):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")

    def export(self, source: Path, start_sec: str, end_sec: str, destination: Path) -> Path:
        if not self.ffmpeg_path:
            raise ExportError("ffmpeg was not found on PATH.")
        if not source.exists():
            raise ExportError("Source video is missing.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-ss",
            start_sec,
            "-to",
            end_sec,
            "-i",
            str(source),
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            str(destination),
        ]
        kwargs: dict = {"check": True}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            subprocess.run(cmd, **kwargs)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ExportError(str(exc)) from exc
        return destination
