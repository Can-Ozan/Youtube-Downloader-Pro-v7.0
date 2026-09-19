from dataclasses import asdict, dataclass, field
from pathlib import Path

from youtube_downloader_pro.i18n import system_language
from youtube_downloader_pro.utils.paths import default_download_dir
from youtube_downloader_pro.utils.validators import ValidationError, validate_template


@dataclass(frozen=True)
class Settings:
    download_folder: str = field(default_factory=lambda: str(default_download_dir()))
    theme: str = "system"
    language: str = field(default_factory=system_language)
    default_quality: str = "Best Available"
    default_format: str = "mp4"
    audio_format: str = "mp3"
    audio_bitrate: int = 192
    parallel_downloads: int = 3
    fragment_concurrency: int = 2
    speed_limit: int = 0  # bytes per second; zero means unlimited, per download
    subtitle_mode: str = "none"
    subtitle_languages: tuple[str, ...] = ("en", "tr")
    manual_subtitles: bool = True
    automatic_subtitles: bool = False
    subtitle_format: str = "srt"
    clipboard_monitoring: bool = False
    notifications: bool = True
    filename_template: str = "%(title)s [%(id)s].%(ext)s"
    history_enabled: bool = True
    auto_open_folder: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = False
    download_thumbnail: bool = False
    preserve_chapters: bool = True
    write_description: bool = False
    archive_enabled: bool = False
    mini_always_on_top: bool = True

    def validate(self) -> "Settings":
        defaults = Settings()
        for name, value in asdict(self).items():
            expected = getattr(defaults, name)
            if name == "subtitle_languages":
                if not isinstance(value, (tuple, list)) or not all(
                    isinstance(v, str) and v and len(v) <= 30 for v in value
                ):
                    raise ValidationError("Subtitle languages must be language codes.")
            elif type(value) is not type(expected):
                raise ValidationError("A setting has an invalid value type.")
        if not Path(self.download_folder).expanduser().is_absolute():
            raise ValidationError("Choose an absolute download folder.")
        choices = {
            "theme": {"dark", "light", "system"},
            "language": {"en", "tr"},
            "default_format": {"mp4", "webm"},
            "audio_format": {"mp3", "m4a", "opus", "flac", "wav"},
            "subtitle_mode": {"none", "preferred", "manual"},
            "subtitle_format": {"srt", "vtt"},
            "default_quality": {
                "Best Available",
                "2160p",
                "1440p",
                "1080p",
                "720p",
                "480p",
                "360p",
            },
        }
        for name, allowed in choices.items():
            if getattr(self, name) not in allowed:
                raise ValidationError("A setting contains an unsupported choice.")
        if not 1 <= self.parallel_downloads <= 5 or not 1 <= self.fragment_concurrency <= 8:
            raise ValidationError("Use 1–5 downloads and 1–8 fragments per download.")
        if self.audio_bitrate not in {128, 192, 256, 320} or not 0 <= self.speed_limit <= 10**10:
            raise ValidationError("Invalid bitrate or speed limit.")
        validate_template(self.filename_template)
        return self

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {key: value for key, value in data.items() if key in cls.__dataclass_fields__}
        if isinstance(known.get("subtitle_languages"), list):
            known["subtitle_languages"] = tuple(known["subtitle_languages"])
        return cls(**known).validate()
