"""Exercise actual yt-dlp/FFmpeg with our own generated files over loopback HTTP."""

import json
import os
import shutil
import subprocess
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from youtube_downloader_pro.core.worker import run_worker
from youtube_downloader_pro.core.ytdlp_service import analyze, download, serialize_options
from youtube_downloader_pro.models.download_item import DownloadOptions

pytestmark = pytest.mark.integration


@pytest.fixture
def ffmpeg():
    path = os.environ.get("YDP_TEST_FFMPEG") or shutil.which("ffmpeg")
    if not path:
        pytest.skip("FFmpeg not installed; set YDP_TEST_FFMPEG to run media conversion tests")
    return path


def test_real_analysis_and_isolated_download(local_media, settings, tmp_path):
    directory, host = local_media
    info = analyze(host + "/tone.wav", lambda _: None)
    assert not info["is_playlist"] and info["formats"]
    stage = tmp_path / "stage"
    stage.mkdir()
    options = DownloadOptions(
        replace(settings, embed_metadata=False, preserve_chapters=False),
        mode="custom",
        custom_format="best",
    )
    events = []
    result = run_worker(
        "download",
        {
            "url": host + "/tone.wav",
            "staging": str(stage),
            "options": serialize_options(options),
            "ffmpeg": "",
        },
        threading.Event(),
        events.append,
        30,
    )
    assert Path(result["output_file"]).read_bytes() == (directory / "tone.wav").read_bytes()
    assert any(event["type"] == "progress" for event in events)


@pytest.mark.parametrize("allowed", [True, False])
def test_spawned_worker_requires_archive_claim_before_download(
    local_media, settings, tmp_path, allowed
):
    from youtube_downloader_pro.core.errors import DownloadError

    directory, host = local_media
    stage = tmp_path / "claimed-stage"
    stage.mkdir()
    options = DownloadOptions(
        replace(settings, archive_enabled=True, embed_metadata=False, preserve_chapters=False),
        mode="custom",
        custom_format="best",
    )
    events = []

    def receive(event):
        events.append(event)
        if event["type"] == "archive_claim":
            return allowed
        return None

    payload = {
        "url": host + "/tone.wav",
        "staging": str(stage),
        "ffmpeg": "",
        "options": serialize_options(options),
        "archive_directory": str(tmp_path / "archive"),
    }
    if allowed:
        result = run_worker("download", payload, threading.Event(), receive, 30)
        assert Path(result["output_file"]).read_bytes() == (directory / "tone.wav").read_bytes()
        kinds = [event["type"] for event in events]
        assert kinds.index("archive_claim") < kinds.index("progress")
    else:
        with pytest.raises(DownloadError, match="already downloading"):
            run_worker("download", payload, threading.Event(), receive, 30)
        assert list(stage.iterdir()) == []
    claims = [event for event in events if event["type"] == "archive_claim"]
    assert len(claims) == 1 and claims[0]["archive_id"]


@pytest.mark.parametrize("codec", ["mp3", "m4a", "opus", "flac", "wav"])
def test_real_audio_conversion(codec, local_media, ffmpeg, settings, tmp_path):
    _, host = local_media
    stage = tmp_path / codec
    stage.mkdir()
    options = DownloadOptions(replace(settings, audio_format=codec), mode="audio")
    result = download(
        {
            "url": host + "/tone.wav",
            "staging": str(stage),
            "ffmpeg": ffmpeg,
            "options": serialize_options(options),
        },
        lambda _: None,
    )
    output = Path(result["output_file"])
    assert output.suffix == "." + codec
    # Actual decode proves the media was converted, not merely renamed.
    subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(output), "-f", "null", "-"],
        check=True,
        capture_output=True,
        timeout=20,
    )


@pytest.mark.parametrize("container", ["mp4", "webm"])
def test_real_video_download(container, local_media, ffmpeg, settings, tmp_path):
    directory, host = local_media
    source = directory / ("video." + container)
    codec = "libx264" if container == "mp4" else "libvpx-vp9"
    audio_codec = "aac" if container == "mp4" else "libopus"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=purple:s=160x90:d=0.5",
            "-i",
            str(directory / "tone.wav"),
            "-c:v",
            codec,
            "-c:a",
            audio_codec,
            "-shortest",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    stage = tmp_path / "stage"
    stage.mkdir()
    options = DownloadOptions(settings, container=container)
    result = download(
        {
            "url": host + "/" + source.name,
            "staging": str(stage),
            "ffmpeg": ffmpeg,
            "options": serialize_options(options),
        },
        lambda _: None,
    )
    output = Path(result["output_file"])
    assert output.is_file() and output.suffix == "." + container
    subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(output), "-f", "null", "-"],
        check=True,
        capture_output=True,
        timeout=20,
    )


def test_real_stream_merge_subtitles_and_chapters(
    local_media, ffmpeg, settings, tmp_path, monkeypatch
):
    from youtube_downloader_pro.core.ytdlp_service import SafeYoutubeDL

    directory, host = local_media
    video, audio = directory / "silent.mp4", directory / "audio.m4a"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=purple:s=160x90:d=0.5",
            "-an",
            "-c:v",
            "libx264",
            str(video),
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(directory / "tone.wav"), "-c:a", "aac", str(audio)],
        check=True,
        capture_output=True,
        timeout=20,
    )
    (directory / "captions.vtt").write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:00.500\nOriginal test caption\n", encoding="utf-8"
    )
    metadata = {
        "id": "original",
        "title": "Original stream test",
        "extractor": "generic",
        "extractor_key": "Generic",
        "webpage_url": host + "/own-media",
        "duration": 0.5,
        "formats": [
            {
                "format_id": "audio",
                "url": host + "/audio.m4a",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
            },
            {
                "format_id": "video",
                "url": host + "/silent.mp4",
                "ext": "mp4",
                "height": 90,
                "width": 160,
                "vcodec": "avc1",
                "acodec": "none",
            },
        ],
        "subtitles": {"en": [{"url": host + "/captions.vtt", "ext": "vtt"}]},
        "chapters": [{"start_time": 0, "end_time": 0.5, "title": "Original chapter"}],
    }
    monkeypatch.setattr(SafeYoutubeDL, "extract_info", lambda *_args, **_kwargs: metadata)
    stage = tmp_path / "stage"
    stage.mkdir()
    options = DownloadOptions(
        replace(settings, subtitle_mode="preferred", subtitle_languages=("en",))
    )
    result = download(
        {
            "url": host + "/own-media",
            "staging": str(stage),
            "ffmpeg": ffmpeg,
            "options": serialize_options(options),
        },
        lambda _: None,
    )
    output = Path(result["output_file"])
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(output),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    probe = str(Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe"))
    details = json.loads(
        subprocess.run(
            [probe, "-v", "error", "-show_format", "-show_chapters", "-of", "json", str(output)],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
    )
    assert details["format"]["tags"]["title"] == "Original stream test"
    assert details["chapters"][0]["tags"]["title"] == "Original chapter"
    assert list(stage.glob("*.srt"))
    assert "Original test caption" in next(stage.glob("*.srt")).read_text()


def test_local_html_playlist_analysis(local_media):
    directory, host = local_media
    (directory / "playlist.html").write_text(
        "<html><head><title>Original test playlist</title></head><body>"
        '<audio src="tone.wav"></audio><audio src="tone.wav?copy=2"></audio></body></html>',
        encoding="utf-8",
    )
    result = analyze(host + "/playlist.html", lambda _: None)
    assert result["is_playlist"]
    assert len(result["entries"]) == 2
    assert all(entry["url"] != host + "/playlist.html" for entry in result["entries"])


@pytest.mark.parametrize("codec", ["mp3", "m4a", "opus", "flac"])
def test_real_audio_cover_thumbnail_and_description(
    codec, app, local_media, ffmpeg, settings, tmp_path, monkeypatch
):
    import mutagen
    from PySide6.QtGui import QImage

    from youtube_downloader_pro.core.ytdlp_service import SafeYoutubeDL

    directory, host = local_media
    cover = QImage(32, 32, QImage.Format.Format_RGB32)
    cover.fill(0x6655AA)
    assert cover.save(str(directory / "cover.png"))
    info = {
        "id": "own-audio",
        "title": "Original cover test",
        "description": "Original test description",
        "extractor": "generic",
        "extractor_key": "Generic",
        "webpage_url": host + "/own-audio",
        "thumbnails": [{"id": "cover", "url": host + "/cover.png"}],
        "formats": [
            {
                "format_id": "wav",
                "url": host + "/tone.wav",
                "ext": "wav",
                "vcodec": "none",
                "acodec": "pcm_s16le",
            }
        ],
    }
    monkeypatch.setattr(SafeYoutubeDL, "extract_info", lambda *_args, **_kwargs: info)
    stage = tmp_path / "stage"
    stage.mkdir()
    options = DownloadOptions(
        replace(
            settings,
            audio_format=codec,
            embed_thumbnail=True,
            download_thumbnail=True,
            write_description=True,
        ),
        mode="audio",
    )
    result = download(
        {
            "url": host + "/own-audio",
            "staging": str(stage),
            "ffmpeg": ffmpeg,
            "options": serialize_options(options),
        },
        lambda _: None,
    )
    media = mutagen.File(result["output_file"])
    if codec == "flac":
        assert media.pictures
    elif codec == "opus":
        assert media.tags["metadata_block_picture"]
    elif codec == "m4a":
        assert media.tags["covr"]
    else:
        assert any(key.startswith("APIC") for key in media.tags)
    assert list(stage.glob("*.png"))
    assert next(stage.glob("*.description")).read_text() == "Original test description"
