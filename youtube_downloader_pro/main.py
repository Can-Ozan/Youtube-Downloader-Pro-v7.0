import argparse
import logging
import multiprocessing
import sys
from pathlib import Path

from youtube_downloader_pro import APP_NAME, __version__


def main() -> int:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--smoke-test", action="store_true", help="Open the UI and close after initialization"
    )
    parser.add_argument(
        "--data-dir", type=Path, help="Explicit application data override for tests/portable use"
    )
    parser.add_argument("--screenshot", type=Path, help="Save the main window after initialization")
    parser.add_argument("--smoke-report", type=Path, help="Write startup diagnostics as JSON")
    args = parser.parse_args()
    if args.smoke_report and (not args.smoke_test or not args.data_dir):
        parser.error("--smoke-report requires --smoke-test and an explicit --data-dir")
    if args.data_dir:
        args.data_dir = args.data_dir.resolve()
    from youtube_downloader_pro.utils.logger import configure_logging

    configure_logging(args.data_dir / "logs" if args.data_dir else None)
    startup_log = logging.getLogger(__name__)
    startup_log.info("Starting application %s", __version__)

    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication, QStyle

        from youtube_downloader_pro.ui.main_window import MainWindow
        from youtube_downloader_pro.utils.resources import application_icon
    except Exception:
        startup_log.exception("Application imports failed")
        raise

    def report_unhandled(error_type, error, traceback):
        startup_log.error(
            "Unhandled application exception", exc_info=(error_type, error, traceback)
        )
        sys.__excepthook__(error_type, error, traceback)

    sys.excepthook = report_unhandled
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("YouTubeDownloaderPro")
    icon_path = application_icon()
    app.setWindowIcon(
        QIcon(str(icon_path))
        if icon_path
        else app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    )
    window = MainWindow(args.data_dir)
    window.show()
    if args.screenshot:
        QTimer.singleShot(1500, lambda: window.grab().save(str(args.screenshot)))
    smoke_failed = False

    def finish_smoke():
        nonlocal smoke_failed
        try:
            if args.smoke_report:
                from youtube_downloader_pro.utils.smoke import write_smoke_report

                write_smoke_report(window, args.smoke_report)
        except Exception:
            startup_log.exception("Startup smoke validation failed")
            smoke_failed = True
        finally:
            window.close()

    if args.smoke_test:
        QTimer.singleShot(2000, finish_smoke)
    result = app.exec()
    return 1 if smoke_failed else result


if __name__ == "__main__":
    raise SystemExit(main())
