"""Virtual download/history cards: painting visible rows, never a QWidget per item."""

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from youtube_downloader_pro.i18n import tr, translate_message
from youtube_downloader_pro.ui.design import (
    DOWNLOAD_ROW_HEIGHT,
    FONT_BODY,
    FONT_META,
    RADIUS,
    tokens,
)
from youtube_downloader_pro.ui.icons import icon
from youtube_downloader_pro.utils.formatting import format_bytes, format_duration


class DownloadDelegate(QStyledItemDelegate):
    overflow = Signal(object)

    def sizeHint(self, option, index):
        return QSize(480, DOWNLOAD_ROW_HEIGHT)

    def editorEvent(self, event, model, option, index):
        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.position().x() > option.rect.right() - 40
        ):
            self.overflow.emit(event.position().toPoint())
            return True
        return False

    def paint(self, painter, option, index):
        item = index.data(Qt.ItemDataRole.UserRole)
        if item is None:
            return
        c = tokens()
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(0, 4, -4, -4)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["selected"] if selected else c["surface"]))
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QColor(c["accent"]))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), RADIUS, RADIUS)
        thumb = QRect(rect.left() + 16, rect.top() + 16, 80, 48)
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if pixmap and not pixmap.isNull():
            painter.drawPixmap(
                thumb.center().x() - pixmap.width() // 2,
                thumb.center().y() - pixmap.height() // 2,
                pixmap,
            )
        else:
            icon("video").paint(painter, thumb.adjusted(24, 8, -24, -8))
        x, width = rect.left() + 112, max(40, rect.width() - 144)
        body = QFont(option.font)
        body.setPixelSize(FONT_BODY)
        body.setWeight(QFont.Weight.DemiBold)
        painter.setFont(body)
        painter.setPen(QColor(c["text"]))
        painter.drawText(
            QRect(x, rect.top() + 8, width, 24),
            Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(item.title, Qt.TextElideMode.ElideRight, width),
        )
        icon("more").paint(painter, QRect(rect.right() - 28, rect.top() + 16, 20, 20))
        body.setPixelSize(FONT_META)
        body.setWeight(QFont.Weight.Normal)
        painter.setFont(body)
        status = (
            translate_message(item.message)
            if item.message.startswith(("Retrying", "Cancelling"))
            else tr(item.status.value)
        )
        painter.setPen(QColor(c["muted"]))
        output = (
            tr("Custom") if item.options.mode == "custom" else item.options.format_label.upper()
        )
        text = f"{tr(item.options.quality_label)} · {output} · {status}"
        painter.drawText(
            QRect(x, rect.top() + 32, width, 20),
            Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, width),
        )
        bar = QRect(x, rect.top() + 56, width, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["hover"]))
        painter.drawRoundedRect(bar, 2, 2)
        color = (
            "success"
            if item.status.value == "Completed"
            else "danger"
            if item.status.value == "Failed"
            else "accent"
        )
        painter.setBrush(QColor(c[color]))
        painter.drawRoundedRect(
            QRect(bar.x(), bar.y(), round(bar.width() * item.progress / 100), 4), 2, 2
        )
        painter.setPen(QColor(c["muted"]))
        size = f"{format_bytes(item.downloaded_bytes)} / {format_bytes(item.total_bytes)}"
        speed = format_bytes(item.speed) + tr("/s") if item.speed else ""
        eta = tr("{time} remaining", time=format_duration(item.eta)) if item.eta else ""
        stats = " · ".join(filter(None, (f"{item.progress:.0f}%", speed, eta)))
        if width < 400:
            text = stats + " · " + size
            painter.drawText(
                QRect(x, rect.top() + 64, width, 20),
                Qt.AlignmentFlag.AlignVCenter,
                painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, width),
            )
        else:
            painter.drawText(
                QRect(x, rect.top() + 64, width, 20), Qt.AlignmentFlag.AlignVCenter, size
            )
            painter.drawText(
                QRect(x, rect.top() + 64, width, 20),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                stats,
            )
        painter.restore()


class HistoryDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        row = index.data(Qt.ItemDataRole.UserRole)
        if not row:
            return
        c = tokens()
        painter.save()
        rect = option.rect.adjusted(0, 4, -4, -4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            QColor(
                c["selected"] if option.state & QStyle.StateFlag.State_Selected else c["surface"]
            )
        )
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QColor(c["accent"]))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), RADIUS, RADIUS)
        font = QFont(option.font)
        font.setPixelSize(FONT_BODY)
        painter.setFont(font)
        painter.setPen(QColor(c["text"]))
        title = painter.fontMetrics().elidedText(
            row["title"], Qt.TextElideMode.ElideRight, rect.width() - 48
        )
        painter.drawText(rect.adjusted(16, 8, -16, -36), Qt.AlignmentFlag.AlignVCenter, title)
        font.setPixelSize(FONT_META)
        painter.setFont(font)
        painter.setPen(QColor(c["muted"]))
        date = row["downloaded_at"][:16].replace("T", " ")
        detail = " · ".join(
            [
                tr("Custom") if row["format"] == "custom" else row["format"].upper(),
                tr(row["quality"]),
                format_bytes(row["file_size"]),
                tr(row["status"]),
                date,
            ]
        )
        painter.drawText(
            rect.adjusted(16, 36, -16, -8),
            Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(
                detail, Qt.TextElideMode.ElideRight, rect.width() - 32
            ),
        )
        painter.restore()
