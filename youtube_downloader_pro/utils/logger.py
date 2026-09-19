import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from youtube_downloader_pro.utils.paths import logs_dir


def redact(text: str) -> str:
    text = re.sub(r'https?://[^\s\]<>"\']+', "[URL redacted]", str(text))
    text = re.sub(r"(?i)(authorization|cookie)(\s*[:=]\s*)[^\r\n]+", r"\1\2[redacted]", text)
    text = re.sub(
        r"(?i)(token|password|secret)(\s*[:=]\s*)[^\s,;]+",
        r"\1\2[redacted]",
        text,
    )
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(folder: Path | None = None) -> Path:
    folder = folder or logs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("youtube_downloader_pro")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(
            folder / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    return folder
