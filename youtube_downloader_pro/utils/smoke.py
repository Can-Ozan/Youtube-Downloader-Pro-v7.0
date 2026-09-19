"""Diagnostics invoked only by an explicit --smoke-test --smoke-report request."""

import importlib
import json
import multiprocessing
import sqlite3
from pathlib import Path

from youtube_downloader_pro import __version__
from youtube_downloader_pro.utils.paths import app_data_dir, logs_dir
from youtube_downloader_pro.utils.resources import application_icon, is_frozen, resource_root


def _check_worker(connection) -> None:
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.extractor.youtube import YoutubeIE

        connection.send({"yt_dlp": YoutubeDL.__name__, "extractor": YoutubeIE.__name__})
    finally:
        connection.close()


def write_smoke_report(window, destination: Path) -> None:
    """Exercise persistence and a spawned child without making network requests."""
    from PySide6.QtGui import QIcon, QImageReader

    from youtube_downloader_pro.i18n.translator import catalog

    catalogs = {code: catalog(code) for code in ("en", "tr")}
    if not catalogs["en"] or catalogs["en"].keys() != catalogs["tr"].keys():
        raise RuntimeError("Translation catalogs are missing or inconsistent")
    if catalogs["tr"].get("Settings") != "Ayarlar":
        raise RuntimeError("Turkish resources could not be loaded")
    modules = (
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtNetwork",
        "sqlite3",
        "psutil",
        "mutagen",
        "platformdirs",
        "yt_dlp",
        "youtube_downloader_pro.core.worker",
        "youtube_downloader_pro.core.ytdlp_service",
    )
    for name in modules:
        importlib.import_module(name)
    window.settings_service.save(window.settings)
    if window.settings_service.load() != window.settings:
        raise RuntimeError("Settings round trip failed")
    with window.history.connection() as db:
        # Roll back a real write, preserving any existing history.
        db.execute("SAVEPOINT startup_smoke")
        db.execute("CREATE TABLE startup_smoke (value TEXT)")
        db.execute("INSERT INTO startup_smoke VALUES (?)", ("Türkçe / 日本語",))
        if db.execute("SELECT value FROM startup_smoke").fetchone()[0] != "Türkçe / 日本語":
            raise RuntimeError("SQLite Unicode round trip failed")
        db.execute("ROLLBACK TO startup_smoke")
        db.execute("RELEASE startup_smoke")
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    worker = context.Process(target=_check_worker, args=(child,))
    worker.start()
    child.close()
    try:
        if not parent.poll(20):
            raise RuntimeError("Spawned engine import check timed out")
        worker_result = parent.recv()
        worker.join(5)
        if worker.exitcode != 0:
            raise RuntimeError(f"Spawned engine import check failed: {worker.exitcode}")
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join(5)
        parent.close()
    icon = application_icon()
    if icon and QIcon(str(icon)).isNull():
        raise RuntimeError("Application icon could not be decoded")
    report = {
        "passed": True,
        "version": __version__,
        "frozen": is_frozen(),
        "language": window.ui_language,
        "translation_keys": {code: len(data) for code, data in catalogs.items()},
        "resource_root": str(resource_root()),
        "icon": str(icon) if icon else None,
        "imports": list(modules),
        "worker": worker_result,
        "settings": str(window.settings_service.path.resolve()),
        "history": str(window.history.path.resolve()),
        "sqlite_version": sqlite3.sqlite_version,
        "default_data": str(app_data_dir()),
        "default_logs": str(logs_dir()),
        "image_formats": sorted(bytes(f).decode() for f in QImageReader.supportedImageFormats()),
        "window_visible": window.isVisible(),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
