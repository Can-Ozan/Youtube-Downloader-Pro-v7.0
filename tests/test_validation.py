from dataclasses import replace
from datetime import UTC, datetime

import pytest

from youtube_downloader_pro.core.clipboard_service import ClipboardService
from youtube_downloader_pro.core.errors import classify_error
from youtube_downloader_pro.core.scheduler import Scheduler, next_run
from youtube_downloader_pro.utils.formatting import format_bytes, format_duration
from youtube_downloader_pro.utils.logger import redact
from youtube_downloader_pro.utils.paths import contained_file, sanitize_filename
from youtube_downloader_pro.utils.validators import ValidationError, validate_template, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "file:///etc/passwd",
        "ftp://example.com",
        "javascript:alert(1)",
        "https://",
        "https://u:p@example.com/a",
        "https://example.com:bad",
        "https://host/a\nb",
        "https://example.com/a b",
        "https://example.com\\@evil.test",
    ],
)
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValidationError):
        validate_url(url)


def test_url_normalization_and_clipboard_hosts():
    assert validate_url(" https://example.com/a?q=x#fragment ") == "https://example.com/a?q=x"
    watcher = ClipboardService()
    assert watcher.detect("https://youtube.com.evil.test/a", True) is None
    assert watcher.detect("https://evil.test/youtube.com", True) is None
    assert watcher.detect("https://youtu.be/abc", False) is None
    assert watcher.detect("https://youtu.be/abc", True)
    assert watcher.detect("https://youtu.be/abc", True) is None


@pytest.mark.parametrize(
    "template",
    [
        "../%(title)s.%(ext)s",
        "/%(title)s.%(ext)s",
        "C:/%(title)s.%(ext)s",
        "%(title)s.mp3",
        "%(unknown)s.%(ext)s",
        "%(title)s/../../x.%(ext)s",
        "%(title)s\\x.%(ext)s",
        "x/%(title)s|evil.%(ext)s",
    ],
)
def test_unsafe_templates_rejected(template):
    with pytest.raises(ValidationError):
        validate_template(template)


def test_safe_filenames_and_paths(tmp_path):
    assert sanitize_filename("CON.txt") == "_CON.txt"
    assert sanitize_filename("a<b>:c?*. ") == "a_b__c__"
    assert sanitize_filename("İstanbul 日本語") == "İstanbul 日本語"
    assert len(sanitize_filename("a" * 1000)) == 160
    assert len(sanitize_filename("日本語" * 100).encode("utf-8")) <= 160
    assert validate_template("%(uploader)s/%(playlist_index)03d - %(title)s.%(ext)s")
    with pytest.raises(ValidationError):
        contained_file(tmp_path, tmp_path / ".." / "escape.txt")


@pytest.mark.parametrize(
    "size, expected",
    [(0, "0.0 B"), (1024, "1.0 KiB"), (1024**4, "1.0 TiB"), (None, "—"), (-1, "—")],
)
def test_size_formatting(size, expected):
    assert format_bytes(size) == expected


def test_duration():
    assert format_duration(3661) == "1:01:01"
    assert format_duration(61) == "1:01"


@pytest.mark.parametrize("value", ["99:99", "abc", "", "24:00", "12:60", "1:00"])
def test_invalid_schedule_never_armed(value):
    scheduler = Scheduler()
    with pytest.raises(ValidationError):
        scheduler.schedule(value)
    assert scheduler.target is None


def test_scheduler_next_day_replace_cancel():
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    assert next_run("11:00", now).day == 10
    scheduler = Scheduler()
    scheduler.schedule("13:00", now)
    scheduler.schedule("14:00", now)
    assert not scheduler.due(now.replace(hour=13))
    assert scheduler.due(now.replace(hour=14))
    assert not scheduler.due(now.replace(hour=15))
    scheduler.schedule("13:00", now)
    scheduler.cancel()
    assert scheduler.target is None


@pytest.mark.parametrize(
    "message, code, retry",
    [
        ("Connection timed out", "network", True),
        ("Video unavailable", "unavailable", False),
        ("Private video", "restricted", False),
        ("Unsupported URL", "unsupported", False),
        ("FFmpeg conversion failed", "ffmpeg", False),
        ("No space left on device", "disk_full", False),
        ("Requested format is not available", "format", False),
    ],
)
def test_error_classification(message, code, retry):
    error = classify_error(RuntimeError(message))
    assert (error.code, error.retryable) == (code, retry)


def test_log_redaction():
    output = redact("Failed https://host/file?token=secret Authorization: bearer cookie=abc")
    assert "secret" not in output and "host" not in output and "abc" not in output


def test_settings_reject_wrong_types(settings):
    with pytest.raises(ValueError):
        replace(settings, parallel_downloads=True).validate()
