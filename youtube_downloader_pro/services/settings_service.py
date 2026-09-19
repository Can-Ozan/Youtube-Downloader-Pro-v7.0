import json
import logging
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from youtube_downloader_pro.models.settings import Settings
from youtube_downloader_pro.utils.paths import app_data_dir

log = logging.getLogger(__name__)


class SettingsService:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "settings.json"
        self.warning = ""

    def load(self) -> Settings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Settings must be an object")
            return Settings.from_dict(data)
        except FileNotFoundError:
            return Settings()
        except (OSError, ValueError, TypeError) as exc:
            log.warning("Configuration could not be loaded: %s", exc)
            self.warning = (
                "Settings could not be loaded. Defaults are in use; the original is retained."
            )
            return Settings()

    def save(self, settings: Settings) -> None:
        settings.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix="settings-",
                suffix=".tmp",
                delete=False,
            ) as f:
                temporary = Path(f.name)
                json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
