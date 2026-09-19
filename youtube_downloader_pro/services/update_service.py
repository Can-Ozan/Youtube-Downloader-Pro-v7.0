import json
import platform
import urllib.request
from functools import lru_cache
from importlib.metadata import version

from youtube_downloader_pro import __version__


@lru_cache(maxsize=1)
def versions() -> dict[str, str]:
    return {
        "Application": __version__,
        "Python": platform.python_version(),
        "yt-dlp": version("yt-dlp"),
        "Operating system": platform.platform(),
    }


def check_engine_version() -> str:
    """Read-only, explicit HTTPS check; never installs or executes release contents."""
    request = urllib.request.Request(
        "https://pypi.org/pypi/yt-dlp/json",
        headers={"User-Agent": "YouTubeDownloaderPro/" + __version__},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("Version response exceeds the size limit")
    version = json.loads(data)["info"]["version"]
    if not isinstance(version, str) or len(version) > 40:
        raise ValueError("Unexpected engine version response")
    return version
