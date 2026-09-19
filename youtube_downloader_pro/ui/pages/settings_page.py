from dataclasses import asdict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from youtube_downloader_pro.models.settings import Settings
from youtube_downloader_pro.ui.localization import bind_text
from youtube_downloader_pro.ui.widgets.common import (
    Page,
    SpinBox,
    button,
    card,
    combo,
    disclosure,
    label,
)


class SettingsPage(Page):
    save_requested = Signal(object)
    error = Signal(str)
    open_logs = Signal()

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            "Settings", "Defaults for new downloads. Existing queue items keep their own options."
        )
        self.controls: dict[str, QWidget] = {}
        self.settings = settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        choices = {
            "theme": ["dark", "light", "system"],
            "language": ["tr", "en"],
            "default_quality": [
                "Best Available",
                "2160p",
                "1440p",
                "1080p",
                "720p",
                "480p",
                "360p",
            ],
            "default_format": ["mp4", "webm"],
            "audio_format": ["mp3", "m4a", "opus", "flac", "wav"],
            "audio_bitrate": ["128", "192", "256", "320"],
            "subtitle_mode": ["none", "preferred", "manual"],
            "subtitle_format": ["srt", "vtt"],
        }
        titles = {
            "language": "Language",
            "theme": "Theme",
            "download_folder": "Download directory",
            "default_format": "Default format",
            "default_quality": "Default quality",
            "audio_format": "Audio format",
            "audio_bitrate": "Bitrate (kbps)",
            "parallel_downloads": "Concurrent downloads",
            "speed_limit": "Speed limit",
            "subtitle_mode": "Subtitles",
            "subtitle_languages": "Subtitle languages",
            "manual_subtitles": "Manual subtitles",
            "automatic_subtitles": "Automatic subtitles",
            "subtitle_format": "Subtitle file format",
            "embed_metadata": "Embed metadata",
            "embed_thumbnail": "Embed thumbnail / cover",
            "download_thumbnail": "Save thumbnail",
            "preserve_chapters": "Preserve chapters",
            "write_description": "Write description",
            "notifications": "Notifications",
            "clipboard_monitoring": "Clipboard detection",
            "history_enabled": "Save download history",
            "archive_enabled": "Skip previously downloaded media",
            "auto_open_folder": "Open folder after download",
            "mini_always_on_top": "Keep Mini Mode on top",
            "filename_template": "Filename template",
            "fragment_concurrency": "Fragments per download",
        }
        groups = {
            "General": ["language", "theme", "download_folder"],
            "Download": [
                "default_format",
                "default_quality",
                "parallel_downloads",
                "speed_limit",
            ],
            "Media": [
                "audio_format",
                "subtitle_mode",
                "embed_metadata",
                "embed_thumbnail",
                "download_thumbnail",
            ],
            "Advanced": [
                "audio_bitrate",
                "subtitle_languages",
                "manual_subtitles",
                "automatic_subtitles",
                "subtitle_format",
                "preserve_chapters",
                "notifications",
                "clipboard_monitoring",
                "history_enabled",
                "mini_always_on_top",
                "filename_template",
                "fragment_concurrency",
                "write_description",
                "archive_enabled",
                "auto_open_folder",
            ],
        }
        self.sections = {}
        for name, keys in groups.items():
            frame, layout = card()
            self.sections[name] = frame
            if name == "Advanced":
                self.advanced_toggle = disclosure("Advanced", frame)
                content_layout.addWidget(self.advanced_toggle)
            else:
                layout.addWidget(label(name, "section"))
            if name == "Advanced":
                self.ffmpeg = label("FFmpeg: Checking…", "muted")
                self.engine_version = label("yt-dlp: Checking…", "muted")
                layout.addWidget(self.ffmpeg)
                layout.addWidget(self.engine_version)
            form = QFormLayout()
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setHorizontalSpacing(24)
            form.setVerticalSpacing(12)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for key in keys:
                value = getattr(settings, key)
                if key in choices:
                    control = combo(choices[key], str(value))
                elif isinstance(value, bool):
                    control = QCheckBox()
                    control.setChecked(value)
                elif isinstance(value, int):
                    control = SpinBox()
                    control.setRange(
                        0 if key == "speed_limit" else 1,
                        5
                        if key == "parallel_downloads"
                        else 8
                        if key == "fragment_concurrency"
                        else 2_000_000_000,
                    )
                    control.setValue(value)
                else:
                    control = QLineEdit(", ".join(value) if isinstance(value, tuple) else value)
                self.controls[key] = control
                title = label(titles[key], "muted")
                bind_text(control, "setAccessibleName", titles[key])
                if key == "download_folder":
                    row = QHBoxLayout()
                    row.addWidget(control, 1)
                    row.addWidget(button("Choose…", self._choose_folder))
                    form.addRow(title, row)
                else:
                    form.addRow(title, control)
            layout.addLayout(form)
            if name == "General":
                layout.addWidget(
                    label(
                        "Language changes apply immediately.",
                        "caption",
                        True,
                    )
                )
            if name == "Download":
                layout.addWidget(
                    label(
                        "Speed limit is bytes per second per download. Use 0 for unlimited.",
                        "caption",
                        True,
                    )
                )
            if name == "Advanced":
                presets = combo(
                    ["Title + ID", "Title + Channel", "Channel / Title", "Playlist Index + Title"]
                )
                templates = [
                    "%(title)s [%(id)s].%(ext)s",
                    "%(title)s - %(uploader)s [%(id)s].%(ext)s",
                    "%(uploader)s/%(title)s [%(id)s].%(ext)s",
                    "%(playlist_index)03d - %(title)s [%(id)s].%(ext)s",
                ]
                presets.currentIndexChanged.connect(
                    lambda i, values=templates: self.controls["filename_template"].setText(
                        values[i]
                    )
                )
                layout.addWidget(label("Filename presets", "muted"))
                layout.addWidget(presets)
            content_layout.addWidget(frame)
        content_layout.addStretch()
        scroll.setWidget(content)
        self.layout.addWidget(scroll, 1)
        footer = QHBoxLayout()
        footer.addWidget(button("Open Logs", self.open_logs.emit))
        footer.addStretch()
        footer.addWidget(button("Save settings", self._save, True))
        self.layout.addLayout(footer)

    def _choose_folder(self) -> None:
        dialog = QFileDialog(self)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly)
        dialog.setDirectory(self.controls["download_folder"].text())
        bind_text(dialog, "setWindowTitle", "Download folder")
        if dialog.exec() and dialog.selectedFiles():
            self.controls["download_folder"].setText(dialog.selectedFiles()[0])
        dialog.deleteLater()

    def _save(self) -> None:
        values = asdict(self.settings)
        for key, widget in self.controls.items():
            if isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                values[key] = widget.value()
            elif isinstance(widget, QComboBox):
                values[key] = (
                    int(widget.currentText()) if key == "audio_bitrate" else widget.currentText()
                )
            else:
                values[key] = widget.text().strip()
        values["subtitle_languages"] = tuple(
            code.strip() for code in values["subtitle_languages"].split(",") if code.strip()
        )
        try:
            settings = Settings.from_dict(values)
        except (ValueError, TypeError) as exc:
            self.error.emit(str(exc))
            return
        self.save_requested.emit(settings)
