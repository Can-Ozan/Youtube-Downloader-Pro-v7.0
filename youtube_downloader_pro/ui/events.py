"""Bounded presentation updates. Engine transitions and download speed are untouched."""

import threading

from PySide6.QtCore import QObject, QTimer, Signal, Slot


class ProgressBuffer:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.pending: dict[str, dict] = {}
        self.states: dict[str, tuple] = {}
        self.sequence = 0

    def put(self, event: dict) -> bool:
        """Return True for a significant event that should wake Qt immediately."""
        with self.lock:
            self.sequence += 1
            event["_sequence"] = self.sequence
            if event["type"] == "removed":
                self.pending.pop(event["id"], None)
                self.states.pop(event["id"], None)
                return True
            if event["type"] != "item":
                return True
            item = event["item"]
            state = (item.status, item.message, item.title, item.thumbnail_url)
            changed = self.states.get(item.id) != state
            self.states[item.id] = state
            if changed or item.status.terminal:
                self.pending.pop(item.id, None)
                return True
            self.pending[item.id] = event
            return False

    def take(self) -> list[dict]:
        with self.lock:
            events = list(self.pending.values())
            self.pending.clear()
            return events


class UiEvents(QObject):
    immediate = Signal(object)
    wake = Signal()

    def __init__(self, callback, parent=None) -> None:
        super().__init__(parent)
        self.buffer = ProgressBuffer()
        self.callback = callback
        self.closed = False
        self.delivered: dict[str, int] = {}
        self.wake_pending = False
        self.timer = QTimer(self)
        self.timer.setInterval(125)  # At most eight visual progress batches per second.
        self.timer.timeout.connect(self.flush)
        from PySide6.QtCore import Qt

        self.immediate.connect(self.deliver, Qt.ConnectionType.QueuedConnection)
        self.wake.connect(self.start_timer, Qt.ConnectionType.QueuedConnection)

    def submit(self, event: dict) -> None:
        # Serialise sequence assignment and signal emission across engine threads.
        with self.buffer.lock:
            if self.closed:
                return
            event = dict(event)
            important = self.buffer.put(event)
            if important:
                self.immediate.emit(event)
            elif not self.wake_pending:
                self.wake_pending = True
                self.wake.emit()

    @Slot()
    def start_timer(self) -> None:
        if not self.closed and not self.timer.isActive():
            self.timer.start()

    @Slot(object)
    def deliver(self, event: dict) -> None:
        if self.closed:
            return
        key = event["item"].id if event["type"] == "item" else event.get("id")
        if key:
            sequence = event["_sequence"]
            if sequence <= self.delivered.get(key, 0):
                return
            # Retain removal sequence until shutdown so queued snapshots cannot resurrect rows.
            self.delivered[key] = sequence
        self.callback(event)

    @Slot()
    def flush(self) -> None:
        if self.closed:
            return
        events = self.buffer.take()
        for event in events:
            self.deliver(event)
        with self.buffer.lock:
            if not self.buffer.pending:
                self.wake_pending = False
                self.timer.stop()

    def shutdown(self) -> None:
        with self.buffer.lock:
            self.closed = True
            self.buffer.pending.clear()
            self.buffer.states.clear()
            self.delivered.clear()
        self.timer.stop()
