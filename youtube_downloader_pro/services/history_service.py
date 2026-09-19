import json
import sqlite3
import threading
from contextlib import closing, contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from youtube_downloader_pro.models.download_item import DownloadItem, DownloadOptions
from youtube_downloader_pro.models.settings import Settings
from youtube_downloader_pro.utils.paths import app_data_dir


class HistoryService:
    """Short-lived connections allow safe use from the background executor."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "history.sqlite3"
        self._lock = threading.RLock()

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS downloads (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, source_url TEXT NOT NULL,
                output_file TEXT NOT NULL, format TEXT NOT NULL, quality TEXT NOT NULL,
                file_size INTEGER NOT NULL, status TEXT NOT NULL, downloaded_at TEXT NOT NULL,
                duration REAL, thumbnail_url TEXT, options_json TEXT NOT NULL, mode TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS history_date ON downloads(downloaded_at DESC)")
            db.execute(
                "CREATE INDEX IF NOT EXISTS history_status_date "
                "ON downloads(status, downloaded_at DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS history_format_date "
                "ON downloads(format, downloaded_at DESC)"
            )
            yield db

    def record(self, item: DownloadItem) -> None:
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO downloads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item.id,
                    item.title,
                    item.url,
                    item.output_file,
                    item.options.format_label,
                    item.options.quality_label,
                    item.downloaded_bytes,
                    item.status.value,
                    datetime.now(UTC).isoformat(),
                    item.duration,
                    item.thumbnail_url,
                    json.dumps(asdict(item.options)),
                    item.options.mode,
                ),
            )

    def search(
        self,
        query: str = "",
        status: str = "All",
        mode: str = "All",
        since: str = "",
        limit: int = 200,
        offset: int = 0,
        format_filter: str = "All",
    ) -> list[dict]:
        conditions, args = (
            ["title LIKE ? ESCAPE '\\'"],
            ["%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"],
        )
        for column, value in (("status", status), ("mode", mode)):
            if value != "All":
                conditions.append(f"{column} = ?")
                args.append(value)
        if format_filter != "All":
            conditions.append("format = ?")
            args.append(format_filter)
        if since:
            conditions.append("downloaded_at >= ?")
            args.append(since)
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM downloads WHERE "
                + " AND ".join(conditions)
                + " ORDER BY downloaded_at DESC LIMIT ? OFFSET ?",
                [*args, min(max(limit, 1), 500), max(offset, 0)],
            ).fetchall()
            return [dict(row) for row in rows]

    def clear(self) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM downloads")

    @staticmethod
    def retry_options(row: dict) -> DownloadOptions:
        data = json.loads(row["options_json"])
        data["settings"] = Settings.from_dict(data["settings"])
        data["download_again"] = True
        return DownloadOptions(**data).validate()
