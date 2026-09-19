import time
import wave
from dataclasses import replace

from PySide6.QtCore import Qt, QTimer

from youtube_downloader_pro.models.download_item import DownloadItem, DownloadOptions
from youtube_downloader_pro.models.download_status import DownloadStatus as Status
from youtube_downloader_pro.ui.main_window import MainWindow
from youtube_downloader_pro.ui.theme import apply_theme
from youtube_downloader_pro.ui.widgets.playlist_selector import PlaylistSelector


def pump(app, predicate, timeout=5):
    end = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() > end:
            raise AssertionError("UI did not reach expected state")
        time.sleep(0.005)


def test_ui_preview_queue_filter_themes_and_shutdown(app, tmp_path, settings):
    window = MainWindow(tmp_path)
    window.settings = replace(settings, notifications=False)
    window.home.apply_settings(window.settings)
    window.show()
    media = {
        "url": "https://example.com/own",
        "title": "<b>My own video</b>",
        "duration": 100,
        "formats": [{"format_id": "137", "height": 1080, "ext": "mp4"}],
        "subtitles": ["en", "tr"],
        "is_playlist": False,
    }
    window.home.set_media(media)
    assert window.manager.snapshot() == []  # analysis never downloads or enqueues
    assert window.home.preview.title.textFormat() == Qt.TextFormat.PlainText
    window._add_media()
    pump(app, lambda: window.queue.model.rowCount() == 1)
    window.queue.search.setText("does not exist")
    pump(app, lambda: window.queue.proxy.rowCount() == 0)
    window.queue.search.clear()
    pump(app, lambda: window.queue.proxy.rowCount() == 1)
    for theme in ("light", "dark", "system"):
        apply_theme(app, theme)
        app.processEvents()
    window._save_settings(replace(window.settings, mini_always_on_top=False))
    pump(app, lambda: not window.settings.mini_always_on_top)
    assert not window.mini.top.isChecked()
    assert not window.settings_page.controls["mini_always_on_top"].isChecked()
    assert not window.mini.isVisible()
    window._show_mini()
    assert window.mini.isVisible()
    window._restore()
    window.close()
    pump(app, lambda: window.ready_to_close)
    assert window.manager.idle


def test_large_queue_remains_event_driven(app, settings):
    from youtube_downloader_pro.ui.pages.queue_page import QueuePage
    from youtube_downloader_pro.ui.widgets.media_preview import ThumbnailLoader

    loader = ThumbnailLoader()
    page = QueuePage(loader)
    options = DownloadOptions(settings)
    for i in range(3000):
        page.model.update_item(DownloadItem(f"https://example.com/{i}", f"Video {i}", options))
    page.show()
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(1))
    pump(app, lambda: bool(ticks))
    page.filter.setCurrentText(Status.COMPLETED.value)
    assert page.proxy.rowCount() == 0
    page.close()
    loader.shutdown()


def test_playlist_keeps_selection_across_pages(app):
    first = {
        "title": "List",
        "entries": [{"url": "https://example.com/1", "title": "One"}],
        "start": 1,
        "count": 101,
        "has_more": True,
    }
    dialog = PlaylistSelector(first, [])
    dialog._select(True)
    dialog._remember()
    dialog.set_page(
        first
        | {
            "entries": [{"url": "https://example.com/101", "title": "Last"}],
            "start": 101,
            "has_more": False,
        }
    )
    dialog._select(True)
    dialog.accept()
    assert len(dialog.selected) == 2


def test_ui_connected_to_real_engine(app, local_media, tmp_path, settings):
    directory, host = local_media
    window = MainWindow(tmp_path / "app-data")
    window.settings = replace(settings, notifications=False)
    window.home.apply_settings(window.settings)
    window.show()
    try:
        window._analyze(host + "/tone.wav")
        pump(app, lambda: window.home.media is not None, timeout=20)
        assert window.home.media["formats"]
        assert window.manager.snapshot() == []
        window.home.mode.setCurrentText("Custom")
        window.home.custom.setCurrentText("best")
        window.home.add_button.click()
        pump(app, lambda: window.manager.idle, timeout=20)
        rows = window.manager.snapshot()
        assert len(rows) == 1 and rows[0].status == Status.COMPLETED
        # FFmpeg may add metadata chunks; compare decoded PCM, not the WAV header.
        with (
            wave.open(rows[0].output_file, "rb") as actual,
            wave.open(str(directory / "tone.wav"), "rb") as expected,
        ):
            assert actual.getparams() == expected.getparams()
            assert actual.readframes(actual.getnframes()) == expected.readframes(
                expected.getnframes()
            )
        assert window.history.search()[0]["status"] == "Completed"
        pump(app, lambda: window.queue.model.items[0].progress == 100)
        # History retry is a real start action and must preserve the first output.
        first_output = rows[0].output_file
        window._history_action("retry", window.history.search()[0])
        pump(app, lambda: window.manager.idle, timeout=20)
        retried = window.manager.snapshot()
        assert len(retried) == 2 and retried[1].status == Status.COMPLETED
        assert retried[1].output_file != first_output
    finally:
        window.close()
        pump(app, lambda: window.ready_to_close)
