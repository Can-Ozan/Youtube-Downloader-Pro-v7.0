from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from youtube_downloader_pro.models.download_status import ALLOWED_TRANSITIONS, DownloadStatus
from youtube_downloader_pro.models.settings import Settings
from youtube_downloader_pro.utils.validators import ValidationError


@dataclass(frozen=True)
class DownloadOptions:
    settings: Settings
    mode: str = "video"
    quality: str = "Best Available"
    container: str = "mp4"
    custom_format: str = ""
    download_again: bool = False
    playlist_index: int | None = None
    playlist_title: str = ""

    def validate(self) -> "DownloadOptions":
        self.settings.validate()
        if self.mode not in {"video", "audio", "custom"}:
            raise ValidationError("Choose Video, Audio, or Custom mode.")
        if self.container not in {"mp4", "webm"}:
            raise ValidationError("Choose MP4 or WebM.")
        if self.mode == "custom" and (
            not self.custom_format
            or len(self.custom_format) > 400
            or any(ord(c) < 32 for c in self.custom_format)
        ):
            raise ValidationError("Enter a yt-dlp format selector or select an available format.")
        if self.quality != "Best Available" and (
            not self.quality.endswith("p") or not self.quality[:-1].isdigit()
        ):
            raise ValidationError("Invalid resolution.")
        return self

    @property
    def quality_label(self) -> str:
        if self.mode == "audio":
            return (
                "Lossless"
                if self.settings.audio_format in {"flac", "wav"}
                else (f"{self.settings.audio_bitrate} kbps")
            )
        return self.quality

    @property
    def format_label(self) -> str:
        return (
            self.settings.audio_format
            if self.mode == "audio"
            else ("custom" if self.mode == "custom" else self.container)
        )


@dataclass
class DownloadItem:
    url: str
    title: str
    options: DownloadOptions
    id: str = field(default_factory=lambda: uuid4().hex)
    status: DownloadStatus = DownloadStatus.WAITING
    thumbnail_url: str = ""
    duration: float | None = None
    estimated_size: int | None = None
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    speed: float | None = None
    eta: float | None = None
    progress: float = 0
    attempt: int = 0
    message: str = ""
    error_code: str = ""
    output_file: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def transition(self, status: DownloadStatus) -> None:
        if status != self.status and status not in ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"Invalid transition: {self.status} → {status}")
        self.status = status
