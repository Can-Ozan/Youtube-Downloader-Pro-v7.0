import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from youtube_downloader_pro.core.download_manager import DownloadManager, retry_delay
from youtube_downloader_pro.core.errors import CancelledError, DownloadError
from youtube_downloader_pro.models.download_item import DownloadItem, DownloadOptions
from youtube_downloader_pro.models.download_status import DownloadStatus as Status
from youtube_downloader_pro.services.archive_service import ArchiveService
from youtube_downloader_pro.services.history_service import HistoryService


def wait_until(predicate, timeout=5):
    end = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= end:
            raise AssertionError("Timed out waiting for task")
        time.sleep(0.01)


@pytest.fixture
def manager_factory(tmp_path):
    managers = []

    def make(runner, workers=2):
        manager = DownloadManager(
            workers,
            history=HistoryService(tmp_path / "history.sqlite3"),
            archive=ArchiveService(tmp_path),
            runner=runner,
            backoff=lambda _: 0,
        )
        managers.append(manager)
        return manager

    yield make
    for manager in managers:
        manager.shutdown()


def success_runner(operation, payload, cancel, emit):
    emit({"type": "state", "status": "Downloading"})
    emit({"type": "progress", "downloaded_bytes": 4, "total_bytes": 10, "speed": 3, "eta": 2})
    emit({"type": "state", "status": "Processing"})
    path = Path(payload["staging"]) / "sample.mp4"
    path.write_bytes(b"test media")
    return {"output_file": str(path), "title": "Sample", "archive_id": "test sample"}


def test_state_transitions(settings):
    item = DownloadItem("https://example.com/a", "Title", DownloadOptions(settings))
    with pytest.raises(ValueError):
        item.transition(Status.COMPLETED)
    for status in (Status.ANALYZING, Status.DOWNLOADING, Status.PROCESSING, Status.COMPLETED):
        item.transition(status)
    with pytest.raises(ValueError):
        item.transition(Status.DOWNLOADING)


def test_success_verified_queue_duplicates_and_history(manager_factory, settings):
    manager = manager_factory(success_runner)
    for _ in range(3):
        manager.add(DownloadItem("https://example.com/a", "Title", DownloadOptions(settings)))
    manager.start()
    manager.start()  # repeated Start must not submit the same item again
    wait_until(lambda: manager.idle)
    rows = manager.snapshot()
    assert all(row.status == Status.COMPLETED and row.progress == 100 for row in rows)
    assert len({row.output_file for row in rows}) == 3
    assert len(manager._history.search()) == 3
    rows[0].title = "mutated snapshot"
    assert manager.snapshot()[0].title == "Sample"
    manager.clear_completed()
    assert manager.snapshot() == []


def test_false_success_regression(manager_factory, settings):
    def missing(_op, payload, _cancel, _emit):
        return {"output_file": str(Path(payload["staging"]) / "missing.mp4")}

    manager = manager_factory(missing)
    manager.add(DownloadItem("https://example.com/a", "Title", DownloadOptions(settings)))
    manager.start()
    wait_until(lambda: manager.idle)
    assert manager.snapshot()[0].status == Status.FAILED
    assert manager.snapshot()[0].error_code == "output"


def test_transient_retries_bounded(manager_factory, settings):
    attempts = []

    def retrying(*args):
        attempts.append(1)
        if len(attempts) < 3:
            raise DownloadError("network", "Temporary network failure", True)
        return success_runner(*args)

    manager = manager_factory(retrying)
    manager.add(DownloadItem("https://example.com/a", "Title", DownloadOptions(settings)))
    manager.start()
    wait_until(lambda: manager.idle)
    assert len(attempts) == 3
    assert manager.snapshot()[0].status == Status.COMPLETED
    assert manager.snapshot()[0].attempt == 3
    assert [retry_delay(i) for i in range(1, 5)] == [2, 4, 8, 8]


def test_permanent_failure_retry_and_cancel_waiting(manager_factory, settings):
    def permanent(*_args):
        raise DownloadError("unavailable", "Unavailable")

    manager = manager_factory(permanent)
    key = manager.add(DownloadItem("https://example.com/a", "Title", DownloadOptions(settings)))
    manager.start()
    wait_until(lambda: manager.idle)
    assert manager.snapshot()[0].attempt == 1
    manager.retry(key)
    assert manager.snapshot()[0].status == Status.WAITING
    manager.cancel(key)
    assert manager.snapshot()[0].status == Status.CANCELLED


def test_cancel_running_and_remove_queued(manager_factory, settings):
    entered = threading.Event()

    def blocked(_op, _payload, cancel, _emit):
        entered.set()
        assert cancel.wait(5)
        raise CancelledError()

    manager = manager_factory(blocked, workers=1)
    first = manager.add(DownloadItem("https://example.com/1", "One", DownloadOptions(settings)))
    second = manager.add(DownloadItem("https://example.com/2", "Two", DownloadOptions(settings)))
    manager.start()
    assert entered.wait(3)
    manager.remove(second)
    manager.cancel(first)
    wait_until(lambda: manager.idle)
    assert [item.id for item in manager.snapshot()] == [first]
    assert manager.snapshot()[0].status == Status.CANCELLED


def test_archive_requires_explicit_download_again(manager_factory, settings):
    manager = manager_factory(success_runner)
    settings = replace(settings, archive_enabled=True, history_enabled=False)
    manager._archive.record("https://example.com/a", "test a", "/gone.mp4")
    key = manager.add(DownloadItem("https://example.com/a", "Title", DownloadOptions(settings)))
    manager.start()
    wait_until(lambda: manager.idle)
    assert manager.snapshot()[0].error_code == "archive"
    manager.retry(key, download_again=True)
    manager.start()
    wait_until(lambda: manager.idle)
    assert manager.snapshot()[0].status == Status.COMPLETED


@pytest.mark.parametrize("same_url", [True, False])
def test_archive_reserves_urls_and_extracted_ids_before_transfer(
    manager_factory, settings, same_url
):
    entered, release = threading.Event(), threading.Event()
    transfers = []

    def held(operation, payload, cancel, emit):
        assert emit({"type": "archive_claim", "archive_id": "test same-media"}) is True
        transfers.append(payload["url"])
        entered.set()
        assert release.wait(5)
        return success_runner(operation, payload, cancel, emit) | {"archive_id": "test same-media"}

    manager = manager_factory(held)
    options = DownloadOptions(replace(settings, archive_enabled=True))
    first = manager.add(DownloadItem("https://example.com/a", "First", options))
    manager.start()
    assert entered.wait(3)
    second = manager.add(
        DownloadItem(
            "https://example.com/a" if same_url else "https://example.com/alias", "Second", options
        )
    )
    try:
        manager.start()
        wait_until(lambda: manager.snapshot()[1].status == Status.FAILED)
        assert manager.snapshot()[1].error_code == "archive"
        assert transfers == ["https://example.com/a"]
    finally:
        release.set()
    wait_until(lambda: manager.idle)
    assert manager.snapshot()[0].status == Status.COMPLETED
    assert not manager._archive_claims
    manager.retry(second)
    manager.start()
    wait_until(lambda: manager.idle)
    assert manager.snapshot()[1].error_code == "archive"
    assert len(transfers) == 1 and manager.snapshot()[0].id == first


def test_archive_different_media_still_download_in_parallel(manager_factory, settings):
    transfers = threading.Barrier(2)

    def parallel(operation, payload, cancel, emit):
        assert emit({"type": "archive_claim", "archive_id": payload["url"]}) is True
        transfers.wait(5)
        return success_runner(operation, payload, cancel, emit) | {"archive_id": payload["url"]}

    manager = manager_factory(parallel)
    for suffix in ("one", "two"):
        manager.add(
            DownloadItem(
                f"https://example.com/{suffix}",
                suffix,
                DownloadOptions(replace(settings, archive_enabled=True)),
            )
        )
    manager.start()
    wait_until(lambda: manager.idle)
    assert all(item.status == Status.COMPLETED for item in manager.snapshot())


@pytest.mark.parametrize("failure", ["cancel", "error"])
def test_archive_reservations_release_on_unsuccessful_jobs(manager_factory, settings, failure):
    first_attempt = True

    def runner(operation, payload, cancel, emit):
        nonlocal first_attempt
        assert emit({"type": "archive_claim", "archive_id": "test retryable"}) is True
        if first_attempt:
            first_attempt = False
            if failure == "cancel":
                cancel.set()
                raise CancelledError()
            raise DownloadError("unavailable", "Unavailable")
        return success_runner(operation, payload, cancel, emit)

    manager = manager_factory(runner)
    key = manager.add(
        DownloadItem(
            "https://example.com/a",
            "First",
            DownloadOptions(replace(settings, archive_enabled=True)),
        )
    )
    manager.start()
    wait_until(lambda: manager.idle)
    assert manager.snapshot()[0].status != Status.COMPLETED
    assert not manager._archive_claims and manager._archive.lookup("https://example.com/a") is None
    manager.retry(key)
    manager.start()
    wait_until(lambda: manager.idle)
    assert manager.snapshot()[0].status == Status.COMPLETED


@pytest.mark.parametrize("cancel_when", ["last_link", "completion_boundary"])
def test_cancel_final_publication_never_completes_or_records_archive(
    manager_factory, settings, monkeypatch, cancel_when
):
    from youtube_downloader_pro.core import download_manager
    from youtube_downloader_pro.utils import staged_output

    def runner(*args):
        result = success_runner(*args)
        (Path(args[1]["staging"]) / "sample.srt").write_text("subtitle")
        return result

    manager = manager_factory(runner)
    events = []
    manager._on_event = events.append
    options = DownloadOptions(replace(settings, archive_enabled=True))
    key = manager.add(DownloadItem("https://example.com/a", "Media", options))
    destination = Path(settings.download_folder)
    destination.mkdir(parents=True)
    existing = destination / "keep.mp4"
    existing.write_bytes(b"existing output")
    if cancel_when == "last_link":
        original = staged_output.os.link

        def cancel_after_link(source, target):
            original(source, target)
            if Path(target).suffix == ".mp4":
                manager.cancel(key)

        monkeypatch.setattr(staged_output.os, "link", cancel_after_link)
    else:
        original = download_manager.publish_files

        def cancel_before_completion(*args, on_published):
            def finish(path):
                manager.cancel(key)
                on_published(path)

            return original(*args, on_published=finish)

        monkeypatch.setattr(download_manager, "publish_files", cancel_before_completion)
    manager.start()
    wait_until(lambda: manager.idle)
    final = manager.snapshot()[0]
    assert final.status == Status.CANCELLED and not final.output_file
    assert all(
        event["item"].status != Status.COMPLETED for event in events if event["type"] == "item"
    )
    assert manager._history.search()[0]["status"] == "Cancelled"
    assert not manager._archive.lookup(final.url) and not manager._archive.contains_id(
        "test sample"
    )
    assert sorted(destination.iterdir()) == [existing]
    assert existing.read_bytes() == b"existing output"
