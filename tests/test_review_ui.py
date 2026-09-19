"""Regression coverage for the current Qodo correctness findings."""

import threading
import time
from collections import Counter
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QNetworkRequest
from PySide6.QtWidgets import QApplication

from youtube_downloader_pro.models.download_item import DownloadItem, DownloadOptions
from youtube_downloader_pro.services.settings_service import SettingsService
from youtube_downloader_pro.ui.main_window import MainWindow
from youtube_downloader_pro.ui.widgets.media_preview import ThumbnailLoader
from youtube_downloader_pro.ui.widgets.playlist_selector import PlaylistSelector


def pump(app, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, "Qt did not reach the expected state"
        time.sleep(0.005)


@pytest.fixture
def window(app, tmp_path, settings):
    SettingsService(tmp_path / "settings.json").save(settings)
    widget = MainWindow(tmp_path)
    widget.show()
    app.processEvents()
    pump(app, lambda: not widget.tasks)
    yield widget
    widget.close()
    pump(app, lambda: widget.ready_to_close)


def test_saved_quality_applies_now_without_resetting_analyzed_media(window, app):
    media = {
        "url": "https://example.com/owned",
        "title": "Own media",
        "formats": [{"format_id": "hi", "height": 1080}, {"format_id": "lo", "height": 720}],
    }
    window.home.set_media(media)
    for quality in ("1080p", "720p", "2160p", "Best Available"):
        window.settings_page.controls["default_quality"].setCurrentText(quality)
        window.settings_page._save()
        pump(
            app,
            lambda quality=quality: window.settings.default_quality == quality and not window.tasks,
        )
        assert window.home.quality.currentText() == (
            "Best Available" if quality == "2160p" else quality
        )
        assert window.home.media is media
        assert window.home.options().quality == window.home.quality.currentText()
    window.home.quality.setCurrentText("720p")
    window._save_settings(replace(window.settings, language="en", theme="light"))
    pump(app, lambda: not window.tasks)
    assert window.home.quality.currentText() == "720p"


def test_internal_queue_and_history_copies_do_not_trigger_clipboard_banner(window, app):
    window.settings = replace(window.settings, clipboard_monitoring=True)
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    key = window.manager.add(DownloadItem(url, "Own media", DownloadOptions(window.settings)))
    window._queue_action("copy_url", key)
    app.processEvents()
    assert QApplication.clipboard().text() == url
    assert not window.clip_banner.isVisible()
    # Delayed clipboard notifications from the same internal copy are suppressed too.
    window._clipboard_changed()
    assert not window.clip_banner.isVisible()
    history_url = "https://youtu.be/lmnopqrstuv"
    window._history_action("copy_url", {"source_url": history_url})
    app.processEvents()
    assert QApplication.clipboard().text() == history_url
    assert not window.clip_banner.isVisible()
    external = "https://vimeo.com/12345678"
    QApplication.clipboard().setText(external)
    pump(app, lambda: window.clip_banner.isVisible())
    assert window.clip_url == external


def test_repeated_playlist_occurrences_survive_pages_reopening_and_queueing(window):
    url = "https://example.com/owned"
    first = {
        "title": "Repeated media",
        "url": "https://example.com/list",
        "is_playlist": True,
        "entries": [
            {"url": url, "title": "First", "playlist_index": 1},
            {"url": url, "title": "Second", "playlist_index": 2},
        ],
        "start": 1,
        "count": 101,
        "has_more": True,
    }
    later = first | {
        "start": 101,
        "has_more": False,
        "entries": [{"url": url, "title": "Again", "playlist_index": 101}],
    }
    dialog = PlaylistSelector(first, [], window)
    dialog._select(True)
    dialog._remember()
    dialog.set_page(later)
    assert dialog.list.item(0).checkState() == Qt.CheckState.Unchecked
    dialog._select(True)
    dialog._remember()
    dialog.set_page(first)
    dialog.list.item(0).setCheckState(Qt.CheckState.Unchecked)
    dialog.accept()
    selected = list(dialog.selected.values())
    assert sorted(item["playlist_index"] for item in selected) == [2, 101]
    reopened = PlaylistSelector(first, selected, window)
    assert reopened.list.item(0).checkState() == Qt.CheckState.Unchecked
    assert reopened.list.item(1).checkState() == Qt.CheckState.Checked
    reopened.set_page(later)
    assert reopened.list.item(0).checkState() == Qt.CheckState.Checked
    window.home.set_media(first)
    window.home.selected_entries = selected
    assert window._add_media()
    items = window.manager.snapshot()
    assert len(items) == 2 and len({item.id for item in items}) == 2
    assert [item.url for item in items] == [url, url]
    assert sorted(item.options.playlist_index for item in items) == [2, 101]
    dialog.close()
    reopened.close()


@pytest.fixture
def redirects(tmp_path, app):
    image = QImage(80, 48, QImage.Format.Format_RGB32)
    image.fill(0x336699)
    path = tmp_path / "cover.png"
    assert image.save(str(path))
    contents = path.read_bytes()
    hits = Counter()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits[self.path] += 1
            if self.path in ("/first", "/second", "/loop"):
                self.send_response(302)
                self.send_header(
                    "Location",
                    {"/first": "second", "/second": "/cover.png", "/loop": "/loop"}[self.path],
                )
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(contents)))
                self.end_headers()
                self.wfile.write(contents)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", hits
    server.shutdown()
    server.server_close()
    thread.join(3)


def test_redirected_thumbnail_loads_and_caches_under_original_url(app, redirects):
    host, hits = redirects
    loader = ThumbnailLoader()
    requests = []
    original = loader.network.get

    def capture(request):
        requests.append(request)
        return original(request)

    loader.network.get = capture
    url = host + "/first"
    try:
        loader.get(url)
        pump(app, lambda: url in loader.cache)
        assert not loader.get(url).isNull()
        assert hits == Counter({"/first": 1, "/second": 1, "/cover.png": 1})
        assert loader.active == 0 and not loader.pending
        assert requests[0].attribute(QNetworkRequest.Attribute.RedirectPolicyAttribute) == (
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy
        )
        assert requests[0].maximumRedirectsAllowed() == 5
    finally:
        loader.shutdown()
        pump(app, lambda: loader.idle)


def test_thumbnail_redirect_loop_is_bounded_and_releases_request_slot(app, redirects):
    host, hits = redirects
    loader = ThumbnailLoader()
    url = host + "/loop"
    try:
        loader.get(url)
        pump(app, lambda: url in loader.cache)
        assert loader.get(url).isNull()
        assert hits["/loop"] <= 6
        assert loader.active == 0 and not loader.pending
        loader.get(host + "/cover.png")
        pump(app, lambda: host + "/cover.png" in loader.cache)
        assert not loader.get(host + "/cover.png").isNull()
    finally:
        loader.shutdown()
        pump(app, lambda: loader.idle)
