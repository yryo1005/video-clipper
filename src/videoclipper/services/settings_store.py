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
        payload = {"volume": max(0, min(100, int(value)))}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass
