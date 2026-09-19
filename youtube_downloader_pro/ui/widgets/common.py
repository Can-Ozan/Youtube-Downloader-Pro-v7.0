from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStyle,
    QStyleOptionComboBox,
    QStyleOptionSpinBox,
    QVBoxLayout,
    QWidget,
)

from youtube_downloader_pro.i18n import tr, translate_message
from youtube_downloader_pro.i18n.translator import TranslatedText
from youtube_downloader_pro.ui.design import CONTROL_HEIGHT, ICON_SIZE, tokens
from youtube_downloader_pro.ui.icons import icon
from youtube_downloader_pro.ui.localization import bind_text, watch_language


class TranslatedLabel(QLabel):
    def __init__(self, text=""):
        super().__init__()
        self.source_text = None
        watch_language(self, self.retranslate_ui)
        self.setText(text)

    def setText(self, text):
        self.source_text = text if isinstance(text, TranslatedText) and text else None
        super().setText(text)

    def retranslate_ui(self):
        if self.source_text is not None:
            self.setText(tr(self.source_text))


class TranslatedButton(QPushButton):
    def __init__(self, text):
        super().__init__()
        self.source_text = None
        watch_language(self, self.retranslate_ui)
        self.setText(text)

    def setText(self, text):
        self.source_text = text if isinstance(text, TranslatedText) else None
        super().setText(text)
        self.setAccessibleName(text)

    def retranslate_ui(self):
        if self.source_text is not None:
            self.setText(tr(self.source_text))


def label(text: str, style: str = "", wrap: bool = False, *, translate: bool = True) -> QLabel:
    widget = TranslatedLabel(tr(text) if translate else text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(style)
    widget.setWordWrap(wrap)
    return widget


def icon_label(name: str, size: int) -> QLabel:
    widget = label("")
    widget.setProperty("icon_name", name)
    widget.setProperty("icon_size", QSize(size, size))
    widget.setPixmap(icon(name).pixmap(size, size))
    return widget


def button(text: str, callback=None, primary: bool = False, icon_name: str = "") -> QPushButton:
    widget = TranslatedButton(tr(text))
    widget.setMinimumHeight(CONTROL_HEIGHT)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setAccessibleName(tr(text))
    if primary:
        widget.setObjectName("primary")
    if icon_name:
        widget.setIcon(icon(icon_name, tokens()["on_accent"] if primary else None))
        widget.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        widget.setProperty("icon_name", icon_name)
    if callback:
        widget.clicked.connect(callback)
    return widget


def check(text: str = "") -> QCheckBox:
    widget = QCheckBox()
    bind_text(widget, "setText", text)
    return widget


class ChoiceCombo(QComboBox):
    """Translated display labels with stable values, including legacy selection calls."""

    display_names = {
        "en": "English",
        "tr": "Türkçe",
        "dark": "Dark",
        "light": "Light",
        "system": "System",
        "none": "None",
        "preferred": "Preferred languages",
        "manual": "Selected languages",
        "video": "Video",
        "audio": "Audio",
        "custom": "Custom",
        "Best Available": "Best",
        "2160p": "4K",
    }

    def __init__(self):
        super().__init__()
        watch_language(self, self.retranslate_ui)

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxArrow, self
        )
        painter = QPainter(self)
        _paint_arrow(painter, rect, self.isEnabled())
        painter.end()

    def retranslate_ui(self):
        blocked = self.blockSignals(True)
        edit_text = self.currentText() if self.isEditable() else None
        for i in range(self.count()):
            key = self.itemData(i, Qt.ItemDataRole.UserRole + 1)
            if key is not None:
                self.setItemText(i, tr(key))
        if edit_text is not None:
            self.setEditText(edit_text)
        self.blockSignals(blocked)

    def addItem(self, text: str, userData=None) -> None:
        value = text if userData is None else userData
        display = self.display_names.get(
            text,
            text.upper() if text in {"mp4", "webm", "mp3", "m4a", "opus", "flac", "wav"} else text,
        )
        super().addItem(tr(display), value)
        self.setItemData(self.count() - 1, display, Qt.ItemDataRole.UserRole + 1)

    def addItems(self, texts) -> None:
        for text in texts:
            self.addItem(text)

    def value(self) -> str:
        return super().currentText() if self.isEditable() else (self.currentData() or "")

    def currentText(self) -> str:
        # Existing callers expect engine values. Display remains Qt's translated itemText.
        return self.value()

    def findText(self, text: str, *_args) -> int:
        return self.findData(text)

    def setCurrentText(self, text: str) -> None:
        index = self.findData(text)
        if index >= 0:
            self.setCurrentIndex(index)
        elif self.isEditable():
            self.setEditText(text)


def combo(items: list[str], current: str = "") -> ChoiceCombo:
    widget = ChoiceCombo()
    widget.addItems(items)
    if current:
        widget.setCurrentText(current)
    return widget


def _paint_arrow(painter: QPainter, rect, enabled: bool, down: bool = True) -> None:
    # Vector strokes use Qt's logical coordinates and scale with the display DPI.
    center = rect.center()
    x, y = center.x(), center.y()
    direction = 1 if down else -1
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(tokens()["text" if enabled else "muted"]), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline(
        QPolygonF(
            [
                QPointF(x - 4, y - direction * 2),
                QPointF(x, y + direction * 2),
                QPointF(x + 4, y - direction * 2),
            ]
        )
    )


class SpinBox(QSpinBox):
    """Native numeric editing and hit targets with theme-aware step indicators."""

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        if self.buttonSymbols() != QSpinBox.ButtonSymbols.NoButtons:
            for control, step, down in (
                (QStyle.SubControl.SC_SpinBoxUp, QSpinBox.StepEnabledFlag.StepUpEnabled, False),
                (QStyle.SubControl.SC_SpinBoxDown, QSpinBox.StepEnabledFlag.StepDownEnabled, True),
            ):
                rect = self.style().subControlRect(
                    QStyle.ComplexControl.CC_SpinBox, option, control, self
                )
                _paint_arrow(
                    painter, rect, self.isEnabled() and bool(option.stepEnabled & step), down
                )
        painter.end()


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)
    return frame, layout


def disclosure(text: str, content: QWidget) -> QPushButton:
    toggle = button(text, icon_name="chevron")
    toggle.setObjectName("disclosure")
    toggle.setCheckable(True)
    content.hide()

    def expand(checked):
        content.setVisible(checked)
        symbol = "chevron_down" if checked else "chevron"
        toggle.setProperty("icon_name", symbol)
        toggle.setIcon(icon(symbol))

    toggle.toggled.connect(expand)
    return toggle


class Page(QWidget):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("page")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(24, 24, 24, 16)
        self.layout.setSpacing(16)
        self.layout.addWidget(label(title, "heading"))
        if subtitle:
            self.layout.addWidget(label(subtitle, "muted", True))


class EmptyState(QWidget):
    def __init__(self, title: str, description: str, icon_name: str = "download") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addStretch()
        image = icon_label(icon_name, 24)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(image)
        for text, style in ((title, "section"), (description, "muted")):
            item = label(text, style, True)
            item.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(item)
        layout.addStretch()


class UrlInput(QLineEdit):
    dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        bind_text(self, "setPlaceholderText", "Paste a video or playlist URL")
        bind_text(self, "setAccessibleName", "Media link")
        self.setAcceptDrops(True)
        self.setMinimumHeight(44)
        self.setMaxLength(8192)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasText() or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        text = mime.urls()[0].toString() if mime.hasUrls() else mime.text()
        self.setText(text.strip())
        self.dropped.emit(text.strip())
        event.acceptProposedAction()


class Banner(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("banner")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        row = QHBoxLayout()
        self.text = label("", wrap=True)
        self.details = label("", "muted", True)
        self.details.hide()
        self.expand = button(
            "Details", lambda: self.details.setVisible(not self.details.isVisible())
        )
        row.addWidget(self.text, 1)
        row.addWidget(self.expand)
        row.addWidget(button("Dismiss", self.hide))
        layout.addLayout(row)
        layout.addWidget(self.details)
        self.hide()

    def show_message(self, text: str, details: str = "") -> None:
        self.text.setText(translate_message(text))
        self.details.setText(translate_message(details))
        self.expand.setVisible(bool(details))
        self.details.hide()
        self.show()
