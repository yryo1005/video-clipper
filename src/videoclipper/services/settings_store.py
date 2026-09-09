from __future__ import annotations

import json
from pathlib import Path


class SettingsStore:
    """Persists small UI preferences such as volume."""

    def __init__(self, path: Path):
        self.path = path

    def load_volume(self, default: int = 50) -> int:
        if not self.path.exists():
            return default
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            value = int(data.get("volume", default))
            return max(0, min(100, value))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return default

    def save_volume(self, value: int) -> None:
        self._merge({"volume": max(0, min(100, int(value)))})

    def load_playback_rate(self, default: float = 1.0) -> float:
        if not self.path.exists():
            return default
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            value = float(data.get("playback_rate", default))
            return value if value > 0 else default
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return default

    def save_playback_rate(self, value: float) -> None:
        self._merge({"playback_rate": float(value)})

    def _merge(self, update: dict) -> None:
        data = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                data = {}
        data.update(update)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass
