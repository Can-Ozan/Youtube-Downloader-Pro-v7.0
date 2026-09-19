"""Picklable worker entry point and bounded, cancellable process runner."""

import logging
import multiprocessing
import threading
import time
from collections.abc import Callable
from multiprocessing.connection import Connection

import psutil

from youtube_downloader_pro.core.errors import CancelledError, DownloadError, classify_error
from youtube_downloader_pro.utils.logger import redact

log = logging.getLogger(__name__)


def worker_entry(operation: str, payload: dict, connection: Connection) -> None:
    # Imports stay in the child so UI startup and test doubles do not initialize extractors.
    from youtube_downloader_pro.core.ytdlp_service import analyze, download

    def emit(event: dict):
        connection.send(event)
        if event["type"] == "archive_claim":
            # The queue owner reserves the extracted identity before any transfer starts.
            return connection.recv()
        return None

    try:
        if operation == "analyze":
            result = analyze(payload["url"], emit, payload.get("start", 1))
        elif operation == "download":
            result = download(payload, emit)
        else:
            raise ValueError("Unknown worker operation")
        emit({"type": "result", "result": result})
    except Exception as exc:
        error = classify_error(exc)
        emit({"type": "log", "message": redact(f"{type(exc).__name__}: {exc}")[:4000]})
        emit(
            {
                "type": "error",
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            }
        )
    finally:
        connection.close()


def stop_process_tree(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    try:
        # Suspend first to prevent spawning another FFmpeg between enumeration and termination.
        parent.suspend()
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                continue
        parent.kill()
        psutil.wait_procs([*children, parent], timeout=3)
    except psutil.NoSuchProcess:
        return


def run_worker(
    operation: str,
    payload: dict,
    cancel: threading.Event,
    emit: Callable[[dict], object],
    timeout: float | None = None,
) -> dict:
    if cancel.is_set():
        raise CancelledError()
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=True)
    process = context.Process(
        target=worker_entry, args=(operation, payload, send), name=f"media-{operation}"
    )
    process.start()
    send.close()
    started = time.monotonic()
    try:
        while True:
            if cancel.is_set():
                raise CancelledError()
            if timeout and time.monotonic() - started > timeout:
                raise DownloadError("network", "Media analysis timed out. Try again.", True)
            if receive.poll(0.1):
                try:
                    event = receive.recv()
                except EOFError as exc:
                    raise DownloadError("engine", "The media worker exited unexpectedly.") from exc
                if event["type"] == "result":
                    return event["result"]
                if event["type"] == "error":
                    raise DownloadError(event["code"], event["message"], event["retryable"])
                response = emit(event)
                if event["type"] == "archive_claim":
                    receive.send(response)
            elif not process.is_alive():
                raise DownloadError("engine", "The media worker exited without a result.")
    finally:
        if process.is_alive():
            if cancel.is_set() or process.exitcode is None:
                # Give a successful child a brief opportunity to exit before terminating it.
                process.join(0.3)
            if process.is_alive():
                stop_process_tree(process.pid)
        process.join(timeout=3)
        receive.close()
        if process.is_alive():
            log.error("Media process did not terminate: %s", process.pid)
        else:
            process.close()
