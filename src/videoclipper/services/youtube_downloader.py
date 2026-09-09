from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

import yt_dlp


class DownloadError(RuntimeError):
    pass


def find_deno() -> str | None:
    found = shutil.which("deno")
    if found:
        return found
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    winget_packages = local_app / "Microsoft" / "WinGet" / "Packages"
    if winget_packages.is_dir():
        matches = sorted(winget_packages.glob("DenoLand.Deno_*/deno.exe"))
        if matches:
            return str(matches[-1])
    home_deno = Path.home() / ".deno" / "bin" / "deno.exe"
    if home_deno.exists():
        return str(home_deno)
    return None


def _result_path(ydl: yt_dlp.YoutubeDL, info: dict) -> Path:
    requested = info.get("requested_downloads") or []
    if requested:
        filepath = requested[0].get("filepath")
        if filepath and Path(filepath).exists():
            return Path(filepath)
    prepared = Path(ydl.prepare_filename(info))
    if prepared.exists():
        return prepared
    merged = prepared.with_suffix(".mp4")
    if merged.exists():
        return merged
    raise DownloadError("Download finished but the output file was not found.")


class YouTubeDownloader:
    """Downloads YouTube videos with yt-dlp using settings that avoid 403s."""

    def __init__(self, download_dir: Path):
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def download(self, url: str, progress_callback: Callable[[float], None] | None = None) -> Path:
        url = url.strip()
        if not url:
            raise DownloadError("URL is empty.")

        def hook(status: dict) -> None:
            if not progress_callback:
                return
            if status.get("status") == "downloading":
                total = status.get("total_bytes") or status.get("total_bytes_estimate")
                downloaded = status.get("downloaded_bytes")
                if total and downloaded is not None:
                    progress_callback(min(100.0, downloaded / total * 100.0))
            elif status.get("status") == "finished":
                progress_callback(100.0)

        outtmpl = str(self.download_dir / "downloaded_%(title)s.%(ext)s")
        ydl_opts: dict = {
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "check_formats": "selected",
            "extractor_args": {
                "youtube": {
                    "player_client": ["default", "-android_vr"],
                }
            },
            "progress_hooks": [hook],
        }
        deno = find_deno()
        if deno:
            ydl_opts["js_runtimes"] = {"deno": {"path": deno}}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise DownloadError("Could not read video information.")
                if "entries" in info:
                    entries = [entry for entry in info["entries"] if entry]
                    if not entries:
                        raise DownloadError("Playlist had no downloadable videos.")
                    info = entries[0]
                return _result_path(ydl, info)
        except DownloadError:
            raise
        except Exception as exc:
            raise DownloadError(str(exc)) from exc
