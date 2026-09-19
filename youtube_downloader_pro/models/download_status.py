from enum import StrEnum


class DownloadStatus(StrEnum):
    WAITING = "Waiting"
    ANALYZING = "Analyzing"
    DOWNLOADING = "Downloading"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}


ALLOWED_TRANSITIONS = {
    DownloadStatus.WAITING: {DownloadStatus.ANALYZING, DownloadStatus.CANCELLED},
    DownloadStatus.ANALYZING: {
        DownloadStatus.DOWNLOADING,
        DownloadStatus.PROCESSING,
        DownloadStatus.COMPLETED,
        DownloadStatus.FAILED,
        DownloadStatus.CANCELLED,
    },
    DownloadStatus.DOWNLOADING: {
        DownloadStatus.PROCESSING,
        DownloadStatus.COMPLETED,
        DownloadStatus.FAILED,
        DownloadStatus.CANCELLED,
        DownloadStatus.ANALYZING,
    },
    DownloadStatus.PROCESSING: {
        DownloadStatus.DOWNLOADING,
        DownloadStatus.COMPLETED,
        DownloadStatus.FAILED,
        DownloadStatus.CANCELLED,
        DownloadStatus.ANALYZING,
    },
    DownloadStatus.FAILED: {DownloadStatus.WAITING},
    DownloadStatus.CANCELLED: {DownloadStatus.WAITING},
    DownloadStatus.COMPLETED: set(),
}
