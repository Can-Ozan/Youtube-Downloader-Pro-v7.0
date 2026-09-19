import errno
import os
import threading
from collections.abc import Callable
from pathlib import Path

from youtube_downloader_pro.core.errors import CancelledError, DownloadError
from youtube_downloader_pro.utils.paths import contained_file


def publish_files(
    staging: Path,
    destination: Path,
    media: Path,
    cancel: threading.Event | None = None,
    *,
    on_published: Callable[[Path], None] | None = None,
) -> Path:
    """Publish a group without overwrites. Roll back only files created by this call."""
    media = contained_file(staging, media)
    if not media.is_file() or not media.stat().st_size:
        raise DownloadError("output", "No final media file was produced.")
    files = sorted(
        p for p in staging.rglob("*") if p.is_file() and p.suffix not in {".part", ".ytdl", ".temp"}
    )
    files.sort(key=lambda p: p == media)  # media becomes visible after all its sidecars
    for counter in range(1, 10_001):
        suffix = "" if counter == 1 else f" ({counter})"
        created: list[Path] = []
        result = None
        try:
            for source in files:
                source = contained_file(staging, source)
                if cancel and cancel.is_set():
                    raise CancelledError()
                relative = source.relative_to(staging)
                name = relative.name
                if name.startswith(media.stem):
                    name = media.stem + suffix + name[len(media.stem) :]
                else:
                    name = relative.stem + suffix + relative.suffix
                target = contained_file(destination, destination / relative.parent / name)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(source, target)
                    created.append(target)
                except OSError as exc:
                    if isinstance(exc, FileExistsError):
                        raise
                    if exc.errno not in {
                        errno.EPERM,
                        errno.EACCES,
                        errno.EXDEV,
                        errno.ENOTSUP,
                        errno.EINVAL,
                        errno.ENOSYS,
                    }:
                        raise
                    # FAT/exFAT and some network filesystems do not support hard links.
                    with target.open("xb") as output:
                        created.append(target)
                        with source.open("rb") as incoming:
                            while chunk := incoming.read(1024 * 1024):
                                if cancel and cancel.is_set():
                                    raise CancelledError() from None
                                output.write(chunk)
                if source == media:
                    result = target
            if result is None:
                raise DownloadError("output", "The final output was not published.")
            if cancel and cancel.is_set():
                raise CancelledError()
            if on_published:
                on_published(result)
            return result
        except BaseException as exc:
            for path in reversed(created):
                path.unlink(missing_ok=True)
            if not isinstance(exc, FileExistsError):
                raise
    raise DownloadError("output", "Too many files have the same name. Choose a different template.")
