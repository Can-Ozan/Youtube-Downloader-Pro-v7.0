from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from youtube_downloader_pro.i18n import tr
from youtube_downloader_pro.ui.localization import watch_language
from youtube_downloader_pro.ui.widgets.common import UrlInput, button, check, label


class MiniWindow(QWidget):
    analyze_requested = Signal(str)
    restore_requested = Signal()
    top_changed = Signal(bool)

    def __init__(self, always_on_top: bool) -> None:
        super().__init__()
        self.retranslate_ui()
        watch_language(self, self.retranslate_ui)
        self.setObjectName("page")
        self.resize(450, 230)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, always_on_top)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(label("Quick capture", "section"))
        self.url = UrlInput()
        layout.addWidget(self.url)
        row = QHBoxLayout()
        row.addWidget(button("Paste", lambda: self.url.setText(QApplication.clipboard().text())))
        row.addWidget(
            button("Analyze link", lambda: self.analyze_requested.emit(self.url.text()), True)
        )
        row.addWidget(button("Full window", self.restore_requested.emit))
        layout.addLayout(row)
        self.count = label("No active downloads", "muted")
        layout.addWidget(self.count)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.top = check("Always on top")
        self.top.setChecked(always_on_top)
        self.top.toggled.connect(self._set_top)
        layout.addWidget(self.top)

    def retranslate_ui(self) -> None:
        self.setWindowTitle("YouTube Downloader Pro · " + tr("Mini Mode"))

    def _set_top(self, value: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, value)
        self.show()
        self.top_changed.emit(value)

    def apply_top_preference(self, value: bool) -> None:
        visible = self.isVisible()
        self.top.blockSignals(True)
        self.top.setChecked(value)
        self.top.blockSignals(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, value)
        if visible:
            self.show()

    def closeEvent(self, event) -> None:
        self.restore_requested.emit()
        event.accept()
