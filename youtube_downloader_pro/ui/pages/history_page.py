from datetime import UTC, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QTableView,
    QWidget,
)

from youtube_downloader_pro.i18n import tr
from youtube_downloader_pro.ui.design import HISTORY_ROW_HEIGHT
from youtube_downloader_pro.ui.localization import bind_text, watch_language
from youtube_downloader_pro.ui.widgets.common import (
    EmptyState,
    Page,
    button,
    combo,
    disclosure,
    label,
)
from youtube_downloader_pro.ui.widgets.row_delegate import HistoryDelegate


class HistoryPage(Page):
    search_requested = Signal(dict)
    action = Signal(str, object)
    clear_requested = Signal()

    def __init__(self) -> None:
        super().__init__(
            "History", "Completed, failed, and cancelled downloads, saved on this device."
        )
        self.offset = 0
        self.rows: list[dict] = []
        self.search = QLineEdit()
        bind_text(self.search, "setPlaceholderText", "Search by title")
        self.status = combo([])
        self.status.addItem("All statuses", "All")
        self.status.addItems(["Completed", "Failed", "Cancelled"])
        self.mode = combo(["All", "video", "audio", "custom"])
        self.format = combo([])
        self.format.addItem("All formats", "All")
        self.format.addItems(["mp4", "webm", "mp3", "m4a", "opus", "flac", "wav"])
        bind_text(self.format, "setToolTip", "Format")
        self.date = combo(["Any time", "Today", "Last 7 days", "Last 30 days"])
        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(self.status)
        filters.addWidget(self.format)
        filters.addWidget(button("Refresh", self.refresh))
        self.layout.addLayout(filters)
        self.extra_filters = QWidget()
        extra = QHBoxLayout(self.extra_filters)
        extra.setContentsMargins(0, 0, 0, 0)
        extra.addWidget(label("Media type", "caption"))
        extra.addWidget(self.mode)
        extra.addWidget(label("Date", "caption"))
        extra.addWidget(self.date)
        extra.addStretch()
        filter_toggle = disclosure("Filters", self.extra_filters)
        self.layout.addWidget(filter_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.extra_filters)
        self.model = QStandardItemModel(0, 1)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(HISTORY_ROW_HEIGHT)
        self.table.horizontalHeader().hide()
        self.table.setItemDelegate(HistoryDelegate(self.table))
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.empty = EmptyState(
            "Your download history is empty.", "Finished downloads will appear here.", "history"
        )
        self.layout.addWidget(self.empty, 1)
        self.table.hide()
        self.layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.record_actions = {}
        for text, action in (
            ("Open File", "open_file"),
            ("Open Folder", "open_folder"),
            ("Retry download", "retry"),
        ):
            control = button(text, lambda _=False, a=action: self._action(a))
            self.record_actions[action] = control
            actions.addWidget(control)
        actions.addStretch()
        more = button("History actions", icon_name="more")
        menu = QMenu(more)
        for text, callback in (
            ("Copy URL", lambda: self._action("copy_url")),
            ("Clear history", self.clear_requested.emit),
        ):
            action = menu.addAction(tr(text), callback)
            bind_text(action, "setText", text)
        more.setMenu(menu)
        actions.addWidget(more)
        self.layout.addLayout(actions)
        self.table.selectionModel().currentChanged.connect(self._update_actions)
        self._update_actions()
        pagination = QHBoxLayout()
        self.info = label("Loading history…", "muted")
        pagination.addWidget(self.info, 1)
        self.previous = button("Previous", lambda: self._page(-100))
        self.next = button("Next", lambda: self._page(100))
        pagination.addWidget(self.previous)
        pagination.addWidget(self.next)
        self.layout.addLayout(pagination)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(250)
        self.debounce.timeout.connect(self.refresh)
        self.search.textChanged.connect(self._changed)
        for widget in (self.status, self.mode, self.date, self.format):
            widget.currentTextChanged.connect(self._changed)
        watch_language(self, self.retranslate_ui)

    def retranslate_ui(self) -> None:
        for index, row in enumerate(self.rows):
            self.model.item(index).setText(row["title"] + " · " + tr(row["status"]))
        self.table.viewport().update()

    def _changed(self) -> None:
        self.offset = 0
        self.debounce.start()

    def _page(self, delta: int) -> None:
        self.offset = max(0, self.offset + delta)
        self.refresh()

    def refresh(self) -> None:
        days = [None, 0, 7, 30][self.date.currentIndex()]
        since = ""
        if days is not None:
            since = (
                (datetime.now().astimezone() - timedelta(days=days))
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .astimezone(UTC)
                .isoformat()
            )
        self.search_requested.emit(
            {
                "query": self.search.text(),
                "status": self.status.currentText(),
                "mode": self.mode.currentText(),
                "since": since,
                "offset": self.offset,
                "limit": 100,
                "format_filter": self.format.currentText(),
            }
        )

    def set_rows(self, rows: list[dict]) -> None:
        self.rows = rows
        self.model.removeRows(0, self.model.rowCount())
        for row in rows:
            item = QStandardItem(row["title"] + " · " + tr(row["status"]))
            item.setData(row, Qt.ItemDataRole.UserRole)
            self.model.appendRow(item)
        self.empty.setVisible(not rows)
        self.table.setVisible(bool(rows))
        self.info.setText(
            tr("{count} records · Page {page}", count=len(rows), page=self.offset // 100 + 1)
            if rows
            else tr("No matching downloads.")
        )
        self.previous.setEnabled(self.offset > 0)
        self.next.setEnabled(len(rows) == 100)

    def _action(self, action: str) -> None:
        index = self.table.currentIndex()
        if index.isValid():
            self.action.emit(action, self.rows[index.row()])

    def _update_actions(self, *_args):
        row = self.table.currentIndex().data(Qt.ItemDataRole.UserRole)
        for action, control in self.record_actions.items():
            control.setEnabled(bool(row) and (action == "retry" or bool(row["output_file"])))
