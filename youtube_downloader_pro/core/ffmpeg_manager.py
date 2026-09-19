import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from youtube_downloader_pro.utils.paths import app_data_dir
from youtube_downloader_pro.utils.resources import resource_root


@dataclass(frozen=True)
class FFmpegStatus:
    path: str = ""
    version: str = "Unavailable"
    source: str = "Not found"
    ffprobe_available: bool = False

    @property
    def available(self) -> bool:
        return bool(self.path) and self.ffprobe_available


def detect_ffmpeg(bundle: Path | None = None, managed: Path | None = None) -> FFmpegStatus:
    executable = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    probe = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    bundle = bundle or resource_root()
    managed = managed or app_data_dir() / "ffmpeg" / "bin"
    candidates = [
        (str(bundle / "ffmpeg" / executable), "Bundled"),
        (str(bundle / "ffmpeg" / "bin" / executable), "Bundled"),
        (str(managed / executable), "Application-managed"),
        (shutil.which("ffmpeg"), "System"),
    ]
    incomplete = FFmpegStatus()
    for value, source in candidates:
        if not value or not Path(value).is_file():
            continue
        try:
            result = subprocess.run(
                [value, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            probe_path = Path(value).parent / probe
            probe_ok = False
            if probe_path.is_file():
                subprocess.run(
                    [str(probe_path), "-version"],
                    capture_output=True,
                    timeout=5,
                    check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                probe_ok = True
            status = FFmpegStatus(
                str(Path(value).absolute()), result.stdout.splitlines()[0], source, probe_ok
            )
            if status.available:
                return status
            incomplete = status
        except (OSError, subprocess.SubprocessError, IndexError) as exc:
            logging.getLogger(__name__).warning("FFmpeg probe failed (%s): %s", source, exc)
            continue
    return incomplete
