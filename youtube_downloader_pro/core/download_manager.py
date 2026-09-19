import logging
import tempfile
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from youtube_downloader_pro.core.errors import CancelledError, DownloadError, classify_error
from youtube_downloader_pro.core.worker import run_worker
from youtube_downloader_pro.models.download_item import DownloadItem
from youtube_downloader_pro.models.download_status import DownloadStatus as Status
from youtube_downloader_pro.services.archive_service import ArchiveService
from youtube_downloader_pro.services.history_service import HistoryService
from youtube_downloader_pro.utils.paths import ensure_output_dir
from youtube_downloader_pro.utils.staged_output import publish_files
from youtube_downloader_pro.utils.validators import validate_url

log = logging.getLogger(__name__)


def retry_delay(attempt: int) -> float:
    return min(2**attempt, 8)


class DownloadManager:
    """Single queue owner. Callbacks carry snapshots, never shared mutable queue records."""

    def __init__(
        self,
        workers: int = 3,
        on_event: Callable[[dict], None] | None = None,
        history: HistoryService | None = None,
        archive: ArchiveService | None = None,
        runner: Callable = run_worker,
        backoff: Callable = retry_delay,
    ) -> None:
        if not 1 <= workers <= 5:
            raise ValueError("Use 1–5 concurrent downloads")
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="download")
        self._lock = threading.RLock()
        self._archive_lock = threading.Lock()
        self._archive_claims: dict[tuple[str, str], str] = {}
        self._items: dict[str, DownloadItem] = {}
        self._futures: dict[str, Future] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._remove_pending: set[str] = set()
        self._on_event = on_event or (lambda _: None)
        self._history = history or HistoryService()
        self._archive = archive or ArchiveService()
        self._runner = runner
        self._backoff = backoff
        self._stopping = False
        self.ffmpeg = ""
        self.workers = workers

    def _emit(self, item: DownloadItem) -> None:
        if item.id not in self._remove_pending:
            self._on_event({"type": "item", "item": replace(item)})

    def snapshot(self) -> list[DownloadItem]:
        with self._lock:
            return [replace(item) for item in self._items.values()]

    @property
    def idle(self) -> bool:
        with self._lock:
            return not self._futures

    def configure_workers(self, workers: int) -> None:
        with self._lock:
            if workers == self.workers:
                return
            if self._futures:
                raise ValueError(
                    "Wait for active jobs to finish before changing parallel downloads."
                )
            if not 1 <= workers <= 5:
                raise ValueError("Use 1–5 concurrent downloads")
            self._executor.shutdown(wait=True)
            self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="download")
            self.workers = workers

    def add(self, item: DownloadItem) -> str:
        item = replace(item, url=validate_url(item.url))
        item.options.validate()
        with self._lock:
            if self._stopping:
                raise ValueError("The download manager is closing")
            if item.id in self._items:
                raise ValueError("This queue item already exists")
            self._items[item.id] = item
            self._cancel[item.id] = threading.Event()
            self._emit(item)
        return item.id

    def start(self) -> None:
        with self._lock:
            if self._stopping:
                return
            for item in self._items.values():
                if item.status != Status.WAITING or item.id in self._futures:
                    continue
                future = self._executor.submit(self._run, item.id)
                self._futures[item.id] = future
                future.add_done_callback(lambda f, key=item.id: self._finished(key, f))

    def _finished(self, key: str, future: Future) -> None:
        if not future.cancelled() and (error := future.exception()) is not None:
            log.error("Unexpected queue worker failure for %s: %s", key, error)
            self._update(
                key,
                status=Status.FAILED,
                error_code="internal",
                message="An internal queue error occurred. See application logs.",
            )
        with self._lock:
            self._futures.pop(key, None)
            if key in self._remove_pending:
                self._discard(key)
            if not self._futures:
                self._on_event({"type": "queue_idle"})

    def _update(self, key: str, **values) -> None:
        with self._lock:
            item = self._items.get(key)
            if not item or item.status.terminal:
                return
            if "status" in values:
                item.transition(values.pop("status"))
            for name, value in values.items():
                setattr(item, name, value)
            self._emit(item)

    def _claim_archive(self, key: str, archive_id: str | None) -> bool:
        with self._lock:
            item = self._items[key]
            if self._cancel[key].is_set():
                raise CancelledError()
            url = item.url
        with self._archive_lock:
            if self._archive.lookup(url) or self._archive.contains_id(archive_id):
                raise DownloadError(
                    "archive", "Previously downloaded. Choose Download again anyway."
                )
            identities = [("url", url)]
            if archive_id:
                identities.append(("id", archive_id))
            if any(self._archive_claims.get(identity, key) != key for identity in identities):
                raise DownloadError("archive", "This media is already downloading. Retry later.")
            for identity in identities:
                self._archive_claims[identity] = key
        return True

    def _handle_worker_event(self, key: str, event: dict):
        kind = event["type"]
        if kind == "archive_claim":
            return self._claim_archive(key, event.get("archive_id"))
        if kind == "log":
            log.info("Job %s: %s", key, event["message"])
        elif kind == "state":
            self._update(key, status=Status(event["status"]))
        elif kind == "metadata":
            media = event["media"]
            self._update(
                key,
                title=media["title"],
                duration=media.get("duration"),
                thumbnail_url=media.get("thumbnail", ""),
            )
        elif kind == "progress":
            total, downloaded = event.get("total_bytes"), event.get("downloaded_bytes", 0)
            self._update(
                key,
                status=Status.DOWNLOADING,
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed=event.get("speed"),
                eta=event.get("eta"),
                progress=min(99.9, downloaded / total * 100) if total else 0,
            )

    def _run(self, key: str) -> None:
        from youtube_downloader_pro.core.ytdlp_service import serialize_options

        with self._lock:
            item = replace(self._items[key])
            cancel = self._cancel[key]
        log.info("Download start: job %s", key)
        try:
            self._update(key, status=Status.ANALYZING)
            if cancel.is_set():
                raise CancelledError()
            if item.options.settings.archive_enabled and not item.options.download_again:
                self._claim_archive(key, None)
            destination = ensure_output_dir(item.options.settings.download_folder)
            # The parent owns staging cleanup, including after forced worker cancellation.
            with tempfile.TemporaryDirectory(prefix=".ydp-", dir=destination) as temporary:
                payload = {
                    "url": item.url,
                    "options": serialize_options(item.options),
                    "staging": temporary,
                    "ffmpeg": self.ffmpeg,
                    "estimated_size": item.estimated_size,
                    "archive_directory": str(self._archive.directory)
                    if item.options.settings.archive_enabled and not item.options.download_again
                    else "",
                }
                for attempt in range(1, 4):
                    if cancel.is_set():
                        raise CancelledError()
                    self._update(
                        key,
                        status=Status.ANALYZING,
                        attempt=attempt,
                        speed=None,
                        eta=None,
                        message="" if attempt == 1 else f"Retrying {attempt}/3",
                    )
                    try:
                        result = self._runner(
                            "download",
                            payload,
                            cancel,
                            lambda event: self._handle_worker_event(key, event),
                        )
                        # Publish only verified staged output; roll back interrupted copies.
                        output = Path(result["output_file"])
                        if not output.is_file() or output.stat().st_size <= 0:
                            raise DownloadError("output", "The final output is missing or empty.")
                        if cancel.is_set():
                            raise CancelledError()

                        def complete(published: Path, result=result) -> None:
                            size = published.stat().st_size
                            # Cancellation and completion share one linearization point.
                            # Until this succeeds the publisher still owns rollback of all files.
                            with self._lock:
                                if cancel.is_set():
                                    raise CancelledError()
                                self._update(
                                    key,
                                    status=Status.COMPLETED,
                                    output_file=str(published),
                                    title=result.get("title") or item.title,
                                    progress=100,
                                    downloaded_bytes=size,
                                    total_bytes=size,
                                    speed=None,
                                    eta=None,
                                    message="Download completed",
                                )

                        output = publish_files(
                            Path(temporary), destination, output, cancel, on_published=complete
                        )
                        if item.options.settings.archive_enabled:
                            try:
                                with self._archive_lock:
                                    self._archive.record(
                                        item.url, result.get("archive_id"), str(output)
                                    )
                            except Exception as exc:
                                # A ledger failure must never misreport a successful media download.
                                log.error("Archive write failed: %s", exc)
                                self._on_event(
                                    {"type": "warning", "message": "Could not update archive."}
                                )
                        break
                    except Exception as exc:
                        error = classify_error(exc)
                        log.warning("Job %s attempt %s: %s", key, attempt, exc)
                        if cancel.is_set():
                            raise CancelledError() from exc
                        if not error.retryable or attempt == 3:
                            raise error from exc
                        self._update(key, message=f"Retrying {attempt + 1}/3 shortly…", speed=None)
                        if cancel.wait(self._backoff(attempt)):
                            raise CancelledError() from exc
        except Exception as exc:
            error = CancelledError() if cancel.is_set() else classify_error(exc)
            self._update(
                key,
                status=Status.CANCELLED if error.code == "cancelled" else Status.FAILED,
                error_code=error.code,
                message=error.message,
                speed=None,
                eta=None,
            )
            log.warning("Download ended: job %s, %s", key, error.code)
        finally:
            with self._lock:
                final = replace(self._items[key])
            with self._archive_lock:
                self._archive_claims = {
                    identity: owner
                    for identity, owner in self._archive_claims.items()
                    if owner != key
                }
            if final.options.settings.history_enabled:
                try:
                    self._history.record(final)
                except Exception as exc:
                    log.error("History write failed: %s", exc)
                    self._on_event(
                        {"type": "warning", "message": "Could not save download history."}
                    )
            log.info("Download finish: job %s, %s", key, final.status.value)

    def cancel(self, key: str) -> None:
        with self._lock:
            item = self._items.get(key)
            if not item or item.status.terminal:
                return
            self._cancel[key].set()
            future = self._futures.get(key)
            if future is None or item.status == Status.WAITING:
                item.transition(Status.CANCELLED)
                item.message = "Cancelled by user."
            else:
                item.message = "Cancelling…"
            self._emit(item)

    def cancel_all(self) -> None:
        for item in self.snapshot():
            self.cancel(item.id)

    def retry(self, key: str, download_again: bool = False) -> None:
        with self._lock:
            item = self._items.get(key)
            if (
                not item
                or key in self._futures
                or item.status not in {Status.FAILED, Status.CANCELLED}
            ):
                return
            item.transition(Status.WAITING)
            item.message = item.error_code = ""
            item.progress = item.downloaded_bytes = item.attempt = 0
            item.total_bytes = item.speed = item.eta = None
            if download_again:
                item.options = replace(item.options, download_again=True)
            self._cancel[key] = threading.Event()
            self._emit(item)

    def retry_failed(self) -> None:
        for item in self.snapshot():
            if item.status == Status.FAILED:
                self.retry(item.id)
        self.start()

    def _discard(self, key: str) -> None:
        self._items.pop(key, None)
        self._cancel.pop(key, None)
        self._remove_pending.discard(key)
        self._on_event({"type": "removed", "id": key})

    def remove(self, key: str) -> None:
        with self._lock:
            if key in self._futures:
                self._remove_pending.add(key)
                self._on_event({"type": "removed", "id": key})
                self.cancel(key)
            else:
                self._discard(key)

    def clear_completed(self) -> None:
        for item in self.snapshot():
            if item.status == Status.COMPLETED:
                self.remove(item.id)

    def begin_shutdown(self) -> None:
        with self._lock:
            self._stopping = True
        self.cancel_all()

    def shutdown(self) -> None:
        self.begin_shutdown()
        self._executor.shutdown(wait=True, cancel_futures=False)
