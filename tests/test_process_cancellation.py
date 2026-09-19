import os
import shutil
import subprocess
import threading
import time

import psutil
import pytest

from youtube_downloader_pro.core import worker
from youtube_downloader_pro.core.errors import CancelledError


def ffmpeg_child_worker(_operation, payload, connection):
    """A real FFmpeg child exercises the same process tree as postprocessing."""
    process = subprocess.Popen(
        [
            payload["ffmpeg"],
            "-v",
            "error",
            "-re",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    connection.send({"type": "child", "pid": process.pid})
    process.wait(timeout=60)


def test_cancellation_kills_actual_ffmpeg_child(monkeypatch):
    ffmpeg = os.environ.get("YDP_TEST_FFMPEG") or shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg required for process-tree cancellation test")
    monkeypatch.setattr(worker, "worker_entry", ffmpeg_child_worker)
    cancel = threading.Event()
    child_started = threading.Event()
    child_ids, results = [], []

    def event(value):
        child_ids.append(value["pid"])
        child_started.set()

    def run():
        try:
            worker.run_worker("download", {"ffmpeg": ffmpeg}, cancel, event)
        except CancelledError:
            results.append("cancelled")

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert child_started.wait(10)
    finally:
        cancel.set()
        thread.join(10)
    assert not thread.is_alive()
    assert results == ["cancelled"]
    for pid in child_ids:
        end = time.monotonic() + 5
        while psutil.pid_exists(pid) and time.monotonic() < end:
            try:
                if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                    break
            except psutil.NoSuchProcess:
                break
            time.sleep(0.05)
        assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
