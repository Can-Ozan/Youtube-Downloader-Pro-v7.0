from unittest.mock import Mock

import pytest

from youtube_downloader_pro.utils.paths import open_path
from youtube_downloader_pro.utils.validators import ValidationError


@pytest.mark.parametrize("platform, command", [("linux", "xdg-open"), ("darwin", "open")])
def test_posix_open_uses_argument_list(monkeypatch, tmp_path, platform, command):
    path = tmp_path / "my $(filename).mp4"
    path.touch()
    launch = Mock()
    monkeypatch.setattr("sys.platform", platform)
    monkeypatch.setattr("subprocess.Popen", launch)
    open_path(path)
    launch.assert_called_once_with([command, str(path.resolve())])


def test_windows_open_is_isolated(monkeypatch, tmp_path):
    launch = Mock()
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("os.startfile", launch, raising=False)
    open_path(tmp_path)
    launch.assert_called_once_with(str(tmp_path.resolve()))


def test_cannot_launch_executable_or_missing_file(tmp_path):
    path = tmp_path / "unsafe.exe"
    path.touch()
    with pytest.raises(ValidationError):
        open_path(path)
    with pytest.raises(FileNotFoundError):
        open_path(tmp_path / "missing.mp4")
