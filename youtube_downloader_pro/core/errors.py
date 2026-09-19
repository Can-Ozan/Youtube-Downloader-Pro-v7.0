import errno
from dataclasses import dataclass


@dataclass
class DownloadError(Exception):
    code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class CancelledError(DownloadError):
    def __init__(self) -> None:
        super().__init__("cancelled", "Cancelled by user.")


def classify_error(exc: Exception) -> DownloadError:
    if isinstance(exc, DownloadError):
        return exc
    text = str(exc).lower()
    if isinstance(exc, PermissionError) or "permission denied" in text:
        return DownloadError("permission", "Cannot write here. Choose a writable download folder.")
    if getattr(exc, "errno", None) == errno.ENOSPC or any(
        word in text for word in ("no space left", "disk full", "insufficient free disk")
    ):
        return DownloadError(
            "disk_full", "Insufficient disk space. Free space or choose another folder."
        )
    if any(
        word in text for word in ("requested format", "no video formats", "format is not available")
    ):
        return DownloadError(
            "format", "The selected format is unavailable. Analyze again or choose Best Available."
        )
    rules = [
        (("drm",), "protected", "This media is protected and cannot be downloaded.", False),
        (
            (
                "private",
                "sign in",
                "login required",
                "authentication",
                "members-only",
                "403",
                "captcha",
                "confirm you’re not",
                "confirm you're not",
            ),
            "restricted",
            "This media requires access or verification. Open it on the source platform.",
            False,
        ),
        (
            ("unavailable", "has been removed", "not available", "404", "copyright"),
            "unavailable",
            "This media is unavailable or has been removed.",
            False,
        ),
        (
            ("unsupported url", "no suitable extractor"),
            "unsupported",
            "This URL is not supported.",
            False,
        ),
        (
            ("requested format", "no video formats", "format is not available"),
            "format",
            "The selected format is unavailable. Analyze again or choose Best Available.",
            False,
        ),
        (
            ("ffmpeg", "ffprobe", "postprocessing", "conversion failed"),
            "ffmpeg",
            "Media processing failed. Check FFmpeg and the selected output format.",
            False,
        ),
        (
            (
                "timed out",
                "timeout",
                "connection",
                "network",
                "temporary",
                "502",
                "503",
                "504",
                "429",
                "urlopen",
                "name resolution",
                "remote end closed",
            ),
            "network",
            "A temporary network error interrupted the download.",
            True,
        ),
    ]
    for words, code, message, retryable in rules:
        if any(word in text for word in words):
            return DownloadError(code, message, retryable)
    if isinstance(exc, OSError):
        return DownloadError(
            "filesystem", "A filesystem error occurred. Check the folder and logs."
        )
    return DownloadError("engine", "The media engine could not finish this request. See details.")
