from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from youtube_downloader_pro.i18n import tr, translate_message
from youtube_downloader_pro.models.download_item import DownloadItem


class DownloadTableModel(QAbstractTableModel):
    """Virtual rows provide the information of cards without a widget per queued item."""

    def __init__(self, thumbnails) -> None:
        super().__init__()
        self.items: list[DownloadItem] = []
        self.positions: dict[str, int] = {}
        self.thumbnails = thumbnails
        self.thumbnail_rows: dict[str, set[str]] = {}
        thumbnails.loaded.connect(self._thumbnail_ready)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return item
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return self.thumbnails.get(item.thumbnail_url)
        if role == Qt.ItemDataRole.ToolTipRole:
            return translate_message(item.message) if item.message else item.title
        if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole}:
            return f"{item.title} · {tr(item.status.value)} · {item.progress:.1f}%"
        return None

    def retranslate_ui(self) -> None:
        if self.items:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self.items) - 1, 0),
                [
                    Qt.ItemDataRole.DisplayRole,
                    Qt.ItemDataRole.AccessibleTextRole,
                    Qt.ItemDataRole.ToolTipRole,
                ],
            )

    def update_item(self, item: DownloadItem) -> None:
        row = self.positions.get(item.id)
        if row is None:
            row = len(self.items)
            self.beginInsertRows(QModelIndex(), row, row)
            self.positions[item.id] = row
            self.items.append(item)
            self.thumbnail_rows.setdefault(item.thumbnail_url, set()).add(item.id)
            self.endInsertRows()
        else:
            previous = self.items[row]
            if previous.thumbnail_url != item.thumbnail_url:
                self._forget_thumbnail(previous.thumbnail_url, item.id)
                self.thumbnail_rows.setdefault(item.thumbnail_url, set()).add(item.id)
            self.items[row] = item
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    def remove_item(self, key: str) -> None:
        row = self.positions.get(key)
        if row is not None:
            self.beginRemoveRows(QModelIndex(), row, row)
            item = self.items.pop(row)
            self._forget_thumbnail(item.thumbnail_url, key)
            self.positions = {item.id: i for i, item in enumerate(self.items)}
            self.endRemoveRows()

    def _forget_thumbnail(self, url: str, key: str) -> None:
        rows = self.thumbnail_rows.get(url)
        if rows is not None:
            rows.discard(key)
            if not rows:
                self.thumbnail_rows.pop(url)

    def _thumbnail_ready(self, url: str) -> None:
        for key in self.thumbnail_rows.get(url, ()):
            if (row := self.positions.get(key)) is not None:
                self.dataChanged.emit(
                    self.index(row, 0), self.index(row, 0), [Qt.ItemDataRole.DecorationRole]
                )
