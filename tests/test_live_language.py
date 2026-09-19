"""Live Qt retranslation must preserve the running application's state."""

import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPersistentModelIndex, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMenu, QPushButton
from shiboken6 import isValid

from youtube_downloader_pro.i18n import language, tr
from youtube_downloader_pro.i18n.translator import catalog
from youtube_downloader_pro.models.download_item import DownloadItem, DownloadOptions
from youtube_downloader_pro.models.download_status import DownloadStatus as Status
from youtube_downloader_pro.services.settings_service import SettingsService
from youtube_downloader_pro.ui.localization import install_qt_language, language_events
from youtube_downloader_pro.ui.main_window import MainWindow
from youtube_downloader_pro.ui.widgets.common import Banner, button, combo, label
from youtube_downloader_pro.ui.widgets.playlist_selector import PlaylistSelector


def pump(app, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, "Qt did not reach the expected state"
        time.sleep(0.005)


def dispose(app, window):
    window.close()
    pump(app, lambda: window.ready_to_close)
    window.mini.deleteLater()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def window(app, tmp_path, settings):
    SettingsService(tmp_path / "settings.json").save(replace(settings, language="tr"))
    widget = MainWindow(tmp_path)
    widget.show()
    app.processEvents()  # Dispatch startup checks before waiting for them.
    pump(app, lambda: not widget.tasks)
    try:
        yield widget
    finally:
        dispose(app, widget)
        install_qt_language(app, "en")


def save_language(window, code):
    window.settings_page.controls["language"].setCurrentText(code)
    save = next(
        b for b in window.settings_page.findChildren(QPushButton) if b.text() == tr("Save settings")
    )
    save.click()
    # Synchronous retranslation, without processing a queued save completion or restarting.
    assert window.ui_language == code
    key = "Analyze" if window.home.analyze_button.isEnabled() else "Analyzing…"
    assert window.home.analyze_button.text() == catalog(code).get(key, key)


def test_all_existing_pages_retranslate_without_resetting_media_or_models(app, window):
    media = {
        "url": "https://example.org/own",
        "title": "Home",
        "uploader": "Settings",
        "duration": 120,
        "estimated_size": 2048,
        "formats": [
            {"format_id": "137", "height": 1080, "ext": "mp4", "vcodec": "avc1"},
            {"format_id": "140", "height": None, "ext": "m4a", "acodec": "aac"},
        ],
        "subtitles": ["tr"],
        "automatic_captions": ["en"],
        "is_playlist": False,
    }
    home = window.home
    home.set_media(media)
    home.mode.setCurrentText("Audio")
    home.quality.setCurrentText("1080p")
    home.container.setCurrentText("webm")
    home.audio_format.setCurrentText("opus")
    home.bitrate.setCurrentText("256")
    home.custom.setEditText("bestvideo+bestaudio/best")
    home.subtitle_mode.setCurrentText("manual")
    home.subtitle_format.setCurrentText("vtt")
    home.languages.item(0).setCheckState(Qt.CheckState.Unchecked)
    home.flags["write_description"].setChecked(True)
    home.selected_entries = [{"url": "https://example.org/selected", "title": "Download"}]
    selected_entries = home.selected_entries
    choices = home.options()
    image = QPixmap(192, 108)
    image.fill(Qt.GlobalColor.blue)
    home.preview.image.setPixmap(image)
    image_key = home.preview.image.pixmap().cacheKey()
    home.set_busy(True)
    analysis_token = window.analysis_cancel
    window.queue.schedule_label.setText(tr("Scheduled for {time}", time="20:15"))
    window.queue.time.setText("20:15")
    window.mini.count.setText(tr("{active} active · {total} in queue", active=1, total=2))
    window.about.set_versions({"Application": "7.0.0", "Operating system": "Windows"})
    window.about.ffmpeg.setText(
        tr(
            "FFmpeg: {version}\nSource: {source}\nffprobe: {probe}",
            version="9.0",
            source=tr("PATH"),
            probe=tr("Ready"),
        )
    )
    item = DownloadItem(media["url"], "Home", choices, status=Status.COMPLETED, progress=100)
    window.history.record(item)
    rows = window.history.search()
    history = window.history_page
    history.set_rows(rows)
    history.table.selectRow(0)
    history.offset = 100
    history_index = QPersistentModelIndex(history.model.index(0, 0))
    window.manager.add(replace(item, status=Status.WAITING, progress=0))
    pump(app, lambda: window.queue.model.rowCount() == 1)
    window.queue.table.selectRow(0)
    queue_index = QPersistentModelIndex(window.queue.proxy.index(0, 0))
    engine, executor = window.manager, window.manager._executor
    queued = engine.snapshot()
    queue_reset, history_reset = (
        QSignalSpy(window.queue.model.modelReset),
        QSignalSpy(history.model.modelReset),
    )
    history_search = QSignalSpy(history.search_requested)
    changed = QSignalSpy(window.queue.model.dataChanged)
    window.stack.setCurrentIndex(3)
    for code in ("en", "tr", "en"):
        save_language(window, code)
        pump(app, lambda: not window.tasks)
        expected = catalog(code)
        assert language() == code
        assert [window.navigation.button(i).text() for i in range(5)] == [
            expected[k] for k in ("Home", "Downloads", "History", "Settings", "About")
        ]
        assert window.navigation.button(0).toolTip() == expected["Home"]
        assert window.stack.currentIndex() == 3
        assert home.url.placeholderText() == expected["Paste a video or playlist URL"]
        assert home.url.accessibleName() == expected["Media link"]
        assert home.mode_tabs.tabText(1) == expected["Audio"]
        assert home.custom.lineEdit().placeholderText() == expected["Format ID or custom selector"]
        assert expected["Automatic"] in home.languages.item(0).text()
        assert expected["Manual"] in home.languages.item(1).text()
        assert expected["Audio"] in home.custom.itemData(1, Qt.ItemDataRole.ToolTipRole)
        assert expected["Video / audio"] in home.preview.meta.text()
        assert home.preview.title.text() == "Home" and "Settings" in home.preview.meta.text()
        assert home.preview.image.pixmap().cacheKey() == image_key
        assert not home.analyze_button.isEnabled() and not home.footer.isEnabled()
        assert home.media is media and home.selected_entries is selected_entries
        assert replace(home.options(), settings=choices.settings) == choices
        assert home.options().settings.audio_format == "opus"
        assert home.options().settings.audio_bitrate == 256
        assert home.options().settings.subtitle_format == "vtt"
        assert home.options().settings.write_description
        assert home.languages.item(0).checkState() == Qt.CheckState.Unchecked
        assert home.custom.currentText() == "bestvideo+bestaudio/best"
        assert window.analysis_cancel is analysis_token and not analysis_token.is_set()
        assert window.manager is engine and engine._executor is executor
        assert engine.snapshot() == queued
        assert history.rows is rows and history.offset == 100
        assert history_index.isValid() and history.table.currentIndex().row() == 0
        assert expected["Completed"] in history_index.data()
        assert queue_index.isValid() and window.queue.table.currentIndex().row() == 0
        assert expected["Waiting"] in queue_index.data()
        assert history.search.placeholderText() == expected["Search by title"]
        assert window.queue.search.placeholderText() == expected["Search downloads"]
        assert window.queue.schedule_label.text() == tr("Scheduled for {time}", time="20:15")
        assert window.queue.time.text() == "20:15"
        assert window.mini.windowTitle().endswith(expected["Mini Mode"])
        assert window.mini.count.text() == tr(
            "{active} active · {total} in queue", active=1, total=2
        )
        assert expected["Operating system"] in window.about.system.text()
        assert expected["Ready"] in window.about.ffmpeg.text()
        assert window.banner.text.text() == expected["Settings saved."]
        for page, title in (
            (home, "Download media"),
            (window.queue, "Downloads"),
            (history, "History"),
            (window.settings_page, "Settings"),
            (window.about, "About"),
        ):
            assert expected[title] in [w.text() for w in page.findChildren(QLabel)]
        for menu in window.queue.findChildren(QMenu):
            assert [a.text() for a in menu.actions()] == [
                expected[k] for k in ("Retry Failed", "Clear Completed", "Cancel All")
            ]
        assert expected["No active downloads yet."] in [
            w.text() for w in window.queue.empty.findChildren(QLabel)
        ]
        assert window.settings_service.load().language == code
    assert changed.count() == 3 and not queue_reset.count() and not history_reset.count()
    assert not history_search.count() and len(window.history.search()) == 1


def test_language_switch_preserves_a_running_download(app, window):
    release = threading.Event()
    tokens = []

    def controlled_worker(_operation, payload, cancel, emit):
        tokens.append(cancel)
        emit(
            {"type": "progress", "downloaded_bytes": 25, "total_bytes": 100, "speed": 5, "eta": 15}
        )
        assert release.wait(10)
        output = Path(payload["staging"]) / "own.txt"
        output.write_text("test output")
        return {"output_file": str(output)}

    window.manager._runner = controlled_worker
    item = DownloadItem("https://example.org/active", "Own media", DownloadOptions(window.settings))
    window.manager.add(item)
    window.manager.start()
    try:
        pump(
            app,
            lambda: bool(window.queue.model.items) and window.queue.model.items[0].progress == 25,
        )
        snapshot = window.manager.snapshot()
        executor = window.manager._executor
        for code in ("en", "tr"):
            save_language(window, code)
            pump(app, lambda: not window.tasks)
            assert not window.manager.idle and not tokens[0].is_set()
            assert window.manager.snapshot() == snapshot
            assert window.manager._executor is executor
            assert catalog(code)["Downloading"] in window.queue.model.index(0, 0).data()
        release.set()
        pump(app, lambda: window.manager.idle)
        assert window.manager.snapshot()[0].status == Status.COMPLETED
    finally:
        release.set()


@pytest.mark.parametrize("code", ["en", "tr"])
def test_save_then_immediate_close_persists_even_with_busy_analysis(app, window, code, monkeypatch):
    release = threading.Event()
    save_started = threading.Event()
    original_save = window.settings_service.save
    calls = []

    def delayed_save(settings):
        save_started.set()
        assert release.wait(10)
        calls.append(settings.language)
        original_save(settings)

    monkeypatch.setattr(window.settings_service, "save", delayed_save)
    try:
        # Network workers are occupied; saves must still start and update the UI immediately.
        for _ in range(2):
            window._submit("busy-analysis", lambda: release.wait(10), lambda *_: None)
        for selected in (code, "tr" if code == "en" else "en", code):
            save_language(window, selected)
        assert save_started.wait(2)
        window.close()
        assert not window.ready_to_close
        release.set()
        pump(app, lambda: window.ready_to_close)
        assert calls == [code, "tr" if code == "en" else "en", code]
        assert window.settings_service.load().language == code
        reopened = MainWindow(window.settings_service.path.parent)
        try:
            assert reopened.ui_language == code
            assert reopened.home.analyze_button.text() == catalog(code)["Analyze"]
        finally:
            dispose(app, reopened)
    finally:
        release.set()


def test_dynamic_widgets_dialogs_banners_and_fallback(app, window, monkeypatch):
    media = {
        "title": "Home",
        "entries": [{"url": "https://example.org/1", "title": "Settings"}],
        "start": 1,
        "count": None,
        "has_more": False,
    }
    save_language(window, "en")
    dialog = PlaylistSelector(media, [], window)
    dialog._select(True)
    dialog.open()
    notice = Banner()
    notice.show_message(
        tr("{status}: {title}", status=tr("Completed"), title="Home"), "Retrying 2/3 shortly…"
    )
    created = button("Analyze")
    raw_title = label("Home", translate=False)
    choice = combo(["dark", "light"], "light")
    choice_changes = QSignalSpy(choice.currentTextChanged)
    signals = QSignalSpy(language_events().languageChanged)
    try:
        for code in ("tr", "en"):
            save_language(window, code)
            assert dialog.windowTitle() == catalog(code)["Select playlist videos"]
            assert dialog.list.item(0).text() == "•   Settings"
            assert dialog.list.item(0).checkState() == Qt.CheckState.Checked
            assert catalog(code)["Unknown total"] in dialog.info.text()
            assert created.text() == catalog(code)["Analyze"]
            assert raw_title.text() == "Home"
            assert choice.currentText() == "light"
            assert choice.itemText(choice.currentIndex()) == catalog(code)["Light"]
            assert notice.text.text() == tr(
                "{status}: {title}", status=tr("Completed"), title="Home"
            )
            assert notice.details.text() == tr("Retrying {attempt}/3 shortly…", attempt=2)
            later = button("Retry")
            assert later.text() == catalog(code)["Retry"]
            later.deleteLater()
        assert signals.count() == 2 and not choice_changes.count()
        monkeypatch.delitem(catalog("tr"), "Analyze")
        monkeypatch.setitem(catalog("tr"), "Save to {folder}", "{missing}")
        path = label(tr("Save to {folder}", folder="C:/Türkçe/media"))
        save_language(window, "tr")
        assert created.text() == "Analyze"
        assert path.text() == "Save to C:/Türkçe/media"
        unknown = label("Uncatalogued external text")
        assert unknown.text() == "Uncatalogued external text"
        path.deleteLater()
        unknown.deleteLater()
        created.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not isValid(created)
        save_language(window, "en")  # Destroyed widgets must no longer receive callbacks.
    finally:
        dialog.close()
        for widget in (dialog, notice, raw_title, choice):
            widget.deleteLater()


def test_existing_folder_dialog_and_download_context_menu_retranslate(app, window, monkeypatch):
    def folder_exec(dialog):
        for code in ("en", "tr"):
            save_language(window, code)
            app.processEvents()
            assert dialog.windowTitle() == catalog(code)["Download folder"]
            assert QCoreApplication.translate("QLineEdit", "&Undo") == (
                "&Undo" if code == "en" else "&Geri Al"
            )
        return 0

    monkeypatch.setattr(QFileDialog, "exec", folder_exec)
    window.settings_page._choose_folder()
    item = DownloadItem("https://example.org/menu", "Own media", DownloadOptions(window.settings))
    window.queue.model.update_item(item)
    window._navigate(1)
    app.processEvents()
    actions = []
    window.queue.action.connect(lambda *args: actions.append(args))

    errors = []

    def inspect_menu():
        menu = QApplication.activePopupWidget()
        try:
            assert isinstance(menu, QMenu)
            for code in ("en", "tr"):
                save_language(window, code)
                assert menu.actions()[0].text() == catalog(code)["Cancel"]
                assert menu.actions()[4].text() == catalog(code)["Open File"]
            menu.actions()[-1].trigger()
        except Exception as error:
            errors.append(error)
        finally:
            if menu is not None:
                menu.close()

    QTimer.singleShot(0, inspect_menu)
    index = window.queue.proxy.index(0, 0)
    window.queue._menu(window.queue.table.visualRect(index).center())
    assert not errors
    assert actions == [("details", item.id)]
