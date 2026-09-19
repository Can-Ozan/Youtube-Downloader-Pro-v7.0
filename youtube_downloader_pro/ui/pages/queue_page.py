from PySide6.QtCore import QSize, QSortFilterProxyModel, Qt, QTimer, Signal
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
from youtube_downloader_pro.models.download_status import DownloadStatus as Status
from youtube_downloader_pro.ui.design import DOWNLOAD_ROW_HEIGHT
from youtube_downloader_pro.ui.localization import bind_text, watch_language
from youtube_downloader_pro.ui.widgets.common import (
    EmptyState,
    Page,
    button,
    combo,
    disclosure,
    label,
)
from youtube_downloader_pro.ui.widgets.download_card import DownloadTableModel
from youtube_downloader_pro.ui.widgets.row_delegate import DownloadDelegate


class QueueFilter(QSortFilterProxyModel):
    query = ""
    status = "All"

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        item = self.sourceModel().items[source_row]
        return (self.query in item.title.casefold() or self.query in item.url.casefold()) and (
            self.status == "All" or item.status.value == self.status
        )


class QueuePage(Page):
    action = Signal(str, str)
    start_requested = Signal()
    schedule_requested = Signal(str)
    cancel_schedule = Signal()

    def __init__(self, thumbnails) -> None:
        super().__init__("Downloads")
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        bind_text(self.search, "setPlaceholderText", "Search downloads")
        self.filter = combo([])
        self.filter.addItem("All statuses", "All")
        self.filter.addItems([s.value for s in Status])
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.filter)
        more = button("Queue actions", icon_name="more")
        bulk_menu = QMenu(more)
        for text, action in (
            ("Retry Failed", "retry_failed"),
            ("Clear Completed", "clear_completed"),
            ("Cancel All", "cancel_all"),
        ):
            item = bulk_menu.addAction(tr(text), lambda a=action: self.action.emit(a, ""))
            bind_text(item, "setText", text)
        more.setMenu(bulk_menu)
        toolbar.addWidget(more)
        self.layout.addLayout(toolbar)
        self.model = DownloadTableModel(thumbnails)
        self.proxy = QueueFilter()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(DOWNLOAD_ROW_HEIGHT)
        self.table.horizontalHeader().hide()
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setIconSize(QSize(72, 42))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, self.model.columnCount()):
            self.table.hideColumn(column)
        delegate = DownloadDelegate(self.table)
        self.table.setItemDelegateForColumn(0, delegate)
        delegate.overflow.connect(self._menu)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.doubleClicked.connect(
            lambda idx: self.action.emit("details", idx.data(Qt.ItemDataRole.UserRole).id)
        )
        self.empty = EmptyState(
            "No active downloads yet.", "Analyze a link on Home to start your first download."
        )
        self.layout.addWidget(self.empty, 1)
        self.layout.addWidget(self.table, 1)
        self.proxy.rowsInserted.connect(self._empty_state)
        self.proxy.rowsRemoved.connect(self._empty_state)
        self.proxy.modelReset.connect(self._empty_state)
        self._empty_state()
        actions = QHBoxLayout()
        self.context_actions = {}
        for text, action in (
            ("Cancel", "cancel"),
            ("Retry", "retry"),
            ("Open File", "open_file"),
            ("Open Folder", "open_folder"),
        ):
            control = button(text, lambda _=False, a=action: self._selected_action(a))
            self.context_actions[action] = control
            actions.addWidget(control)
        self.table.selectionModel().selectionChanged.connect(self._update_actions)
        self.model.dataChanged.connect(self._selected_data_changed)
        self._update_actions()
        actions.addStretch()
        actions.addWidget(label("More actions: right-click a download", "caption"))
        self.layout.addLayout(actions)
        footer = QHBoxLayout()
        self.schedule_label = label("Start when you are ready.", "muted")
        self.schedule_label.setWordWrap(True)
        self.layout.addWidget(self.schedule_label)
        self.schedule_controls = QWidget()
        schedule = QHBoxLayout(self.schedule_controls)
        schedule.setContentsMargins(0, 0, 0, 0)
        self.time = QLineEdit()
        bind_text(self.time, "setPlaceholderText", "HH:MM")
        self.time.setMaximumWidth(85)
        schedule.addWidget(self.time)
        schedule.addWidget(
            button("Start at…", lambda: self.schedule_requested.emit(self.time.text()))
        )
        schedule.addWidget(button("Cancel schedule", self.cancel_schedule.emit))
        footer.addWidget(disclosure("Schedule", self.schedule_controls))
        footer.addStretch()
        footer.addWidget(button("Start now", self.start_requested.emit, True))
        self.layout.addWidget(self.schedule_controls)
        self.layout.addLayout(footer)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(300)
        self.debounce.timeout.connect(self._filter)
        self.search.textChanged.connect(lambda: self.debounce.start())
        self.filter.currentTextChanged.connect(self._filter)
        watch_language(self, self.retranslate_ui)

    def retranslate_ui(self) -> None:
        self.model.retranslate_ui()
        self.table.viewport().update()

    def _filter(self) -> None:
        self.proxy.beginFilterChange()
        self.proxy.query = self.search.text().casefold()
        self.proxy.status = self.filter.currentText()
        self.proxy.endFilterChange()
        self._empty_state()

    def _empty_state(self, *_args) -> None:
        empty = self.proxy.rowCount() == 0
        self.empty.setVisible(empty)
        self.table.setVisible(not empty)

    def _selected_action(self, action: str) -> None:
        for index in self.table.selectionModel().selectedRows():
            item = index.data(Qt.ItemDataRole.UserRole)
            if self._action_available(action, item):
                self.action.emit(action, item.id)

    @staticmethod
    def _action_available(action, item):
        if action == "cancel":
            return not item.status.terminal
        if action == "retry":
            return item.status in {Status.FAILED, Status.CANCELLED}
        return item.status == Status.COMPLETED and bool(item.output_file)

    def _update_actions(self, *_args):
        items = [
            idx.data(Qt.ItemDataRole.UserRole) for idx in self.table.selectionModel().selectedRows()
        ]
        for action, control in self.context_actions.items():
            control.setVisible(any(self._action_available(action, item) for item in items))

    def _selected_data_changed(self, first, last, *_args):
        # Most progress notifications don't affect the selected item; don't rebuild controls.
        for index in self.table.selectionModel().selectedRows():
            row = self.proxy.mapToSource(index).row()
            if first.row() <= row <= last.row():
                self._update_actions()
                break

    def _menu(self, position) -> None:
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        key = index.data(Qt.ItemDataRole.UserRole).id
        menu = QMenu(self)
        for name, action in (
            ("Cancel", "cancel"),
            ("Retry", "retry"),
            ("Download again anyway", "again"),
            ("Remove", "remove"),
            ("Open File", "open_file"),
            ("Open Folder", "open_folder"),
            ("Copy Source URL", "copy_url"),
            ("Details", "details"),
        ):
            item = menu.addAction(tr(name), lambda a=action: self.action.emit(a, key))
            bind_text(item, "setText", name)
        menu.exec(self.table.viewport().mapToGlobal(position))
        menu.deleteLater()
