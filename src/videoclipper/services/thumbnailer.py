from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path


def _cache_key(video_path: Path, mtime: float) -> str:
    digest = hashlib.sha1(str(video_path.resolve()).encode("utf-8")).hexdigest()
    return f"{digest}_{int(mtime)}.jpg"


def get_thumbnail(video_path: Path, cache_dir: Path) -> Path | None:
    """Returns a cached thumbnail for video_path, generating one with ffmpeg if needed.

    Returns None if ffmpeg is unavailable or extraction fails.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path or not video_path.exists():
        return None

    cache_path = cache_dir / _cache_key(video_path, video_path.stat().st_mtime)
    if cache_path.exists():
        return cache_path

    cmd = [
        ffmpeg_path,
        "-y",
        "-ss",
        "0.5",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        "scale=160:-1",
        "-q:v",
        "5",
        str(cache_path),
    ]
    kwargs: dict = {
        "check": True,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        subprocess.run(cmd, **kwargs)
    except (OSError, subprocess.CalledProcessError):
        return None
    return cache_path if cache_path.exists() else None
