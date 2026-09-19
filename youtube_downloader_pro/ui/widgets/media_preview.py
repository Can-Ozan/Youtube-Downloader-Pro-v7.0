import logging
from collections import OrderedDict, deque

from PySide6.QtCore import (
    QBuffer,
    QIODevice,
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout

from youtube_downloader_pro.i18n import tr
from youtube_downloader_pro.ui.design import PREVIEW_SIZE
from youtube_downloader_pro.ui.icons import icon
from youtube_downloader_pro.ui.localization import watch_language
from youtube_downloader_pro.ui.widgets.common import label
from youtube_downloader_pro.utils.formatting import format_bytes, format_duration
from youtube_downloader_pro.utils.validators import ValidationError, validate_url

log = logging.getLogger(__name__)

THUMBNAIL_SIZES = ((192, 108), (80, 48))


class DecodeTask(QRunnable):
    def __init__(self, url, data, completed):
        super().__init__()
        self.url, self.data, self.completed = url, data, completed

    def run(self):
        images = {}
        try:
            buffer = QBuffer()
            buffer.setData(self.data)
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            reader = QImageReader(buffer)
            size = reader.size()
            if size.isValid() and size.width() * size.height() <= 32_000_000:
                reader.setScaledSize(
                    size.scaled(QSize(480, 270), Qt.AspectRatioMode.KeepAspectRatio)
                )
                image = reader.read()
                if not image.isNull():
                    images = {
                        dimensions: image.scaled(
                            QSize(*dimensions),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        for dimensions in THUMBNAIL_SIZES
                    }
        except Exception:
            log.exception("Thumbnail decoding failed")
        finally:
            self.completed.emit(self.url, images)


class ThumbnailLoader(QObject):
    loaded = Signal(str)
    decoded = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.cache: OrderedDict[str, dict] = OrderedDict()
        self.cache_bytes = 0
        self.pending: set[str] = set()
        self.waiting: deque[str] = deque()
        self.active = 0
        self.closed = False
        QImageReader.setAllocationLimit(32)
        self.decoded.connect(self._decoded, Qt.ConnectionType.QueuedConnection)

    @property
    def idle(self):
        return self.active == 0 and self.pool.activeThreadCount() == 0

    def get(self, url: str, size: tuple = (80, 48)) -> QPixmap:
        if url in self.cache:
            self.cache.move_to_end(url)
            return self.cache[url].get(size, QPixmap())
        if url and url not in self.pending and not self.closed and len(self.pending) < 64:
            try:
                validate_url(url)
            except ValidationError:
                return QPixmap()
            self.pending.add(url)
            self.waiting.append(url)
            self._pump()
        return QPixmap()

    def _pump(self) -> None:
        while self.waiting and self.active < 4 and not self.closed:
            url = self.waiting.popleft()
            request = QNetworkRequest(QUrl(url))
            request.setTransferTimeout(10_000)
            request.setAttribute(
                QNetworkRequest.Attribute.RedirectPolicyAttribute,
                QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
            )
            request.setMaximumRedirectsAllowed(5)
            reply = self.network.get(request)
            self.active += 1
            reply.readyRead.connect(
                lambda r=reply: r.abort() if r.bytesAvailable() > 4_000_000 else None
            )
            reply.finished.connect(lambda r=reply, u=url: self._finish(u, r))

    def _finish(self, url: str, reply: QNetworkReply) -> None:
        if (
            not self.closed
            and reply.error() == QNetworkReply.NetworkError.NoError
            and reply.bytesAvailable() <= 4_000_000
        ):
            self.pool.start(DecodeTask(url, reply.readAll(), self.decoded))
        else:
            self._decoded(url, {})
        reply.deleteLater()

    @Slot(str, object)
    def _decoded(self, url: str, images: dict) -> None:
        self.pending.discard(url)
        self.active -= 1
        if self.closed:
            return
        values = {size: QPixmap.fromImage(image) for size, image in images.items()}
        self.cache[url] = values
        self.cache_bytes += sum(p.width() * p.height() * 4 for p in values.values())
        while len(self.cache) > 100 or self.cache_bytes > 32 * 1024**2:
            _, removed = self.cache.popitem(last=False)
            self.cache_bytes -= sum(p.width() * p.height() * 4 for p in removed.values())
        self.loaded.emit(url)
        self._pump()

    def shutdown(self) -> None:
        self.closed = True
        self.waiting.clear()
        for reply in self.network.findChildren(QNetworkReply):
            if not reply.isFinished():
                reply.abort()


class MediaPreview(QFrame):
    def __init__(self, thumbnails: ThumbnailLoader) -> None:
        super().__init__()
        self.setObjectName("card")
        self.thumbnails = thumbnails
        self.url = ""
        self.media = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        self.image = label("")
        self.image.setPixmap(icon("video").pixmap(32, 32))
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedSize(*PREVIEW_SIZE)
        layout.addWidget(self.image)
        details = QVBoxLayout()
        self.title = label("Analyze a link to see its details", "section", True)
        self.meta = label("", "muted", True)
        self.formats = label("", "muted", True)
        details.addWidget(self.title)
        details.addWidget(self.meta)
        details.addWidget(self.formats)
        layout.addLayout(details, 1)
        thumbnails.loaded.connect(self._loaded)
        watch_language(self, self.retranslate_ui)

    def set_media(self, media: dict) -> None:
        self.media = media
        self.title.setText(media["title"])
        self.title.setToolTip(media["title"])
        self.url = media.get("thumbnail", "")
        self.image.setPixmap(icon("video").pixmap(32, 32))
        self._loaded(self.url)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        media = self.media
        if media is None:
            return
        self.meta.setText(
            "  ·  ".join(
                filter(
                    None,
                    [
                        media.get("uploader"),
                        tr("Playlist" if media.get("is_playlist") else "Video / audio"),
                        format_duration(media.get("duration")),
                        format_bytes(media.get("estimated_size")),
                    ],
                )
            )
        )
        self.formats.setText(
            tr("Select the videos you want to save.") if media.get("is_playlist") else ""
        )

    def _loaded(self, url: str) -> None:
        if url == self.url:
            image = self.thumbnails.get(url, (192, 108))
            if not image.isNull():
                self.image.setPixmap(
                    image.scaled(
                        self.image.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
