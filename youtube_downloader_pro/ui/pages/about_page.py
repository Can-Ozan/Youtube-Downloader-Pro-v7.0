from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from youtube_downloader_pro import APP_NAME, REPOSITORY_URL
from youtube_downloader_pro.i18n import tr
from youtube_downloader_pro.ui.localization import watch_language
from youtube_downloader_pro.ui.widgets.common import Page, button, card, label


class AboutPage(Page):
    check_version = Signal()
    open_logs = Signal()

    def __init__(self) -> None:
        super().__init__("About", "A focused desktop workspace for the media you can download.")
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)
        frame, layout = card()
        layout.addWidget(label(APP_NAME, "section"))
        layout.addWidget(label("Developed by Yusuf Can Ozan / Can-Ozan", "muted"))
        self.system = label("Checking…", "muted", True)
        layout.addWidget(self.system)
        self.ffmpeg = label("FFmpeg: Checking…", wrap=True)
        layout.addWidget(self.ffmpeg)
        self.latest = label("Latest yt-dlp version: Not checked", "muted")
        layout.addWidget(self.latest)
        self.check_button = button("Check engine version", self.check_version.emit)
        layout.addWidget(self.check_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(
            label(
                "Source installations are updated in their virtual environment. "
                "Packaged builds receive engine updates through application releases.",
                "muted",
                True,
            )
        )
        links = QHBoxLayout()
        links.addWidget(
            button("GitHub repository", lambda: QDesktopServices.openUrl(QUrl(REPOSITORY_URL)))
        )
        links.addWidget(button("Open Logs", self.open_logs.emit))
        links.addStretch()
        layout.addLayout(links)
        body.addWidget(frame)
        body.addWidget(
            label(
                "Users are responsible for ensuring they have permission to download "
                "and store the media they process.",
                "muted",
                True,
            )
        )
        body.addWidget(
            label(
                "No telemetry. No built-in credential collection. "
                "No protection or access-control bypass.",
                "muted",
                True,
            )
        )
        body.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.layout.addWidget(scroll, 1)
        self.version_values = None
        watch_language(self, self.retranslate_ui)

    def set_versions(self, values: dict) -> None:
        self.version_values = values
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        if self.version_values is not None:
            self.system.setText(
                "\n".join(f"{tr(key)}: {tr(value)}" for key, value in self.version_values.items())
            )
