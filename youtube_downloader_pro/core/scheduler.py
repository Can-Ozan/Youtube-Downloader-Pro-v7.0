import re
from datetime import datetime, timedelta

from youtube_downloader_pro.utils.validators import ValidationError


def next_run(value: str, now: datetime | None = None) -> datetime:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValidationError("Enter a valid 24-hour time, such as 03:00 or 18:30.")
    now = now or datetime.now().astimezone()
    hour, minute = map(int, value.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


class Scheduler:
    """One schedule, checked by the UI's low-frequency timer; no scheduler threads."""

    def __init__(self) -> None:
        self.target: datetime | None = None

    def schedule(self, value: str, now: datetime | None = None) -> datetime:
        self.target = next_run(value, now)
        return self.target

    def cancel(self) -> None:
        self.target = None

    def due(self, now: datetime | None = None) -> bool:
        if self.target and (now or datetime.now().astimezone()) >= self.target:
            self.target = None
            return True
        return False
