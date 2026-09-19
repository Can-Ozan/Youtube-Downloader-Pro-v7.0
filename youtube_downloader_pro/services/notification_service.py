from PySide6.QtWidgets import QSystemTrayIcon

from youtube_downloader_pro import APP_NAME


class NotificationService:
    def __init__(self, parent) -> None:
        self.tray = QSystemTrayIcon(parent.windowIcon(), parent)
        self.tray.setToolTip(APP_NAME)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def notify(self, message: str, enabled: bool, failed: bool = False) -> None:
        if enabled and self.tray.isVisible() and QSystemTrayIcon.supportsMessages():
            kind = (
                QSystemTrayIcon.MessageIcon.Warning
                if failed
                else QSystemTrayIcon.MessageIcon.Information
            )
            self.tray.showMessage(APP_NAME, message, kind, 4000)
