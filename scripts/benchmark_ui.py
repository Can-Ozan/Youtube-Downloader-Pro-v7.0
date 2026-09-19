"""Opt-in local UI benchmark; generates no network traffic or production profiling."""

import argparse
import json
import os
import threading
import time
from dataclasses import replace
from pathlib import Path

import psutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    started = time.perf_counter()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from youtube_downloader_pro.models.download_item import DownloadItem, DownloadOptions
    from youtube_downloader_pro.models.download_status import DownloadStatus
    from youtube_downloader_pro.models.settings import Settings
    from youtube_downloader_pro.ui.main_window import MainWindow

    app = QApplication([])
    window = MainWindow(args.output.parent / "benchmark-data")
    window.show()
    app.processEvents()
    startup = time.perf_counter() - started
    window._navigate(1)
    options = DownloadOptions(Settings())
    items = [DownloadItem(f"https://example.org/{i}", f"Media {i}", options) for i in range(1000)]
    for item in items:
        item.status = DownloadStatus.DOWNLOADING
        window.queue.model.update_item(item)
    changes = []
    window.queue.model.dataChanged.connect(lambda *_: changes.append(1))
    gaps = []
    last_tick = time.perf_counter()

    def tick():
        nonlocal last_tick
        now = time.perf_counter()
        gaps.append(now - last_tick)
        last_tick = now

    timer = QTimer()
    timer.setInterval(16)
    timer.timeout.connect(tick)
    timer.start()
    submit = window.ui_events.submit

    def flood():
        for value in range(1, 21):
            for item in items:
                submit({"type": "item", "item": replace(item, progress=value)})

    before = time.perf_counter()
    producer = threading.Thread(target=flood)
    producer.start()
    while producer.is_alive() or window.queue.model.items[-1].progress < 20:
        app.processEvents()
        if time.perf_counter() - before > 20:
            raise RuntimeError("UI benchmark timed out")
        time.sleep(0.001)
    producer.join()
    elapsed = time.perf_counter() - before
    process = psutil.Process()
    cpu_before = sum(process.cpu_times()[:2])
    deadline = time.perf_counter() + 1
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.005)
    idle_cpu = sum(process.cpu_times()[:2]) - cpu_before
    timer.stop()
    window.close()
    deadline = time.perf_counter() + 15
    while not window.ready_to_close and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)
    report = {
        "startup_seconds": round(startup, 4),
        "rows": len(items),
        "events": 20000,
        "flood_seconds": round(elapsed, 4),
        "row_notifications": len(changes),
        "max_timer_gap_ms": round(max(gaps, default=0) * 1000, 2),
        "idle_cpu_seconds_per_second": round(idle_cpu, 4),
        "graceful_exit": window.ready_to_close,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
