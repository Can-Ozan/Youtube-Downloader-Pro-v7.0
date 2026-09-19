import functools
import math
import os
import struct
import threading
import wave
from dataclasses import replace
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from youtube_downloader_pro.models.settings import Settings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def settings(tmp_path):
    return replace(Settings(), download_folder=str(tmp_path / "downloads"), notifications=False)


@pytest.fixture(scope="session")
def app():
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    if os.name == "nt":
        QFontDatabase.addApplicationFont(os.path.join(os.environ["WINDIR"], "Fonts", "segoeui.ttf"))
    yield application


@pytest.fixture
def local_media(tmp_path):
    with wave.open(str(tmp_path / "tone.wav"), "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(16000)
        sound.writeframes(
            b"".join(
                struct.pack("<h", int(math.sin(i * 2 * math.pi * 440 / 16000) * 5000))
                for i in range(8000)
            )
        )

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(tmp_path))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield tmp_path, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(3)
