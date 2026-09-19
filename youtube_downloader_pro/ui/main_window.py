import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from youtube_downloader_pro import APP_NAME, __version__
from youtube_downloader_pro.core.clipboard_service import ClipboardService
from youtube_downloader_pro.core.download_manager import DownloadManager
from youtube_downloader_pro.core.errors import CancelledError, classify_error
from youtube_downloader_pro.core.ffmpeg_manager import detect_ffmpeg
from youtube_downloader_pro.core.scheduler import Scheduler
from youtube_downloader_pro.core.worker import run_worker
from youtube_downloader_pro.i18n import language, tr
from youtube_downloader_pro.models.download_item import DownloadItem
from youtube_downloader_pro.models.download_status import DownloadStatus as Status
from youtube_downloader_pro.services.archive_service import ArchiveService
from youtube_downloader_pro.services.history_service import HistoryService
from youtube_downloader_pro.services.notification_service import NotificationService
from youtube_downloader_pro.services.settings_service import SettingsService
from youtube_downloader_pro.services.update_service import check_engine_version, versions
from youtube_downloader_pro.ui.design import NAV_HEIGHT, SIDEBAR_WIDTH
from youtube_downloader_pro.ui.events import UiEvents
from youtube_downloader_pro.ui.localization import bind_text, install_qt_language, watch_language
from youtube_downloader_pro.ui.pages.about_page import AboutPage
from youtube_downloader_pro.ui.pages.history_page import HistoryPage
from youtube_downloader_pro.ui.pages.home_page import HomePage
from youtube_downloader_pro.ui.pages.queue_page import QueuePage
from youtube_downloader_pro.ui.pages.settings_page import SettingsPage
from youtube_downloader_pro.ui.theme import apply_theme
from youtube_downloader_pro.ui.widgets.common import Banner, button, icon_label, label
from youtube_downloader_pro.ui.widgets.media_preview import ThumbnailLoader
from youtube_downloader_pro.ui.widgets.mini_window import MiniWindow
from youtube_downloader_pro.ui.widgets.playlist_selector import PlaylistSelector
from youtube_downloader_pro.utils.paths import logs_dir, open_path
from youtube_downloader_pro.utils.validators import validate_url

log = logging.getLogger(__name__)


class EventBridge(QObject):
    result = Signal(str, object, object)


class MainWindow(QMainWindow):
    """Qt coordinator; download work and filesystem operations belong to services."""

    def __init__(self, data_directory: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} · v{__version__}")
        available = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(min(760, available.width() - 32), min(480, available.height() - 32))
        self.resize(min(1120, available.width() - 32), min(760, available.height() - 32))
        self.log_directory = data_directory / "logs" if data_directory else logs_dir()
        self.settings_service = SettingsService(
            data_directory / "settings.json" if data_directory else None
        )
        self.settings = self.settings_service.load()
        self.ui_language = self.settings.language
        install_qt_language(QApplication.instance(), self.ui_language)
        apply_theme(QApplication.instance(), self.settings.theme)
        self.history = HistoryService(
            data_directory / "history.sqlite3" if data_directory else None
        )
        self.bridge = EventBridge(self)
        self.ui_events = UiEvents(self._engine_event, self)
        self.bridge.result.connect(self._task_result, Qt.ConnectionType.QueuedConnection)
        self.manager = DownloadManager(
            self.settings.parallel_downloads,
            self.ui_events.submit,
            self.history,
            ArchiveService(data_directory),
        )
        self.background = ThreadPoolExecutor(max_workers=2, thread_name_prefix="application")
        # Save in order, independently of potentially long network analysis tasks.
        self.settings_writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="settings")
        self.tasks: dict[str, Future] = {}
        self.callbacks: dict[str, object] = {}
        self.task_number = self.history_generation = 0
        self.analysis_cancel = threading.Event()
        self.scheduler = Scheduler()
        self.clipboard = ClipboardService()
        self.thumbnails = ThumbnailLoader(self)
        self.notifications = NotificationService(self)
        self.closing = self.ready_to_close = False
        self.notified: set[str] = set()
        self.last_notification = 0.0
        self.playlist: PlaylistSelector | None = None
        self._build_ui()
        self.mini = MiniWindow(self.settings.mini_always_on_top)
        self.mini.restore_requested.connect(self._restore)
        self.mini.analyze_requested.connect(self._mini_analyze)
        self.mini.top_changed.connect(
            lambda value: self._save_settings(replace(self.settings, mini_always_on_top=value))
        )
        self._connect_pages()
        watch_language(self, self.retranslate_ui)
        app = QApplication.instance()
        apply_theme(app, self.settings.theme)
        app.styleHints().colorSchemeChanged.connect(self._system_theme_changed)
        app.clipboard().dataChanged.connect(self._clipboard_changed)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        QTimer.singleShot(0, lambda: self._submit("ffmpeg", detect_ffmpeg, self._ffmpeg_result))
        if self.settings_service.warning:
            self.banner.show_message(self.settings_service.warning)
        QTimer.singleShot(0, lambda: self._submit("system", versions, self._system_ready))
        log.info("Application startup: %s", __version__)

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(8, 16, 8, 16)
        side.setSpacing(4)
        brand = QHBoxLayout()
        mark = icon_label("download", 24)
        brand.addWidget(mark)
        brand.addWidget(label("YouTube\nDownloader Pro", "brand"), 1)
        side.addLayout(brand)
        side.addSpacing(16)
        self.navigation = QButtonGroup(self)
        self.navigation.setExclusive(True)
        self.stack = QStackedWidget()
        self.home = HomePage(self.settings, self.thumbnails)
        self.queue = QueuePage(self.thumbnails)
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage(self.settings)
        self.about = AboutPage()
        for i, (name, symbol, page) in enumerate(
            zip(
                ["Home", "Downloads", "History", "Settings", "About"],
                ["home", "download", "history", "settings", "info"],
                [self.home, self.queue, self.history_page, self.settings_page, self.about],
                strict=True,
            )
        ):
            nav = button(name, icon_name=symbol)
            nav.setObjectName("nav")
            bind_text(nav, "setToolTip", name)
            nav.setCheckable(True)
            nav.setMinimumHeight(NAV_HEIGHT)
            self.navigation.addButton(nav, i)
            nav.clicked.connect(lambda _=False, index=i: self._navigate(index))
            side.addWidget(nav)
            self.stack.addWidget(page)
        self.navigation.button(0).setChecked(True)
        side.addStretch()
        mini_button = button("Mini Mode", self._show_mini, icon_name="mini")
        mini_button.setObjectName("quiet")
        side.addWidget(mini_button)
        side.addSpacing(16)
        self.engine_status = label("Checking…", "caption", True)
        side.addWidget(self.engine_status)
        side.addWidget(label(f"v{__version__}", "caption"))
        layout.addWidget(sidebar)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.banner = Banner()
        right.addWidget(self.banner)
        self.clip_banner = QFrame()
        self.clip_banner.setObjectName("banner")
        clip_layout = QHBoxLayout(self.clip_banner)
        clip_layout.addWidget(label("Media link detected", "section"), 1)
        clip_layout.addWidget(button("Analyze", self._analyze_clipboard))
        clip_layout.addWidget(button("Dismiss", self.clip_banner.hide))
        self.clip_banner.hide()
        self.clip_url = ""
        right.addWidget(self.clip_banner)
        right.addWidget(self.stack, 1)
        layout.addLayout(right, 1)
        self.setCentralWidget(central)

    def _system_ready(self, values, error) -> None:
        if error:
            self._failure(error)
        else:
            self.about.set_versions(values)
            self.settings_page.engine_version.setText(
                tr("yt-dlp version: {version}", version=values["yt-dlp"])
            )

    def _connect_pages(self) -> None:
        self.home.analyze_requested.connect(self._analyze)
        self.home.cancel_analysis.connect(lambda: self.analysis_cancel.set())
        self.home.add_requested.connect(self._add_media)
        self.home.download_requested.connect(self._download_now)
        self.home.playlist_requested.connect(self._select_playlist)
        self.queue.action.connect(self._queue_action)
        self.queue.start_requested.connect(self._start)
        self.queue.schedule_requested.connect(self._schedule)
        self.queue.cancel_schedule.connect(self._cancel_schedule)
        self.history_page.search_requested.connect(self._search_history)
        self.history_page.action.connect(self._history_action)
        self.history_page.clear_requested.connect(self._clear_history)
        self.settings_page.save_requested.connect(self._save_settings)
        self.settings_page.error.connect(self.banner.show_message)
        self.settings_page.open_logs.connect(self._open_logs)
        self.about.open_logs.connect(self._open_logs)
        self.about.check_version.connect(self._check_version)

    def _navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.navigation.button(index).setChecked(True)
        if index == 2:
            self.history_page.refresh()

    def _submit(self, name: str, operation, callback) -> None:
        if self.closing:
            return
        if name != "settings" and len(self.tasks) >= 8:
            callback(None, ValueError("Background tasks are busy. Please try again shortly."))
            return
        self.task_number += 1
        key = f"{name}-{self.task_number}"
        self.callbacks[key] = callback
        executor = self.settings_writer if name == "settings" else self.background
        future = executor.submit(operation)
        self.tasks[key] = future

        def done(result: Future) -> None:
            try:
                value, error = result.result(), None
            except Exception as exc:
                value, error = None, exc
            self.bridge.result.emit(key, value, error)

        future.add_done_callback(done)

    def _task_result(self, key: str, value, error) -> None:
        self.tasks.pop(key, None)
        callback = self.callbacks.pop(key, None)
        if callback and not self.closing:
            callback(value, error)

    def _failure(self, error: Exception) -> None:
        if isinstance(error, CancelledError):
            self.banner.show_message("Analysis cancelled.")
        else:
            log.warning("Background task failed: %s", error)
            self.banner.show_message(
                classify_error(error).message,
                tr("Open Logs in Settings for technical diagnostics."),
            )

    def _analyze(self, url: str) -> None:
        try:
            url = validate_url(url)
        except ValueError as exc:
            self.banner.show_message(str(exc))
            return
        if not self.home.analyze_button.isEnabled():
            return
        self.home.url.setText(url)
        self.home.set_busy(True)
        self.analysis_cancel.set()
        self.analysis_cancel = threading.Event()
        token = self.analysis_cancel
        self._submit(
            "analyze",
            lambda: run_worker("analyze", {"url": url}, token, self._analysis_event, timeout=120),
            self._analyzed,
        )

    def _analysis_event(self, event: dict) -> None:
        if event["type"] == "log":
            log.info("Analysis: %s", event["message"])

    def _analyzed(self, media, error) -> None:
        self.home.set_busy(False)
        if error:
            self._failure(error)
        else:
            self.home.set_media(media)
            self.banner.show_message(
                "Playlist analyzed. Select videos to add."
                if media.get("is_playlist")
                else "Link analyzed. Choose a format to start downloading."
            )

    def _select_playlist(self) -> None:
        media = self.home.media
        if media and media.get("is_playlist"):
            self.playlist = PlaylistSelector(media, self.home.selected_entries, self)
            self.playlist.page_requested.connect(self._playlist_page)
            self.playlist.accepted.connect(self._playlist_selected)
            self.playlist.rejected.connect(lambda: self.analysis_cancel.set())
            self.playlist.open()

    def _playlist_page(self, start: int) -> None:
        dialog = self.playlist
        self.analysis_cancel.set()
        self.analysis_cancel = threading.Event()
        token = self.analysis_cancel
        url = self.home.media["url"]

        def ready(media, error) -> None:
            if error:
                self._failure(error)
                dialog.set_page(dialog.media)
            elif dialog.isVisible():
                dialog.set_page(media)

        self._submit(
            "playlist",
            lambda: run_worker(
                "analyze",
                {"url": url, "start": start},
                token,
                self._analysis_event,
                120,
            ),
            ready,
        )

    def _playlist_selected(self) -> None:
        self.home.selected_entries = list(self.playlist.selected.values())
        self.home.playlist_button.setText(
            tr("{count} videos selected · Change selection", count=len(self.home.selected_entries))
        )

    def _add_media(self) -> bool:
        try:
            media = self.home.media
            if not media:
                return False
            options = self.home.options()
            entries = self.home.selected_entries if media.get("is_playlist") else [media]
            if not entries:
                self._select_playlist()
                return False
            for entry in entries:
                job_options = replace(
                    options,
                    playlist_index=entry.get("playlist_index"),
                    playlist_title=media["title"] if media.get("is_playlist") else "",
                )
                self.manager.add(
                    DownloadItem(
                        entry["url"],
                        entry["title"],
                        job_options,
                        thumbnail_url=entry.get("thumbnail", ""),
                        duration=entry.get("duration"),
                        estimated_size=entry.get("estimated_size"),
                    )
                )
            self._navigate(1)
            self.banner.show_message(
                tr("Added {count} item(s). Start now or choose a schedule.", count=len(entries))
            )
            return True
        except ValueError as exc:
            self.banner.show_message(str(exc))
        return False

    def _download_now(self) -> None:
        if self._add_media():
            self._start()

    def _start(self) -> None:
        self._cancel_schedule()
        self.manager.start()

    def _schedule(self, value: str) -> None:
        try:
            target = self.scheduler.schedule(value)
            self.queue.schedule_label.setText(
                tr("Scheduled for {time}", time=target.strftime("%d.%m, %H:%M"))
            )
        except ValueError as exc:
            self.banner.show_message(str(exc))

    def _cancel_schedule(self) -> None:
        self.scheduler.cancel()
        self.queue.schedule_label.setText(tr("Start when you are ready."))

    def _queue_action(self, action: str, key: str) -> None:
        if action in {"cancel_all", "clear_completed", "retry_failed"}:
            if action == "cancel_all":
                self._cancel_schedule()
            getattr(self.manager, action)()
            return
        item = next((item for item in self.manager.snapshot() if item.id == key), None)
        if not item:
            return
        if action in {"cancel", "remove"}:
            getattr(self.manager, action)(key)
        elif action in {"retry", "again"}:
            self.notified.discard(key)
            if item.status == Status.COMPLETED and action == "again":
                self.manager.add(
                    DownloadItem(
                        item.url,
                        item.title,
                        replace(item.options, download_again=True),
                        thumbnail_url=item.thumbnail_url,
                        duration=item.duration,
                    )
                )
            else:
                self.manager.retry(key, download_again=action == "again")
            self.manager.start()
        elif action == "copy_url":
            self._copy_url(item.url)
        elif action == "details":
            self.banner.show_message(
                item.message or item.status.value,
                tr(
                    "{error} · Attempt {attempt}/3. "
                    "Open Logs in Settings for technical diagnostics.",
                    error=item.error_code or tr("No error"),
                    attempt=item.attempt,
                ),
            )
        elif action in {"open_file", "open_folder"}:
            path = (
                Path(item.output_file)
                if item.output_file
                else Path(item.options.settings.download_folder)
            )
            if action == "open_file" and not item.output_file:
                self.banner.show_message("This item has no completed output file.")
            else:
                self._open(path.parent if action == "open_folder" and item.output_file else path)

    def _engine_event(self, event: dict) -> None:
        if self.closing:
            return
        if event["type"] == "item":
            item = event["item"]
            self.queue.model.update_item(item)
            if item.status.terminal and item.id not in self.notified:
                self.notified.add(item.id)
                self.banner.show_message(
                    tr("{status}: {title}", status=tr(item.status.value), title=item.title),
                    item.message,
                )
                if item.status in {Status.COMPLETED, Status.FAILED}:
                    now = time.monotonic()
                    if now - self.last_notification > 3:
                        self.notifications.notify(
                            tr("{status}: {title}", status=tr(item.status.value), title=item.title),
                            self.settings.notifications,
                            item.status == Status.FAILED,
                        )
                        self.last_notification = now
                if item.status == Status.COMPLETED and self.settings.auto_open_folder:
                    self._open(Path(item.output_file).parent)
        elif event["type"] == "removed":
            self.queue.model.remove_item(event["id"])
            self.notified.discard(event["id"])
        elif event["type"] == "warning":
            self.banner.show_message(event["message"])
        elif event["type"] == "queue_idle":
            items = self.manager.snapshot()
            completed = sum(item.status == Status.COMPLETED for item in items)
            failed = sum(item.status == Status.FAILED for item in items)
            cancelled = sum(item.status == Status.CANCELLED for item in items)
            waiting = sum(item.status == Status.WAITING for item in items)
            summary = tr(
                "Queue idle · {completed} completed · {failed} failed · "
                "{cancelled} cancelled · {waiting} waiting",
                completed=completed,
                failed=failed,
                cancelled=cancelled,
                waiting=waiting,
            )
            self.banner.show_message(summary)
            self.notifications.notify(summary, self.settings.notifications, bool(failed))
            if self.stack.currentIndex() == 2:
                self.history_page.refresh()

    def _search_history(self, parameters: dict) -> None:
        self.history_generation += 1
        generation = self.history_generation

        def ready(rows, error) -> None:
            if generation == self.history_generation:
                if error:
                    self._failure(error)
                else:
                    self.history_page.set_rows(rows)

        self._submit("history", lambda: self.history.search(**parameters), ready)

    def _history_action(self, action: str, row: dict) -> None:
        try:
            if action == "retry":
                self.manager.add(
                    DownloadItem(
                        row["source_url"],
                        row["title"],
                        self.history.retry_options(row),
                        thumbnail_url=row.get("thumbnail_url") or "",
                    )
                )
                self._navigate(1)
                self._start()
            elif action == "copy_url":
                self._copy_url(row["source_url"])
            elif row["output_file"]:
                path = Path(row["output_file"])
                self._open(path.parent if action == "open_folder" else path)
            else:
                self.banner.show_message("This history record has no output file.")
        except (ValueError, TypeError, KeyError) as exc:
            log.warning("History record could not be restored: %s", exc)
            self.banner.show_message(
                "This history record could not be restored.",
                tr("Open Logs in Settings for technical diagnostics."),
            )

    def _clear_history(self) -> None:
        def ready(_, error) -> None:
            if error:
                self._failure(error)
            else:
                self.history_page.refresh()
                self.banner.show_message("History cleared. Downloaded files are kept.")

        self._submit("history-clear", self.history.clear, ready)

    def _save_settings(self, settings) -> None:
        if self.closing:
            return
        if not self.manager.idle and settings.parallel_downloads != self.manager.workers:
            self.banner.show_message(
                "Wait for downloads to finish before changing parallel downloads."
            )
            return

        def ready(_, error) -> None:
            if error:
                self._failure(error)
                return
            if self.manager.idle and self.manager.workers != settings.parallel_downloads:
                self.manager.configure_workers(settings.parallel_downloads)
            self.settings = settings
            self.settings_page.settings = settings
            self.settings_page.controls["mini_always_on_top"].setChecked(
                settings.mini_always_on_top
            )
            self.mini.apply_top_preference(settings.mini_always_on_top)
            self.home.apply_settings(settings)
            apply_theme(QApplication.instance(), settings.theme)
            if not settings.clipboard_monitoring:
                self.clip_banner.hide()
            self.queue.table.viewport().update()
            self.history_page.table.viewport().update()
            self.banner.show_message("Settings saved.")

        install_qt_language(QApplication.instance(), settings.language)
        self._submit("settings", lambda: self.settings_service.save(settings), ready)

    def retranslate_ui(self) -> None:
        self.ui_language = language()

    def _system_theme_changed(self, _scheme) -> None:
        if not self.closing and self.settings.theme == "system":
            apply_theme(QApplication.instance(), self.settings.theme)
            self.queue.table.viewport().update()
            self.history_page.table.viewport().update()

    def _ffmpeg_result(self, status, error) -> None:
        if error:
            self._failure(error)
            self.engine_status.setText(tr("Engine check failed"))
            return
        self.manager.ffmpeg = status.path if status.available else ""
        self.engine_status.setText(tr("FFmpeg ready" if status.available else "FFmpeg not found"))
        self.about.ffmpeg.setText(
            tr(
                "FFmpeg: {version}\nSource: {source}\nffprobe: {probe}",
                version=(
                    status.version.split()[2]
                    if status.version.startswith("ffmpeg version ")
                    else tr(status.version)
                ),
                source=tr(status.source),
                probe=tr("Ready" if status.ffprobe_available else "Unavailable"),
            )
        )
        self.settings_page.ffmpeg.setText(
            tr("FFmpeg ready" if status.available else "FFmpeg not found")
        )
        log.info("FFmpeg status: %s", status)
        if not status.available:
            self.banner.show_message(
                "FFmpeg unavailable. Combined video formats can still download.",
                "Install FFmpeg and ffprobe from a trusted source, add them to PATH, "
                "and restart. See README for bundled/managed locations.",
            )

    def _check_version(self) -> None:
        self.about.check_button.setEnabled(False)

        def ready(version, error) -> None:
            self.about.check_button.setEnabled(True)
            if error:
                self._failure(error)
            else:
                self.about.latest.setText(
                    tr("Latest known yt-dlp version: {version}", version=version)
                )

        self._submit("version", check_engine_version, ready)

    def _open(self, path: Path) -> None:
        self._submit(
            "open",
            lambda: open_path(path),
            lambda _, error: self._failure(error) if error else None,
        )

    def _open_logs(self) -> None:
        self._open(self.log_directory)

    def _clipboard_changed(self) -> None:
        url = self.clipboard.detect(
            QApplication.clipboard().text(), self.settings.clipboard_monitoring
        )
        if url:
            self.clip_url = url
            self.clip_banner.show()

    def _copy_url(self, url: str) -> None:
        self.clipboard.ignore_copy(url)
        QApplication.clipboard().setText(url)

    def _analyze_clipboard(self) -> None:
        self.clip_banner.hide()
        self._navigate(0)
        self._analyze(self.clip_url)

    def _show_mini(self) -> None:
        self.mini.show()
        self.hide()

    def _restore(self) -> None:
        self.show()
        self.raise_()
        self.mini.hide()

    def _mini_analyze(self, url: str) -> None:
        self._restore()
        self._navigate(0)
        self._analyze(url)

    def _tick(self) -> None:
        if self.closing:
            if self.manager.idle and not self.tasks and self.thumbnails.idle:
                self.manager.shutdown()
                self.background.shutdown(wait=True, cancel_futures=True)
                self.settings_writer.shutdown(wait=True)
                self.ready_to_close = True
                self.close()
            return
        if self.manager.idle and self.manager.workers != self.settings.parallel_downloads:
            self.manager.configure_workers(self.settings.parallel_downloads)
        if self.scheduler.due():
            self.queue.schedule_label.setText(tr("Scheduled downloads started"))
            self.manager.start()
        if not self.mini.isVisible():
            return
        items = self.queue.model.items
        active = [
            item
            for item in items
            if item.status in {Status.ANALYZING, Status.DOWNLOADING, Status.PROCESSING}
        ]
        self.mini.count.setText(
            tr("{active} active · {total} in queue", active=len(active), total=len(items))
        )
        self.mini.progress.setValue(
            round(sum(item.progress for item in items) / len(items)) if items else 0
        )

    def closeEvent(self, event) -> None:
        if self.ready_to_close:
            self.timer.stop()
            self.mini.hide()
            self.notifications.tray.hide()
            log.info("Application shutdown complete")
            event.accept()
            return
        event.ignore()
        if not self.closing:
            self.closing = True
            self.analysis_cancel.set()
            self.scheduler.cancel()
            self.ui_events.shutdown()
            self.queue.debounce.stop()
            self.history_page.debounce.stop()
            self.manager.begin_shutdown()
            self.thumbnails.shutdown()
            self.stack.setEnabled(False)
            self.banner.show_message(
                "Closing safely · stopping downloads and finishing local tasks…"
            )
            for key, future in list(self.tasks.items()):
                if not key.startswith("settings-"):
                    future.cancel()
            self.timer.setInterval(100)
