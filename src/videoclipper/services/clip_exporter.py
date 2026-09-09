from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable


class ExportError(RuntimeError):
    pass


class ClipExporter:
    """Cuts a source video to a named clip with ffmpeg."""

    def __init__(self, ffmpeg_path: str | None = None):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")

    def export(
        self,
        source: Path,
        start_sec: str,
        end_sec: str,
        destination: Path,
        progress_callback: Callable[[float], None] | None = None,
    ) -> Path:
        if not self.ffmpeg_path:
            raise ExportError("ffmpeg was not found on PATH.")
        if not source.exists():
            raise ExportError("Source video is missing.")
        destination.parent.mkdir(parents=True, exist_ok=True)

        clip_duration_ms = max(1.0, (float(end_sec) - float(start_sec)) * 1000.0)

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
            "-progress",
            "pipe:1",
            "-nostats",
            str(destination),
        ]
        kwargs: dict = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            process = subprocess.Popen(cmd, **kwargs)
            assert process.stdout is not None
            for line in process.stdout:
                if progress_callback and line.startswith("out_time_ms="):
                    # ffmpeg's "out_time_ms" field is actually microseconds (long-standing
                    # naming quirk kept for backward compatibility).
                    raw = line.strip().split("=", 1)[1]
                    if raw.isdigit():
                        out_time_ms = int(raw) / 1000
                        progress_callback(min(100.0, out_time_ms / clip_duration_ms * 100.0))
            returncode = process.wait()
            if returncode != 0:
                raise ExportError(f"ffmpeg exited with status {returncode}.")
        except (OSError, ValueError) as exc:
            raise ExportError(str(exc)) from exc
        if progress_callback:
            progress_callback(100.0)
        return destination
