import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts import windows_support
from youtube_downloader_pro.utils import resources
from youtube_downloader_pro.utils.paths import app_data_dir, logs_dir


def test_resources_ignore_working_directory(monkeypatch, tmp_path):
    expected = resources.resource_root()
    monkeypatch.chdir(tmp_path)
    assert resources.resource_root() == expected
    assert resources.resource_path("assets", "icons") == expected / "assets" / "icons"
    with pytest.raises(ValueError):
        resources.resource_path("..", "private")


def test_frozen_resources_and_separate_user_data(monkeypatch, tmp_path):
    bundle = tmp_path / "Test User Türkçe 日本語" / "_internal"
    icon = bundle / "assets" / "icons" / "app.ico"
    icon.parent.mkdir(parents=True)
    icon.touch()  # Path lookup test; deliberately never used as a distribution icon.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.chdir(tmp_path)
    assert resources.resource_root() == bundle
    assert resources.application_icon() == icon
    assert not app_data_dir().is_relative_to(bundle.parent)
    assert not logs_dir().is_relative_to(bundle.parent)


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        "_internal/.env.production",
        "_internal/tests/test_core.py",
        "_internal/.git/config",
        "_internal/credentials",
        "_internal/private.key",
        "_internal/project/main.py",
        "_internal/pyproject.toml",
        "_internal/direct_url.json",
    ],
)
def test_distribution_rejects_development_and_private_files(name):
    assert windows_support.unsafe_runtime_file(Path(name))


@pytest.mark.parametrize(
    "name",
    [
        "YouTube Downloader Pro.exe",
        "_internal/PySide6/__init__.py",
        "_internal/shiboken6/__init__.py",
        "_internal/assets/icons/app.ico",
        "_internal/PySide6/plugins/platforms/qwindows.dll",
    ],
)
def test_distribution_keeps_required_runtime_files(name):
    assert not windows_support.unsafe_runtime_file(Path(name))


def test_ffmpeg_requires_provenance_before_execution(tmp_path):
    (tmp_path / "provenance.json").write_text(
        json.dumps(
            {
                "source_url": "https://example.org/ffmpeg",
                "source_archive_url": "https://example.org/src",
                "license": "LGPL-2.1-or-later",
                "build_configuration": "--disable-gpl",
                "verification": "Compared supplier hashes",
                "sha256": {"ffmpeg.exe": "0" * 64, "ffprobe.exe": "0" * 64},
            }
        )
    )
    (tmp_path / "ffmpeg.exe").write_bytes(b"untrusted input")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        windows_support.ffmpeg_inputs(tmp_path)


def test_release_zip_and_checksum_reject_stale_smoke(monkeypatch, tmp_path):
    dist = tmp_path / "dist" / windows_support.APP_NAME
    (dist / "_internal").mkdir(parents=True)
    (dist / "Türkçe 日本語.txt").write_text("runtime", encoding="utf-8")
    metadata = dist / "_internal" / "BUILD-INFO.json"
    metadata.write_text(json.dumps({"debug_console": False, "icon": False, "ffmpeg": None}))
    work = tmp_path / "work"
    work.mkdir()
    (work / "packaged-smoke.json").write_text(json.dumps({"passed": True, "fingerprint": "old"}))
    monkeypatch.setattr(windows_support, "ROOT", tmp_path)
    monkeypatch.setattr(windows_support, "DIST", dist)
    monkeypatch.setattr(windows_support, "WORK", work)
    monkeypatch.setattr(
        windows_support,
        "audit_distribution",
        lambda: {
            "fingerprint": "current",
            "files": ["Türkçe 日本語.txt", "_internal/BUILD-INFO.json"],
        },
    )
    with pytest.raises(RuntimeError, match="smoke test"):
        windows_support.package_release()
    archive_path = windows_support.package_release(allow_unverified=True)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert archive.read(f"{windows_support.APP_NAME}/Türkçe 日本語.txt") == b"runtime"
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert archive_path.with_suffix(".zip.sha256").read_text().startswith(digest)
    report = json.loads(archive_path.with_suffix(".zip.validation.json").read_text())
    assert report["packaged_startup_passed"] is False


@pytest.mark.skipif(sys.platform != "win32", reason="Native PowerShell cleanup check")
def test_clean_build_preserves_source_and_release(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    root = tmp_path / "Test User Türkçe"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for name in ("clean_build.ps1", "windows_common.ps1"):
        shutil.copyfile(windows_support.ROOT / "scripts" / name, scripts / name)
    for folder in ("build/.work", "build/.cache", "dist", "release"):
        (root / folder).mkdir(parents=True)
        (root / folder / "generated.txt").touch()
    (root / "build" / "windows.spec").write_text("source configuration")
    subprocess.run([shell, "-NoProfile", "-File", str(scripts / "clean_build.ps1")], check=True)
    assert (root / "build" / "windows.spec").read_text() == "source configuration"
    assert (root / "release" / "generated.txt").is_file()
    assert not (root / "dist").exists()
    assert not (root / "build" / ".work").exists()
