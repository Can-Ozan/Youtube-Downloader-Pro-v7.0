import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from youtube_downloader_pro.utils.paths import app_data_dir


class ArchiveService:
    """Verified completion ledger with an export compatible with yt-dlp archives."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or app_data_dir()

    @contextmanager
    def _connect(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.directory / "archive.sqlite3", timeout=10)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS archive (source_url TEXT PRIMARY KEY, "
                "archive_id TEXT, output_file TEXT)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS archive_media ON archive(archive_id)")
            yield db

    def lookup(self, url: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT output_file FROM archive WHERE source_url=?", (url,)
            ).fetchone()
        return row[0] if row else None

    def contains_id(self, archive_id: str | None) -> bool:
        if not archive_id:
            return False
        with self._connect() as db:
            return (
                db.execute("SELECT 1 FROM archive WHERE archive_id=?", (archive_id,)).fetchone()
                is not None
            )

    def record(self, url: str, archive_id: str | None, output_file: str) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO archive VALUES (?,?,?)", (url, archive_id, output_file)
            )
            rows = db.execute(
                "SELECT DISTINCT archive_id FROM archive WHERE archive_id IS NOT NULL"
            )
            contents = "".join(row[0] + "\n" for row in rows if row[0])
            # The manager serializes writes; SQLite is the authoritative archive.
            (self.directory / "download-archive.txt").write_text(contents, encoding="utf-8")
