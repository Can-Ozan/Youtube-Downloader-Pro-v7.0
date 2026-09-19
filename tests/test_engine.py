import errno
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from youtube_downloader_pro.core.ffmpeg_manager import detect_ffmpeg
from youtube_downloader_pro.core.ytdlp_service import (
    SafeYoutubeDL,
    analyze,
    build_options,
    compact_media,
)
from youtube_downloader_pro.models.download_item import DownloadOptions
from youtube_downloader_pro.utils.paths import check_disk_space
from youtube_downloader_pro.utils.staged_output import publish_files


def test_format_discovery_and_playlist_paging(monkeypatch):
    info = {
        "title": "My media",
        "formats": [
            {"format_id": "137", "ext": "mp4", "height": 1080, "vcodec": "avc1", "acodec": "none"},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "aac"},
            {"format_id": "protected", "has_drm": True},
        ],
        "subtitles": {"en": []},
        "automatic_captions": {"tr": []},
    }
    media = compact_media(info, "https://example.com/a")
    assert len(media["formats"]) == 2
    assert media["subtitles"] == ["en"] and media["automatic_captions"] == ["tr"]
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    ydl.extract_info.return_value = {
        "title": "List",
        "playlist_count": 1000,
        "entries": ({"url": f"https://example.com/{i}", "title": str(i)} for i in range(1000)),
    }
    factory = MagicMock(return_value=ydl)
    monkeypatch.setattr("youtube_downloader_pro.core.ytdlp_service.yt_dlp.YoutubeDL", factory)
    result = analyze("https://example.com/list", lambda _: None, start=101)
    assert len(result["entries"]) == 100
    assert result["has_more"] and result["count"] == 1000
    assert factory.call_args.args[0]["playlist_items"] == "101:200"


@pytest.mark.parametrize(
    "entry, expected",
    [
        (
            {"url": "abcdefghijk", "ie_key": "Youtube"},
            "https://www.youtube.com/watch?v=abcdefghijk",
        ),
        (
            {"id": "abcdefghijk", "ie_key": "Youtube", "webpage_url": "https://example.com/list"},
            "https://www.youtube.com/watch?v=abcdefghijk",
        ),
        ({"url": "/media/clip.mp4"}, "https://example.com/media/clip.mp4"),
        ({"url": "//cdn.example.com/clip.mp4"}, "https://cdn.example.com/clip.mp4"),
        (
            {"webpage_url": "https://example.com/watch/one", "url": "not-a-url"},
            "https://example.com/watch/one",
        ),
        (
            {
                "webpage_url": "https://example.com/list#top",
                "url": "internal-id",
                "formats": [{"url": "https://cdn.example.com/clip.mp4"}],
            },
            "https://cdn.example.com/clip.mp4",
        ),
    ],
)
def test_playlist_entries_resolve_to_selected_media(entry, expected):
    result = compact_media(entry, "https://example.com/list", index=27)
    assert result["url"] == expected
    assert result["playlist_index"] == 27


def test_unresolved_playlist_entries_never_fall_back_to_parent(monkeypatch):
    from youtube_downloader_pro.core.errors import DownloadError

    with pytest.raises(DownloadError, match="unavailable"):
        compact_media({"url": "opaque-id"}, "https://example.com/list", index=1)
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    ydl.extract_info.return_value = {
        "title": "List",
        "entries": [{"url": "opaque-id"}] * 99 + [{"url": "https://example.com/valid"}],
    }
    monkeypatch.setattr("youtube_downloader_pro.core.ytdlp_service.yt_dlp.YoutubeDL", lambda _: ydl)
    events = []
    result = analyze("https://example.com/list", events.append)
    assert result["has_more"]  # Unavailable rows cannot prematurely stop unknown-length paging.
    assert [entry["playlist_index"] for entry in result["entries"]] == [100]
    assert result["entries"][0]["url"] == "https://example.com/valid"
    assert len(events) == 99 and all(event["type"] == "log" for event in events)


def test_final_fallback_copy_rolls_back_when_cancelled_on_close(tmp_path, monkeypatch):
    import threading
    from contextlib import contextmanager

    from youtube_downloader_pro.core.errors import CancelledError
    from youtube_downloader_pro.utils import staged_output

    source, destination = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    destination.mkdir()
    media = source / "media.mp4"
    media.write_bytes(b"owned test media")
    cancel = threading.Event()

    def no_hardlinks(*_):
        raise OSError(errno.EXDEV, "copy required")

    original_open = Path.open

    @contextmanager
    def cancel_after_close(path, mode="r", *args, **kwargs):
        with original_open(path, mode, *args, **kwargs) as stream:
            yield stream
        if mode == "xb":
            cancel.set()

    monkeypatch.setattr(staged_output.os, "link", no_hardlinks)
    monkeypatch.setattr(Path, "open", cancel_after_close)
    with pytest.raises(CancelledError):
        publish_files(source, destination, media, cancel)
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("codec", ["mp3", "m4a", "opus", "flac", "wav"])
def test_audio_uses_real_postprocessor(codec, settings, tmp_path):
    options = DownloadOptions(replace(settings, audio_format=codec), mode="audio")
    result = build_options(options, tmp_path, "/trusted/ffmpeg", lambda _: None)
    assert result["postprocessors"][0] == {
        "key": "FFmpegExtractAudio",
        "preferredcodec": codec,
        "preferredquality": "192",
    }
    assert result["ignoreerrors"] is False


def test_video_constraints_and_subtitles(settings, tmp_path):
    settings = replace(
        settings,
        subtitle_mode="preferred",
        automatic_subtitles=True,
        subtitle_languages=("tr", "en"),
        speed_limit=1000,
        fragment_concurrency=4,
    )
    result = build_options(
        DownloadOptions(settings, quality="1080p"), tmp_path, "/ffmpeg", lambda _: None
    )
    assert "height<=1080" in result["format"]
    assert result["subtitleslangs"] == ["tr", "en"]
    assert result["ratelimit"] == 1000
    assert result["concurrent_fragment_downloads"] == 4
    assert {"key": "FFmpegSubtitlesConvertor", "format": "srt"} in result["postprocessors"]
    assert "exec_cmd" not in result and "cookiefile" not in result


def test_safe_expanded_filename(settings, tmp_path):
    opts = build_options(DownloadOptions(settings), tmp_path, "", lambda _: None)
    with SafeYoutubeDL(opts, tmp_path) as ydl:
        path = Path(ydl.prepare_filename({"title": "../CON:/日本語?", "id": "123", "ext": "mp4"}))
    assert path.is_relative_to(tmp_path)
    assert "日本語" in path.name
    assert path.suffix == ".mp4"
    with SafeYoutubeDL(opts, tmp_path) as ydl:
        long_path = Path(ydl.prepare_filename({"title": "日本語" * 100, "id": "123", "ext": "mp4"}))
    assert long_path.suffix == ".mp4"
    assert len(long_path.name.encode("utf-8")) < 255


def test_ffmpeg_detection_order_and_fallback(monkeypatch, tmp_path):
    import sys

    extension = ".exe" if sys.platform == "win32" else ""
    system = tmp_path / "system"
    bundled = tmp_path / "bundle" / "ffmpeg" / "bin"
    for directory in (system, bundled):
        directory.mkdir(parents=True)
        (directory / f"ffmpeg{extension}").touch()
        (directory / f"ffprobe{extension}").touch()
    monkeypatch.setattr("shutil.which", lambda name: str(system / (name + extension)))
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "ffmpeg version test\n")
    )
    result = detect_ffmpeg(tmp_path / "bundle", tmp_path / "managed")
    assert result.available and result.source == "Bundled"
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert detect_ffmpeg(tmp_path / "bundle", tmp_path / "managed").source == "Bundled"
    assert not detect_ffmpeg(tmp_path / "missing", tmp_path / "managed").available


def test_disk_check(monkeypatch, tmp_path):
    monkeypatch.setattr("shutil.disk_usage", lambda _: type("Usage", (), {"free": 10})())
    with pytest.raises(OSError) as error:
        check_disk_space(tmp_path, 1000)
    assert error.value.errno == errno.ENOSPC


def test_publish_collision_keeps_subtitles_and_originals(tmp_path):
    staging, target = tmp_path / "stage", tmp_path / "out"
    staging.mkdir()
    target.mkdir()
    (staging / "video.mp4").write_bytes(b"new media")
    (staging / "video.en.srt").write_text("new subtitles")
    (target / "video.mp4").write_bytes(b"original")
    output = publish_files(staging, target, staging / "video.mp4")
    assert output.name == "video (2).mp4"
    assert (target / "video (2).en.srt").is_file()
    assert (target / "video.mp4").read_bytes() == b"original"
    assert not (target / "video.en.srt").exists()


def test_publish_without_hardlinks(monkeypatch, tmp_path):
    staging = tmp_path / "stage"
    staging.mkdir()
    source = staging / "media.mp4"
    source.write_bytes(b"media" * 1000)

    def unsupported(*_args):
        raise OSError(errno.ENOTSUP, "No hard links")

    monkeypatch.setattr("os.link", unsupported)
    output = publish_files(staging, tmp_path / "out", source)
    assert output.read_bytes() == source.read_bytes()
