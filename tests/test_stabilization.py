import ast
import threading
import time
from dataclasses import replace
from pathlib import Path
from string import Formatter

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage

from youtube_downloader_pro.i18n import set_language, system_language, tr, translate_message
from youtube_downloader_pro.i18n.translator import catalog
from youtube_downloader_pro.models.download_item import DownloadItem, DownloadOptions
from youtube_downloader_pro.models.download_status import DownloadStatus as Status
from youtube_downloader_pro.services.history_service import HistoryService
from youtube_downloader_pro.services.settings_service import SettingsService
from youtube_downloader_pro.ui.events import UiEvents
from youtube_downloader_pro.ui.main_window import MainWindow
from youtube_downloader_pro.ui.widgets.common import ChoiceCombo
from youtube_downloader_pro.ui.widgets.media_preview import DecodeTask, ThumbnailLoader


def pump(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline
        time.sleep(0.005)


@pytest.fixture(autouse=True)
def restore_language():
    yield
    set_language("en")


def test_catalog_coverage_and_parameters():
    english, turkish = catalog("en"), catalog("tr")
    assert english and english.keys() == turkish.keys()
    for key in english:

        def fields(text):
            return {field for _, field, _, _ in Formatter().parse(text) if field}

        assert fields(english[key]) == fields(turkish[key]), key
        assert turkish[key].strip()
    for path in Path("youtube_downloader_pro").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"tr", "label", "button", "check", "ValidationError"}:
                    argument = node.args[0] if node.args else None
                elif node.func.id == "DownloadError":
                    argument = node.args[1] if len(node.args) > 1 else None
                else:
                    continue
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    text = argument.value
                    if text and not text.startswith("YouTube"):
                        assert text in english, (path, node.lineno, text)


def test_language_fallback_and_engine_messages(monkeypatch):
    set_language("tr")
    assert tr("Settings") == "Ayarlar"
    assert translate_message("Retrying 2/3 shortly…") == "Birazdan yeniden denenecek (2/3)…"
    monkeypatch.delitem(catalog("tr"), "Settings")
    assert tr("Settings") == "Settings"
    monkeypatch.setitem(catalog("tr"), "Save to {folder}", "{missing}")
    assert tr("Save to {folder}", folder="C:/media") == "Save to C:/media"
    set_language("unknown")
    assert tr("Settings") == "Settings"
    assert tr("Unknown upstream text") == "Unknown upstream text"


@pytest.mark.parametrize("locale,expected", [("tr_TR", "tr"), ("en_US", "en"), ("de_DE", "en")])
def test_system_language(locale, expected):
    assert system_language(locale) == expected


def test_live_language_persistence_and_qt_standard_controls(app, tmp_path, settings):
    service = SettingsService(tmp_path / "settings.json")
    service.save(replace(settings, language="tr"))
    first = MainWindow(tmp_path)
    try:
        assert first.home.analyze_button.text() == "Analiz Et"
        control = first.settings_page.controls["theme"]
        assert isinstance(control, ChoiceCombo)
        control.setCurrentText("dark")
        assert control.currentText() == "dark"
        assert control.itemText(control.currentIndex()) == "Koyu"
        assert QCoreApplication.translate("QLineEdit", "&Undo") != "&Undo"
        first._save_settings(replace(first.settings, language="en"))
        assert first.home.analyze_button.text() == "Analyze"
        pump(app, lambda: first.settings.language == "en")
    finally:
        first.close()
        pump(app, lambda: first.ready_to_close)
    second = MainWindow(tmp_path)
    try:
        assert second.ui_language == "en"
        assert second.home.analyze_button.text() == "Analyze"
        assert QCoreApplication.translate("QLineEdit", "&Undo") == "&Undo"
        assert service.load().language == "en"
    finally:
        second.close()
        pump(app, lambda: second.ready_to_close)


def test_progress_coalescing_order_removal_and_shutdown(app, settings):
    delivered = []
    events = UiEvents(delivered.append)
    item = DownloadItem(
        "https://example.org/a", "Own media", DownloadOptions(settings), status=Status.DOWNLOADING
    )
    events.submit({"type": "item", "item": item})
    for value in range(1, 100):
        events.submit({"type": "item", "item": replace(item, progress=value)})
    # Force a timer flush before queued immediate signals: stale initial state must be ignored.
    events.flush()
    app.processEvents()
    assert len(delivered) == 1 and delivered[-1]["item"].progress == 99
    events.submit({"type": "item", "item": replace(item, status=Status.COMPLETED, progress=100)})
    events.submit({"type": "removed", "id": item.id})
    pump(app, lambda: delivered[-1]["type"] == "removed")
    assert delivered[-2]["item"].status == Status.COMPLETED
    events.deliver({"type": "item", "item": item, "_sequence": 1})
    assert delivered[-1]["type"] == "removed"
    events.shutdown()
    events.submit({"type": "item", "item": item})
    app.processEvents()
    assert not events.timer.isActive() and not events.buffer.pending


def test_thumbnail_cache_and_failed_decode_shutdown(app, local_media):
    directory, host = local_media
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(0x336699)
    assert image.save(str(directory / "cover.png"))
    loader = ThumbnailLoader()
    url = host + "/cover.png"
    for _ in range(30):
        loader.get(url)
    assert loader.active == 1
    pump(app, lambda: url in loader.cache)
    assert not loader.get(url).isNull()
    assert loader.get(url).width() <= 80
    assert loader.get(url, (192, 108)).width() <= 192
    assert loader.active == 0
    invalid = host + "/tone.wav"
    loader.get(invalid)
    loader.shutdown()
    pump(app, lambda: loader.idle)


def test_decode_exception_still_completes(monkeypatch):
    from youtube_downloader_pro.ui.widgets import media_preview

    class BrokenBuffer:
        def __init__(self):
            raise RuntimeError("decoder failure")

    class Completion:
        result = None

        def emit(self, *values):
            self.result = values

    completion = Completion()
    monkeypatch.setattr(media_preview, "QBuffer", BrokenBuffer)
    DecodeTask("image", b"invalid", completion).run()
    assert completion.result == ("image", {})


def test_history_pagination_and_format_filter(tmp_path, settings):
    history = HistoryService(tmp_path / "history.sqlite3")
    for i in range(105):
        history.record(
            DownloadItem(
                f"https://example.org/{i}",
                f"Media {i}",
                DownloadOptions(settings),
                status=Status.COMPLETED,
            )
        )
    first = history.search(limit=100, format_filter="mp4")
    second = history.search(limit=100, offset=100, format_filter="mp4")
    assert len(first) == 100 and len(second) == 5
    assert not {row["id"] for row in first} & {row["id"] for row in second}
    assert not history.search(format_filter="mp3")


def test_background_work_is_off_ui_thread_and_busy_analysis_recovers(app, tmp_path):
    window = MainWindow(tmp_path)
    main_thread = threading.get_ident()
    results = []
    try:
        window._submit(
            "thread-test", threading.get_ident, lambda value, error: results.append(value)
        )
        pump(app, lambda: bool(results))
        assert results[0] != main_thread
        pump(app, lambda: not window.tasks)
        # Saturation must restore the Analyze control, not leave the page stuck busy.
        window.tasks = {str(i): None for i in range(8)}
        window._analyze("https://example.org/a")
        assert window.home.analyze_button.isEnabled()
        window.tasks.clear()
    finally:
        window.tasks = {key: future for key, future in window.tasks.items() if future is not None}
        window.close()
        pump(app, lambda: window.ready_to_close)
