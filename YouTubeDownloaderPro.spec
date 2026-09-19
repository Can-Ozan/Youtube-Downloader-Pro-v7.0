# Compatibility specification. Windows builds use the maintained source spec.
import sys
from pathlib import Path

if sys.platform == "win32":
    specification = Path(SPECPATH) / "build" / "windows.spec"
    namespace = dict(globals(), SPECPATH=str(specification.parent))
    exec(compile(specification.read_text(encoding="utf-8"), str(specification), "exec"), namespace)
else:
    # Build on the target operating system. Version always comes from the package.
    import os
    import runpy
    
    from PyInstaller.utils.hooks import collect_submodules, copy_metadata
    from PyInstaller.utils.hooks.qt import pyside6_library_info
    
    from PySide6.QtCore import QLibraryInfo

    qt_catalog = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)) / "qtbase_tr.qm"
    root = Path(SPECPATH)
    version = runpy.run_path(str(root / "youtube_downloader_pro" / "__init__.py"))["__version__"]
    binaries = []
    if os.environ.get("YDP_BUNDLE_FFMPEG"):
        directory = Path(os.environ["YDP_BUNDLE_FFMPEG"]).resolve()
        for name in ("ffmpeg", "ffprobe"):
            path = directory / name
            if not path.is_file():
                raise SystemExit(f"Missing explicitly supplied binary: {path}")
            binaries.append((str(path), "ffmpeg/bin"))
    
    analysis = Analysis(
        [str(root / "youtube_indirici.py")], pathex=[str(root)], binaries=binaries,
        datas=[(str(qt_catalog), pyside6_library_info.qt_rel_dir + "/translations")] + copy_metadata("yt-dlp") + copy_metadata("platformdirs") + copy_metadata("psutil") + copy_metadata("mutagen") + [(str(root / "youtube_downloader_pro" / "i18n"), "youtube_downloader_pro/i18n")],
        hiddenimports=collect_submodules("yt_dlp", filter=lambda name: "__pyinstaller" not in name and not name.endswith(".__main__")),
        excludes=["tkinter", "pytest", "ruff"], noarchive=False,
    )
    pyz = PYZ(analysis.pure)
    executable = EXE(
        pyz, analysis.scripts, [], exclude_binaries=True, name="YouTubeDownloaderPro",
        debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
        console=bool(os.environ.get("YDP_DEBUG_CONSOLE")),
    )
    collection = COLLECT(executable, analysis.binaries, analysis.datas, strip=False, upx=False,
                         name="YouTubeDownloaderPro")
    if sys.platform == "darwin":
        app = BUNDLE(collection, name="YouTube Downloader Pro.app",
                     bundle_identifier="com.canozan.youtubedownloaderpro",
                     info_plist={"CFBundleShortVersionString": version, "NSHighResolutionCapable": True})
