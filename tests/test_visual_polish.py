"""Presentation changes preserve the existing options, actions, and live translations."""

import time
from dataclasses import replace

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QPushButton

from youtube_downloader_pro.i18n import tr
from youtube_downloader_pro.models.download_item import DownloadItem, DownloadOptions
from youtube_downloader_pro.models.download_status import DownloadStatus as Status
from youtube_downloader_pro.services.settings_service import SettingsService
from youtube_downloader_pro.ui.localization import install_qt_language
from youtube_downloader_pro.ui.main_window import MainWindow
from youtube_downloader_pro.ui.pages.home_page import HomePage
from youtube_downloader_pro.ui.pages.queue_page import QueuePage
from youtube_downloader_pro.ui.pages.settings_page import SettingsPage
from youtube_downloader_pro.ui.widgets.media_preview import ThumbnailLoader

MEDIA = {
    "url": "https://example.org/own",
    "title": "A short film",
    "duration": 180,
    "formats": [
        {"format_id": "v2160", "height": 2160, "ext": "mp4"},
        {"format_id": "v1080", "height": 1080, "ext": "mp4"},
    ],
    "subtitles": ["en", "tr"],
    "is_playlist": False,
}


def test_simple_home_and_advanced_options_share_real_values(app, settings):
    install_qt_language(app, "en")
    loader = ThumbnailLoader()
    home = HomePage(settings, loader)
    home.resize(900, 700)
    home.show()
    try:
        home.set_media(MEDIA)
        app.processEvents()
        assert home.mode_tabs.count() == 2
        assert not home.advanced.isVisible() and not home.custom.isVisible()
        assert home.audio_quick.count() == 2
        assert home.quality.findText("720p") == -1
        home.quality.setCurrentText("2160p")
        assert home.quality.itemText(home.quality.currentIndex()) == "4K"
        assert home.options().quality == "2160p"
        home.mode_tabs.setCurrentIndex(1)
        home.audio_quick.setCurrentText("m4a")
        assert home.options().settings.audio_format == "m4a"
        assert home.options().mode == "audio"
        home.advanced_toggle.click()
        for codec in ("opus", "flac", "wav"):
            home.audio_format.setCurrentText(codec)
            assert home.audio_quick.currentText() == codec
            assert home.options().settings.audio_format == codec
            assert home.bitrate.isEnabled() == (codec == "opus")
        home.mode.setCurrentText("Custom")
        home.custom.setEditText("bestvideo+bestaudio/best")
        assert home.mode_tabs.count() == 3 and home.custom.isVisible()
        assert home.options().custom_format == "bestvideo+bestaudio/best"
        for code in ("tr", "en"):
            install_qt_language(app, code)
            assert home.advanced_toggle.text() == tr("Advanced")
            assert home.mode_tabs.tabText(2) == tr("Custom")
            assert home.custom.currentText() == "bestvideo+bestaudio/best"
        home.mode_tabs.setCurrentIndex(0)
        assert home.mode_tabs.count() == 2 and home.options().mode == "video"
        home.set_busy(True)
        assert home.analyze_button.text() == tr("Analyzing…")
        assert not home.add_button.isEnabled()
        home.set_busy(False)
        assert home.analyze_button.text() == tr("Analyze")
        assert home.add_button.isEnabled()
    finally:
        home.close()
        loader.shutdown()


def test_download_actions_follow_selection_without_resetting_rows(app, settings):
    loader = ThumbnailLoader()
    page = QueuePage(loader)
    page.show()
    item = DownloadItem("https://example.org/own", "Own media", DownloadOptions(settings))
    page.model.update_item(item)
    page.table.selectRow(0)
    resets = QSignalSpy(page.model.modelReset)
    actions = QSignalSpy(page.action)
    try:
        for status, expected in (
            (Status.DOWNLOADING, {"cancel"}),
            (Status.FAILED, {"retry"}),
            (Status.COMPLETED, {"open_file", "open_folder"}),
        ):
            page.model.update_item(replace(item, status=status, output_file="C:/media/own.mp4"))
            assert {
                name for name, b in page.context_actions.items() if not b.isHidden()
            } == expected
            action = sorted(expected)[0]
            page.context_actions[action].click()
            assert actions.at(actions.count() - 1) == [action, item.id]
        assert resets.count() == 0 and page.model.rowCount() == 1
        assert not page.schedule_controls.isVisible()
    finally:
        page.close()
        loader.shutdown()


def test_settings_regrouping_preserves_every_value(app, settings):
    page = SettingsPage(settings)
    page.show()
    saved = QSignalSpy(page.save_requested)
    try:
        assert set(page.sections) == {"General", "Download", "Media", "Advanced"}
        assert not page.sections["Advanced"].isVisible()
        assert set(page.controls) == set(settings.__dataclass_fields__)
        page.advanced_toggle.click()
        assert page.controls["filename_template"].isVisible()
        page._save()
        assert saved.count() == 1 and saved.at(0)[0] == settings
    finally:
        page.close()


def test_small_layouts_keep_actions_reachable_in_both_languages(app, tmp_path, settings):
    SettingsService(tmp_path / "settings.json").save(replace(settings, language="en"))
    window = MainWindow(tmp_path)
    window.show()
    try:
        window.home.set_media(MEDIA)
        for width, height in ((760, 480), (1092, 600), (1120, 700), (1280, 900)):
            window.resize(width, height)
            for code in ("tr", "en"):
                install_qt_language(app, code)
                for index in range(5):
                    window.stack.setCurrentIndex(index)
                    app.processEvents()
                    assert window.width() == width and window.height() == height
                    for control in window.stack.currentWidget().findChildren(QPushButton):
                        if control.isVisible() and control.text():
                            assert control.width() >= control.sizeHint().width(), control.text()
                window.stack.setCurrentIndex(0)
                window.home.scroll.ensureWidgetVisible(window.home.add_button)
                app.processEvents()
                position = window.home.add_button.mapTo(
                    window.home.scroll.viewport(), window.home.add_button.rect().center()
                )
                assert window.home.scroll.viewport().rect().contains(position)
    finally:
        window.close()
        deadline = time.monotonic() + 10
        while not window.ready_to_close:
            app.processEvents()
            assert time.monotonic() < deadline
            time.sleep(0.01)
        install_qt_language(app, "en")
