from collections import deque

from youtube_downloader_pro.utils.validators import is_clipboard_media_url, validate_url


class ClipboardService:
    def __init__(self) -> None:
        self.seen: deque[str] = deque(maxlen=100)

    def detect(self, text: str, enabled: bool) -> str | None:
        if not enabled or not is_clipboard_media_url(text):
            return None
        url = validate_url(text)
        if url in self.seen:
            return None
        self.seen.append(url)
        return url

    def ignore_copy(self, text: str) -> None:
        """Remember application copies before Qt emits clipboard change notifications."""
        if is_clipboard_media_url(text):
            url = validate_url(text)
            if url not in self.seen:
                self.seen.append(url)
