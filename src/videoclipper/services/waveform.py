from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from array import array
from pathlib import Path

from videoclipper.config import WAVEFORM_BUCKETS

_SAMPLE_RATE = 4000
_CACHE_VERSION = 2  # bump when the peak calculation/normalization changes


def _cache_key(video_path: Path, mtime: float, buckets: int) -> str:
    digest = hashlib.sha1(str(video_path.resolve()).encode("utf-8")).hexdigest()
    return f"{digest}_{int(mtime)}_{buckets}_v{_CACHE_VERSION}.json"


def get_waveform(video_path: Path, cache_dir: Path, buckets: int = WAVEFORM_BUCKETS) -> list[float] | None:
    """Returns cached peak amplitudes (0..1) for video_path, computing them with ffmpeg if needed.

    Returns None if ffmpeg is unavailable, the source has no audio, or extraction fails.
    """
    if not video_path.exists():
        return None

    cache_path = cache_dir / _cache_key(video_path, video_path.stat().st_mtime, buckets)
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return None

    cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(_SAMPLE_RATE),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "pipe:1",
    ]
    kwargs: dict = {"stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(cmd, **kwargs)
        data = result.stdout
    except OSError:
        return None

    if not data or len(data) < 2:
        return None

    samples = array("h")
    usable_len = len(data) - (len(data) % 2)
    samples.frombytes(data[:usable_len])
    if not samples:
        return None

    chunk_size = max(1, len(samples) // buckets)
    peaks: list[float] = []
    for i in range(0, len(samples), chunk_size):
        chunk = samples[i : i + chunk_size]
        peak = max(abs(s) for s in chunk) / 32768.0
        peaks.append(peak)
    peaks = peaks[:buckets]

    # Scale relative to this clip's own loudest moment rather than the
    # theoretical int16 maximum, so quieter recordings still fill the display.
    loudest = max(peaks) if peaks else 0.0
    if loudest > 0:
        peaks = [min(1.0, p / loudest) for p in peaks]

    try:
        cache_path.write_text(json.dumps(peaks), encoding="utf-8")
    except OSError:
        pass
    return peaks
