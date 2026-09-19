"""Build-time validation and packaging, never imported by the application."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = runpy.run_path(str(ROOT / "youtube_downloader_pro" / "__init__.py"))
APP_NAME = PACKAGE["APP_NAME"]
VERSION = PACKAGE["__version__"]
DIST = ROOT / "dist" / APP_NAME
WORK = ROOT / "build" / ".work"
RUNTIME_PACKAGES = (
    "PySide6",
    "PySide6-Essentials",
    "PySide6-Addons",
    "shiboken6",
    "yt-dlp",
    "platformdirs",
    "psutil",
    "mutagen",
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_environment() -> None:
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise RuntimeError("Build with 64-bit Python on Windows 10/11 x64")
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("This specification targets Windows x64, not ARM64")
    if not (3, 11) <= sys.version_info[:2] <= (3, 12):
        raise RuntimeError("Use the tested Python 3.11 or 3.12 x64 build environment")
    for name in (*RUNTIME_PACKAGES, "PyInstaller", "pytest", "ruff"):
        print(f"{name}: {importlib.metadata.version(name)}")


def ffmpeg_inputs(directory: Path) -> tuple[list, list, dict]:
    """Require an explicit, hash-verified distribution and its licensing record."""
    directory = directory.resolve(strict=True)
    manifest_path = directory / "provenance.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for field in (
        "source_url",
        "source_archive_url",
        "license",
        "build_configuration",
        "verification",
    ):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise ValueError(f"FFmpeg provenance is missing {field}")
    if "--enable-nonfree" in manifest["build_configuration"]:
        raise ValueError("Nonfree FFmpeg builds cannot be redistributed by this pipeline")
    hashes = manifest.get("sha256", {})
    if not {"ffmpeg.exe", "ffprobe.exe"}.issubset(hashes):
        raise ValueError("Record SHA256 for both ffmpeg.exe and ffprobe.exe")
    binaries = []
    for name, expected in hashes.items():
        if (
            Path(name).name != name
            or name not in {"ffmpeg.exe", "ffprobe.exe"}
            and not name.lower().endswith(".dll")
        ):
            raise ValueError(f"Unexpected FFmpeg runtime filename: {name}")
        path = directory / name
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError("FFmpeg inputs cannot redirect outside the supplied directory")
        if not isinstance(expected, str) or sha256(path) != expected.lower():
            raise ValueError(f"FFmpeg SHA256 mismatch: {name}")
        import pefile

        with pefile.PE(str(path), fast_load=True) as pe:
            if pe.FILE_HEADER.Machine != 0x8664:
                raise ValueError(f"FFmpeg input is not Windows x64: {name}")
        binaries.append((str(path), "ffmpeg"))
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        result = subprocess.run(
            [str(directory / name), "-version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if "--enable-nonfree" in result.stdout + result.stderr:
            raise ValueError("FFmpeg binary reports a non-redistributable configuration")
    licenses = list((directory / "licenses").rglob("*"))
    license_files = [p for p in licenses if p.is_file()]
    if not license_files:
        raise ValueError("Supply FFmpeg and dependency license notices in licenses/")
    datas = [(str(manifest_path), "ffmpeg")]
    for path in license_files:
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError("License files cannot redirect outside the FFmpeg directory")
        if path.suffix.lower() not in {"", ".txt", ".md", ".html"}:
            raise ValueError(f"Unexpected license file: {path.name}")
        datas.append((str(path), str(Path("ffmpeg") / path.relative_to(directory).parent)))
    return binaries, datas, manifest


def build_inputs(work: Path, ffmpeg: Path | None = None) -> tuple[list, list]:
    binaries, datas, provenance = ffmpeg_inputs(ffmpeg) if ffmpeg else ([], [], None)
    assets = ROOT / "assets"
    for folder, extensions in {
        "icons": {".ico", ".png", ".svg"},
        "themes": {".qss"},
        "translations": {".qm"},
    }.items():
        for path in sorted((assets / folder).rglob("*")):
            if path.is_file() and path.suffix.lower() in extensions:
                if path.is_symlink() or not path.resolve().is_relative_to(assets):
                    raise ValueError(f"Asset escapes its source directory: {path.name}")
                datas.append((str(path), str(path.relative_to(ROOT).parent)))
    for path in (ROOT / "youtube_downloader_pro" / "i18n").glob("*.json"):
        datas.append((str(path), "youtube_downloader_pro/i18n"))
    from PySide6.QtCore import QLibraryInfo

    qt_catalog = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)) / "qtbase_tr.qm"
    if not qt_catalog.is_file():
        raise RuntimeError("Qt Turkish translations are missing")
    datas.append((str(qt_catalog), "PySide6/translations"))
    dependencies = {}
    for name in RUNTIME_PACKAGES:
        distribution = importlib.metadata.distribution(name)
        dependencies[name] = distribution.version
        # Retain shipped notices without copying development metadata/direct_url.json.
        for entry in distribution.files or ():
            if ".dist-info/" in str(entry) and any(
                word in str(entry).lower() for word in ("license", "copying", "notice")
            ):
                datas.append((str(distribution.locate_file(entry)), f"licenses/{name}"))
    metadata = work / "metadata" / "BUILD-INFO.json"
    write_json(
        metadata,
        {
            "product": APP_NAME,
            "version": VERSION,
            "architecture": "Windows-x64",
            "python": platform.python_version(),
            "pyinstaller": importlib.metadata.version("PyInstaller"),
            "dependencies": dependencies,
            "ffmpeg": provenance,
            "icon": (assets / "icons" / "app.ico").is_file(),
            "debug_console": os.environ.get("YDP_DEBUG_CONSOLE") == "1",
        },
    )
    datas.extend(
        [
            (str(metadata), "."),
            (str(ROOT / "docs" / "THIRD_PARTY.md"), "."),
        ]
    )
    return binaries, datas


def unsafe_runtime_file(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    forbidden = {
        ".git",
        ".github",
        ".venv",
        "venv",
        "tests",
        "test",
        ".vscode",
        ".idea",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "pip",
        "pytest",
        "ruff",
        "pyinstaller",
        "setuptools",
        "credentials",
        ".aws",
        ".ssh",
    }
    name = path.name.lower()
    if parts & forbidden or name.startswith(".env"):
        return True
    if name in {"pyproject.toml", "direct_url.json", "conftest.py", "id_rsa", "id_ed25519"}:
        return True
    if path.suffix.lower() in {".key", ".pfx", ".p12", ".spec", ".ps1", ".sqlite3", ".log"}:
        return True
    # PySide6 and Shiboken load their small support modules from disk at runtime.
    return path.suffix.lower() == ".py" and not parts & {"pyside6", "shiboken6"}


def audit_distribution(directory: Path = DIST) -> dict:
    import pefile
    from PyInstaller.archive.readers import CArchiveReader

    executable = directory / f"{APP_NAME}.exe"
    if not executable.is_file():
        raise RuntimeError(f"Missing executable: {executable}")
    metadata = json.loads((directory / "_internal" / "BUILD-INFO.json").read_text("utf-8"))
    if metadata["version"] != VERSION:
        raise RuntimeError("Distribution version differs from the package source")
    for code in ("en", "tr"):
        path = directory / "_internal" / "youtube_downloader_pro" / "i18n" / f"{code}.json"
        source = ROOT / "youtube_downloader_pro" / "i18n" / path.name
        expected = json.loads(source.read_text("utf-8"))
        if json.loads(path.read_text("utf-8")) != expected:
            raise RuntimeError(f"Packaged {code} translations differ from source")
    if not (directory / "_internal" / "PySide6" / "translations" / "qtbase_tr.qm").is_file():
        raise RuntimeError("Packaged Qt Turkish translations are missing")
    with pefile.PE(str(executable)) as pe:
        if pe.FILE_HEADER.Machine != 0x8664:
            raise RuntimeError("Executable is not x64")
        expected_subsystem = 3 if metadata["debug_console"] else 2
        if pe.OPTIONAL_HEADER.Subsystem != expected_subsystem:
            raise RuntimeError("Executable console/windowed mode is incorrect")
        strings = {}
        for group in pe.FileInfo:
            for info in group:
                for table in getattr(info, "StringTable", []):
                    strings.update(table.entries)
        for field, value in {
            b"ProductName": APP_NAME,
            b"FileDescription": APP_NAME,
            b"FileVersion": VERSION,
            b"ProductVersion": VERSION,
            b"OriginalFilename": f"{APP_NAME}.exe",
            b"CompanyName": "Yusuf Can Ozan / Can-Ozan",
        }.items():
            if strings.get(field, b"").decode("utf-8") != value:
                raise RuntimeError(f"Invalid executable metadata: {field.decode()}")
    archive = CArchiveReader(str(executable))
    pyz = archive.open_embedded_archive("PYZ.pyz")
    required = {
        "youtube_downloader_pro.main",
        "youtube_downloader_pro.core.worker",
        "youtube_downloader_pro.utils.smoke",
        "mutagen",
        "yt_dlp",
        "yt_dlp.extractor.youtube",
        "sqlite3",
        "multiprocessing",
        "platformdirs",
        "psutil",
    }
    if missing := required - set(pyz.toc):
        raise RuntimeError(f"Missing bundled imports: {sorted(missing)}")
    if bad := {n.split(".")[0] for n in pyz.toc} & {
        "pytest",
        "pip",
        "ruff",
        "PyInstaller",
        "tkinter",
    }:
        raise RuntimeError(f"Unexpected development modules: {sorted(bad)}")
    files = {}
    secret_pattern = re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\r\n]+[A-Za-z0-9+/]{40,}|"
        rb"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,}|AKIA[A-Z0-9]{16})\b"
    )
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise RuntimeError(f"Distribution contains a link: {relative}")
        if not path.is_file():
            continue
        if unsafe_runtime_file(relative):
            raise RuntimeError(f"Unexpected development/private file: {relative}")
        if secret_pattern.search(path.read_bytes()):
            raise RuntimeError(f"Potential credential in {relative}; inspect locally")
        files[relative.as_posix()] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    required_files = (
        "_internal/PySide6/QtCore.pyd",
        "_internal/PySide6/QtWidgets.pyd",
        "_internal/PySide6/plugins/platforms/qwindows.dll",
        "_internal/_sqlite3.pyd",
    )
    for name in required_files:
        if name not in files:
            raise RuntimeError(f"Missing runtime dependency: {name}")
    if not list((directory / "_internal").glob("python3*.dll")):
        raise RuntimeError("Missing bundled Python runtime")
    if metadata["icon"] and "_internal/assets/icons/app.ico" not in files:
        raise RuntimeError("Application icon is missing from resources")
    if metadata["ffmpeg"]:
        for name, expected in metadata["ffmpeg"]["sha256"].items():
            if sha256(directory / "_internal" / "ffmpeg" / name) != expected.lower():
                raise RuntimeError(f"Packaged FFmpeg changed: {name}")
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    report = {
        "version": VERSION,
        "files": files,
        "fingerprint": fingerprint,
        "total_bytes": sum(f["bytes"] for f in files.values()),
        "passed": True,
    }
    write_json(WORK / "distribution-audit.json", report)
    return report


def smoke_distribution(allow_blocked: bool = False) -> dict:
    audit = audit_distribution()
    # Launch a copy under a Unicode/space path with an unrelated CWD and no Python PATH.
    smoke_root = ROOT / ".test-artifacts" / "windows-package"
    smoke_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="Test User Türkçe 日本語 ", dir=smoke_root
    ) as temporary:
        base = Path(temporary)
        installed = base / APP_NAME
        shutil.copytree(DIST, installed)
        cwd = base / "unrelated working directory"
        cwd.mkdir()
        data = base / "user data"
        output = base / "startup.json"
        environment = os.environ.copy()
        for key in (
            "PYTHONPATH",
            "PYTHONHOME",
            "VIRTUAL_ENV",
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
        ):
            environment.pop(key, None)
        environment["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")
        environment["QT_QPA_PLATFORM"] = "offscreen"
        result = {"passed": False, "fingerprint": audit["fingerprint"]}
        try:
            process = subprocess.run(
                [
                    str(installed / f"{APP_NAME}.exe"),
                    "--smoke-test",
                    "--data-dir",
                    str(data),
                    "--smoke-report",
                    str(output),
                ],
                cwd=cwd,
                env=environment,
                timeout=50,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if process.returncode != 0 or not output.is_file():
                raise RuntimeError(
                    f"Packaged startup failed (exit {process.returncode}); no valid report"
                )
            startup = json.loads(output.read_text("utf-8"))
            if not startup["passed"] or not startup["frozen"] or startup["version"] != VERSION:
                raise RuntimeError("Startup did not validate the frozen application")
            for field in ("settings", "history"):
                if (
                    not Path(startup[field]).is_relative_to(data)
                    or not Path(startup[field]).is_file()
                ):
                    raise RuntimeError(f"Startup persistence path failed: {field}")
            for field in ("default_data", "default_logs"):
                if Path(startup[field]).is_relative_to(installed):
                    raise RuntimeError(f"Default user data points inside the app: {field}")
            if Path(startup["resource_root"]) != installed / "_internal":
                raise RuntimeError("Frozen resources are not found beside the packaged runtime")
            result.update(passed=True, startup=startup, python_removed_from_path=True)
        except OSError as error:
            result.update(error=str(error), winerror=getattr(error, "winerror", None))
            if not allow_blocked or result["winerror"] not in {4551, 577, 1260}:
                raise
            print(f"Windows security policy blocked startup; NOT validated: {error}")
        finally:
            if data.is_dir():
                shutil.copytree(data, WORK / "packaged-smoke-data", dirs_exist_ok=True)
            write_json(WORK / "packaged-smoke.json", result)
    return result


def package_release(allow_unverified: bool = False) -> Path:
    audit = audit_distribution()
    smoke_path = WORK / "packaged-smoke.json"
    smoke = json.loads(smoke_path.read_text("utf-8")) if smoke_path.is_file() else {}
    verified = smoke.get("passed") and smoke.get("fingerprint") == audit["fingerprint"]
    if not verified and not allow_unverified:
        raise RuntimeError(
            "Run the packaged smoke test first; -AllowUnverified creates a test candidate only"
        )
    metadata = json.loads((DIST / "_internal" / "BUILD-INFO.json").read_text("utf-8"))
    if metadata["debug_console"]:
        raise RuntimeError("Rebuild without -DebugConsole before making a production ZIP")
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    path = release / f"YouTube-Downloader-Pro-v{VERSION}-Windows-x64.zip"
    temporary = path.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            for name in audit["files"]:
                archive.write(DIST / name, f"{APP_NAME}/{name}")
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("ZIP integrity check failed")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    digest = sha256(path)
    path.with_suffix(".zip.sha256").write_text(f"{digest}  {path.name}\n", encoding="ascii")
    write_json(
        path.with_suffix(".zip.validation.json"),
        {
            "version": VERSION,
            "created_utc": datetime.now(UTC).isoformat(),
            "zip_bytes": path.stat().st_size,
            "sha256": digest,
            "artifact_audit_passed": True,
            "packaged_startup_passed": bool(verified),
            "smoke_error": smoke.get("error"),
            "ffmpeg_bundled": bool(metadata["ffmpeg"]),
            "icon_supplied": metadata["icon"],
            "distribution_fingerprint": audit["fingerprint"],
        },
    )
    print(f"ZIP: {path}\nBytes: {path.stat().st_size}\nSHA256: {digest}")
    if not verified:
        print("TEST CANDIDATE: packaged startup remains unverified; do not publish as tested.")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("environment", "audit", "smoke", "package"))
    parser.add_argument("--allow-blocked", action="store_true")
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args()
    if args.command == "environment":
        verify_environment()
    elif args.command == "audit":
        report = audit_distribution()
        print(f"Audited {len(report['files'])} files, {report['total_bytes']} bytes")
    elif args.command == "smoke":
        smoke_distribution(args.allow_blocked)
    else:
        package_release(args.allow_unverified)


if __name__ == "__main__":
    main()
