from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QScrollArea,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from youtube_downloader_pro.i18n import tr
from youtube_downloader_pro.models.download_item import DownloadOptions
from youtube_downloader_pro.models.settings import Settings
from youtube_downloader_pro.ui.icons import icon
from youtube_downloader_pro.ui.localization import bind_text, watch_language
from youtube_downloader_pro.ui.widgets.common import (
    EmptyState,
    Page,
    UrlInput,
    button,
    card,
    check,
    combo,
    disclosure,
    label,
)
from youtube_downloader_pro.ui.widgets.media_preview import MediaPreview
from youtube_downloader_pro.utils.validators import ValidationError


class HomePage(Page):
    analyze_requested = Signal(str)
    cancel_analysis = Signal()
    add_requested = Signal()
    playlist_requested = Signal()

    download_requested = Signal()

    def __init__(self, settings: Settings, thumbnails) -> None:
        super().__init__("Download media", "Your next download starts with a link.")
        self.settings = settings
        self.media: dict | None = None
        self.selected_entries: list[dict] = []
        url_row = QHBoxLayout()
        self.url = UrlInput()
        self.url.returnPressed.connect(lambda: self.analyze_requested.emit(self.url.text()))
        url_row.addWidget(self.url, 1)
        url_row.addWidget(
            button("Paste", lambda: self.url.setText(QApplication.clipboard().text()))
        )
        self.analyze_button = button(
            "Analyze", lambda: self.analyze_requested.emit(self.url.text())
        )
        url_row.addWidget(self.analyze_button)
        self.layout.addLayout(url_row)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.hide()
        self.layout.addWidget(self.busy)
        self.cancel_button = button("Cancel analysis", self.cancel_analysis.emit)
        self.cancel_button.hide()
        self.layout.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.empty = EmptyState(
            "Save something worth keeping.",
            "Paste a link above to see the available video and audio formats.",
            "video",
        )
        self.empty.setMaximumHeight(160)
        self.layout.addWidget(self.empty, 1, Qt.AlignmentFlag.AlignTop)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        self.preview = MediaPreview(thumbnails)
        content_layout.addWidget(self.preview)
        self.playlist_button = button("Select playlist videos", self.playlist_requested.emit)
        self.playlist_button.hide()
        content_layout.addWidget(self.playlist_button, 0, Qt.AlignmentFlag.AlignLeft)
        configuration = QWidget()
        config_layout = QVBoxLayout(configuration)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(12)
        self.mode = combo(["Video", "Audio", "Custom"])
        self.mode_tabs = QTabBar()
        self.mode_tabs.setDrawBase(False)
        self.mode_tabs.setProperty("icon_names", ["video", "audio", "code"])
        self.mode_tabs.setExpanding(False)
        for name, symbol in (("Video", "video"), ("Audio", "audio")):
            self.mode_tabs.addTab(icon(symbol), tr(name))
        self.mode_tabs.currentChanged.connect(self.mode.setCurrentIndex)
        config_layout.addWidget(self.mode_tabs)
        self.quality = combo(["Best Available"], settings.default_quality)
        self.container = combo(["mp4", "webm"], settings.default_format)
        self.audio_format = combo(["mp3", "m4a", "opus", "flac", "wav"], settings.audio_format)
        self.audio_quick = combo(["mp3", "m4a"])
        self.audio_quick.currentIndexChanged.connect(
            lambda: self.audio_format.setCurrentText(self.audio_quick.currentText())
        )
        self.bitrate = combo(["128", "192", "256", "320"], str(settings.audio_bitrate))
        self.custom = combo([])
        self.custom.setEditable(True)
        bind_text(self.custom, "setPlaceholderText", "Format ID or custom selector")
        bind_text(self.custom.lineEdit(), "setPlaceholderText", "Format ID or custom selector")
        self.fields = {}
        fields = QHBoxLayout()
        fields.setSpacing(16)
        for name, widget, group in (
            ("Video quality", self.quality, "Video"),
            ("Video container", self.container, "Video"),
            ("Audio format", self.audio_quick, "Audio"),
        ):
            box = QWidget()
            layout = QVBoxLayout(box)
            layout.setContentsMargins(0, 8, 0, 0)
            layout.setSpacing(8)
            layout.addWidget(label(name, "muted"))
            layout.addWidget(widget)
            fields.addWidget(box, 1)
            self.fields[widget] = (box, group)
        config_layout.addLayout(fields)
        self.format_note = label(
            "Choose a format. Original quality depends on the source.", "caption", True
        )
        config_layout.addWidget(self.format_note)
        content_layout.addWidget(configuration)
        self.advanced, advanced_layout = card()
        self.advanced_toggle = disclosure("Advanced", self.advanced)
        subform = QFormLayout()
        subform.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        subform.setSpacing(12)
        subform.addRow(label("Media type", "muted"), self.mode)
        subform.addRow(label("Audio format", "muted"), self.audio_format)
        subform.addRow(label("Bitrate (kbps)", "muted"), self.bitrate)
        subform.addRow(label("Custom format selector", "muted"), self.custom)
        self.subtitle_mode = combo(["none", "preferred", "manual"], settings.subtitle_mode)
        self.subtitle_format = combo(["srt", "vtt"], settings.subtitle_format)
        subform.addRow(label("Subtitles", "muted"), self.subtitle_mode)
        subform.addRow(label("Subtitle file format", "muted"), self.subtitle_format)
        advanced_layout.addLayout(subform)
        self.languages = QListWidget()
        self.languages.setMaximumHeight(120)
        bind_text(self.languages, "setToolTip", "Select the subtitle languages to download.")
        advanced_layout.addWidget(self.languages)
        self.flags: dict[str, QCheckBox] = {}
        checks = QGridLayout()
        names = {
            "manual_subtitles": "Manual subtitles",
            "automatic_subtitles": "Automatic subtitles",
            "embed_metadata": "Embed metadata",
            "preserve_chapters": "Preserve chapters",
            "embed_thumbnail": "Embed thumbnail / cover",
            "download_thumbnail": "Save thumbnail",
            "write_description": "Write description",
        }
        for i, (key, text) in enumerate(names.items()):
            checkbox = check(text)
            checkbox.setChecked(getattr(settings, key))
            self.flags[key] = checkbox
            checks.addWidget(checkbox, i // 2, i % 2)
        advanced_layout.addLayout(checks)
        self.again = check("Download again anyway")
        advanced_layout.addWidget(self.again)
        self.footer = QWidget()
        footer = QHBoxLayout(self.footer)
        footer.setContentsMargins(0, 0, 0, 0)
        self.destination = label(
            tr("Save to {folder}", folder=settings.download_folder), "caption", True
        )
        content_layout.addWidget(self.destination)
        footer.addWidget(self.advanced_toggle)
        footer.addStretch()
        enqueue = button("Add to queue", self.add_requested.emit)
        enqueue.setObjectName("quiet")
        footer.addWidget(enqueue)
        self.add_button = button("Start Download", self.download_requested.emit, True, "download")
        self.add_button.setEnabled(False)
        footer.addWidget(self.add_button)
        self.footer.hide()
        content_layout.addWidget(self.footer)
        content_layout.addWidget(self.advanced)
        content_layout.addStretch()
        self.scroll.setWidget(content)
        self.scroll.hide()
        self.layout.addWidget(self.scroll, 1)
        self.layout.addWidget(
            label("Only download media you own or have permission to store.", "caption", True)
        )

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.audio_format.currentIndexChanged.connect(self._audio_format_changed)
        self._audio_format_changed()
        watch_language(self, self.retranslate_ui)

    def retranslate_ui(self) -> None:
        for index, name in enumerate(("Video", "Audio", "Custom")[: self.mode_tabs.count()]):
            self.mode_tabs.setTabText(index, tr(name))
        if self.media is None:
            return
        for index, fmt in enumerate(self.media.get("formats", [])):
            self.custom.setItemData(index, self._format_tooltip(fmt), Qt.ItemDataRole.ToolTipRole)
        manual = set(self.media.get("subtitles", []))
        for index in range(self.languages.count()):
            item = self.languages.item(index)
            code = item.data(Qt.ItemDataRole.UserRole)
            source = tr("Manual" if code in manual else "Automatic")
            item.setText(f"{code}  ({source})")

    @staticmethod
    def _format_tooltip(fmt) -> str:
        return f"{fmt.get('ext')} · {fmt.get('height') or tr('Audio')} · " + tr(
            "Video / audio"
            if fmt.get("acodec") not in {None, "none"} and fmt.get("vcodec") not in {None, "none"}
            else "Video"
            if fmt.get("height")
            else "Audio"
        )

    def _mode_changed(self, *_args) -> None:
        mode = self.mode.currentText()
        # Custom appears in the main selector only after explicitly choosing it in Advanced.
        blocked = self.mode_tabs.blockSignals(True)
        if mode == "Custom":
            if self.mode_tabs.count() == 2:
                self.mode_tabs.addTab(icon("code"), tr("Custom"))
            self.advanced_toggle.setChecked(True)
        elif self.mode_tabs.count() == 3:
            self.mode_tabs.removeTab(2)
        self.mode_tabs.setCurrentIndex(self.mode.currentIndex())
        self.mode_tabs.blockSignals(blocked)
        for widget, (box, group) in self.fields.items():
            box.setVisible(mode == group)
            widget.setEnabled(mode == group)
        self.custom.setEnabled(mode == "Custom")
        self.audio_format.setEnabled(mode == "Audio")
        self.bitrate.setEnabled(
            mode == "Audio" and self.audio_format.currentText() not in {"flac", "wav"}
        )

    def _audio_format_changed(self, *_args) -> None:
        selected = self.audio_format.currentText()
        blocked = self.audio_quick.blockSignals(True)
        if self.audio_quick.count() > 2:
            self.audio_quick.removeItem(2)
        if selected not in {"mp3", "m4a"}:
            self.audio_quick.addItem(selected)
        self.audio_quick.setCurrentText(selected)
        self.audio_quick.blockSignals(blocked)
        self._mode_changed()

    def set_busy(self, busy: bool) -> None:
        self.analyze_button.setText(tr("Analyzing…" if busy else "Analyze"))
        self.analyze_button.setEnabled(not busy)
        self.busy.setVisible(busy)
        self.cancel_button.setVisible(busy)
        self.add_button.setEnabled(not busy and self.media is not None)
        self.footer.setEnabled(not busy)
        self.scroll.setEnabled(not busy)

    def set_media(self, media: dict) -> None:
        self.media = media
        self.empty.hide()
        self.scroll.show()
        self.footer.show()
        self.selected_entries = []
        self.preview.set_media(media)
        self.playlist_button.setVisible(bool(media.get("is_playlist")))
        self.playlist_button.setText(tr("Select playlist videos"))
        heights = sorted(
            {int(f["height"]) for f in media.get("formats", []) if f.get("height")}, reverse=True
        )
        if media.get("is_playlist"):
            heights = [2160, 1440, 1080, 720, 480, 360]
        self.quality.clear()
        self.quality.addItems(["Best Available", *(f"{h}p" for h in heights)])
        if self.quality.findText(self.settings.default_quality) >= 0:
            self.quality.setCurrentText(self.settings.default_quality)
        self.custom.clear()
        for fmt in media.get("formats", []):
            key = str(fmt["format_id"])
            self.custom.addItem(key)
            self.custom.setItemData(
                self.custom.count() - 1,
                self._format_tooltip(fmt),
                Qt.ItemDataRole.ToolTipRole,
            )
        self.languages.clear()
        manual = set(media.get("subtitles", []))
        automatic = set(media.get("automatic_captions", []))
        for code in sorted(manual | automatic):
            source = tr("Manual" if code in manual else "Automatic")
            entry = QListWidgetItem(f"{code}  ({source})")
            entry.setData(Qt.ItemDataRole.UserRole, code)
            entry.setCheckState(
                Qt.CheckState.Checked
                if code in self.settings.subtitle_languages
                else Qt.CheckState.Unchecked
            )
            self.languages.addItem(entry)
        self.add_button.setEnabled(True)

    def options(self) -> DownloadOptions:
        mode = self.subtitle_mode.currentText()
        languages = self.settings.subtitle_languages
        if mode == "manual":
            languages = tuple(
                self.languages.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.languages.count())
                if self.languages.item(i).checkState() == Qt.CheckState.Checked
            )
            if not languages:
                raise ValidationError(
                    "Select at least one subtitle language, or use Preferred languages."
                )
        settings = replace(
            self.settings,
            audio_format=self.audio_format.currentText(),
            audio_bitrate=int(self.bitrate.currentText()),
            subtitle_mode=mode,
            subtitle_languages=languages,
            subtitle_format=self.subtitle_format.currentText(),
            **{key: widget.isChecked() for key, widget in self.flags.items()},
        )
        return DownloadOptions(
            settings,
            self.mode.currentText().lower(),
            self.quality.currentText(),
            self.container.currentText(),
            self.custom.currentText(),
            self.again.isChecked(),
        ).validate()

    def apply_settings(self, settings: Settings) -> None:
        previous = self.settings
        self.settings = settings
        self.destination.setText(tr("Save to {folder}", folder=settings.download_folder))
        if previous.default_quality != settings.default_quality:
            quality = settings.default_quality
            self.quality.setCurrentText(
                quality if self.quality.findText(quality) >= 0 else "Best Available"
            )
        # A language/theme save must preserve choices made for the analyzed media.
        for key, control in (
            ("default_format", self.container),
            ("audio_format", self.audio_format),
            ("audio_bitrate", self.bitrate),
            ("subtitle_mode", self.subtitle_mode),
            ("subtitle_format", self.subtitle_format),
        ):
            if getattr(previous, key) != getattr(settings, key):
                control.setCurrentText(str(getattr(settings, key)))
        for key, checkbox in self.flags.items():
            if getattr(previous, key) != getattr(settings, key):
                checkbox.setChecked(getattr(settings, key))
