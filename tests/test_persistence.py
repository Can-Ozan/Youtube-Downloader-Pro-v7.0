from dataclasses import replace

from youtube_downloader_pro.models.download_item import DownloadItem, DownloadOptions
from youtube_downloader_pro.models.download_status import DownloadStatus as Status
from youtube_downloader_pro.services.archive_service import ArchiveService
from youtube_downloader_pro.services.history_service import HistoryService
from youtube_downloader_pro.services.settings_service import SettingsService


def test_settings_round_trip_and_corruption(settings, tmp_path):
    service = SettingsService(tmp_path / "data" / "settings.json")
    expected = replace(
        settings, theme="light", audio_format="flac", subtitle_languages=("en", "tr")
    )
    service.save(expected)
    assert SettingsService(service.path).load() == expected
    assert not list(service.path.parent.glob("*.tmp"))
    service.path.write_text('{"parallel_downloads": 99}', encoding="utf-8")
    assert service.load().parallel_downloads == 3
    assert service.warning
    assert "99" in service.path.read_text()


def test_history_round_trip_filters_and_clear(settings, tmp_path):
    history = HistoryService(tmp_path / "history.sqlite3")
    item = DownloadItem(
        "https://example.com/a",
        "100% original",
        DownloadOptions(settings),
        status=Status.COMPLETED,
        output_file=str(tmp_path / "a.mp4"),
        downloaded_bytes=42,
    )
    history.record(item)
    row = HistoryService(history.path).search("100%", "Completed", "video")[0]
    assert row["file_size"] == 42
    assert history.retry_options(row).settings == settings
    assert history.retry_options(row).download_again
    assert history.search(status="Failed") == []
    assert history.search(query="' OR 1=1 --") == []
    assert history.search(since="2999-01-01") == []
    history.clear()
    assert history.search() == []


def test_archive_is_independent_of_history(tmp_path):
    archive = ArchiveService(tmp_path)
    assert archive.lookup("https://example.com/a") is None
    archive.record("https://example.com/a", "generic a", "/media/a.mp4")
    assert ArchiveService(tmp_path).lookup("https://example.com/a") == "/media/a.mp4"
    assert (tmp_path / "download-archive.txt").read_text() == "generic a\n"


def test_concurrent_history_writes_are_not_lost(settings, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    history = HistoryService(tmp_path / "history.sqlite3")
    items = [
        DownloadItem(
            f"https://example.com/{i}",
            f"Own media {i}",
            DownloadOptions(settings),
            status=Status.COMPLETED,
        )
        for i in range(30)
    ]
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(history.record, items))
    assert len(history.search()) == 30
