import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from platformdirs import user_data_path, user_downloads_path, user_log_path

from youtube_downloader_pro.utils.validators import ValidationError


def app_data_dir() -> Path:
    return user_data_path("YouTubeDownloaderPro", appauthor=False)


def logs_dir() -> Path:
    return user_log_path("YouTubeDownloaderPro", appauthor=False)


def default_download_dir() -> Path:
    return user_downloads_path() / "YouTube Downloader Pro"


def sanitize_filename(value: str, max_length: int = 160) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value, re.I):
        value = "_" + value
    value = value[:max_length]
    while len(value.encode("utf-8")) > max_length:
        value = value[:-1]
    return value.rstrip(" .") or "untitled"


def ensure_output_dir(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValidationError("Choose an absolute download folder.")
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def contained_file(root: Path, value: str | Path) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValidationError("The output filename would escape the download folder.")
    return path


def check_disk_space(folder: Path, estimated_size: int | None) -> None:
    if estimated_size and shutil.disk_usage(folder).free < estimated_size * 2 + 32 * 1024**2:
        raise OSError(28, "Insufficient free disk space for the media and processing files")


def open_path(path: Path) -> None:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError("This file or folder no longer exists.")
    media_extensions = {
        ".mp4",
        ".webm",
        ".mkv",
        ".mov",
        ".avi",
        ".flv",
        ".m4v",
        ".ts",
        ".mp3",
        ".m4a",
        ".opus",
        ".ogg",
        ".flac",
        ".wav",
        ".aac",
        ".wma",
        ".srt",
        ".vtt",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".txt",
    }
    if path.is_file() and path.suffix.lower() not in media_extensions:
        raise ValidationError("This file type cannot be opened from the application.")
    if sys.platform == "win32":
        os.startfile(str(path))
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
