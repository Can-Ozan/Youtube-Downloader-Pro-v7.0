# Source configuration: clean_build.ps1 preserves this file.
import os
import runpy
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

if sys.platform != "win32":
    raise SystemExit("Build this specification on Windows x64.")

root = Path(SPECPATH).resolve().parent
support = runpy.run_path(str(root / "scripts" / "windows_support.py"))
support["verify_environment"]()
version, name = support["VERSION"], support["APP_NAME"]
ffmpeg = os.environ.get("YDP_BUNDLE_FFMPEG")
binaries, datas = support["build_inputs"](
    root / "build" / ".work", Path(ffmpeg) if ffmpeg else None,
)
parts = tuple(int(part) for part in version.split(".")) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=parts, prodvers=parts, mask=0x3F, flags=0,
                     OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable("040904B0", [
        StringStruct("ProductName", name), StringStruct("FileDescription", name),
        StringStruct("CompanyName", "Yusuf Can Ozan / Can-Ozan"),
        StringStruct("FileVersion", version), StringStruct("ProductVersion", version),
        StringStruct("OriginalFilename", name + ".exe"),
    ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
)

analysis = Analysis(
    # This six-line launcher calls the same main() as python -m youtube_downloader_pro.
    [str(root / "youtube_indirici.py")], pathex=[str(root)], binaries=binaries,
    datas=datas + copy_metadata("yt-dlp") + copy_metadata("platformdirs") + copy_metadata("psutil"),
    # yt-dlp resolves extractors/postprocessors by name; include that package only.
    hiddenimports=collect_submodules(
        "yt_dlp", filter=lambda module: "__pyinstaller" not in module
        and not module.endswith(".__main__"),
    ),
    excludes=["tkinter", "pytest", "ruff", "pip", "PyInstaller", "setuptools"],
    noarchive=False,
)

# An embedded Python distribution can ship ICU with version-suffixed exports.
# Qt needs the unversioned Windows API. Do not shadow OS ICU with an incompatible
# DLL, and never copy Windows system DLLs as a workaround.
import pefile
incompatible_icu = False
for destination, source, kind in analysis.binaries:
    if Path(destination).name.lower() == "icuuc.dll":
        with pefile.PE(source) as library:
            exports = {symbol.name for symbol in library.DIRECTORY_ENTRY_EXPORT.symbols}
            incompatible_icu = b"ucnv_open" not in exports
if incompatible_icu:
    analysis.binaries = [entry for entry in analysis.binaries
                         if Path(entry[0]).name.lower() != "icuuc.dll"
                         and not Path(entry[0]).name.lower().startswith("icudt")]

icon = root / "assets" / "icons" / "app.ico"
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True, name=name,
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=os.environ.get("YDP_DEBUG_CONSOLE") == "1",
    version=version_info, icon=str(icon) if icon.is_file() else "NONE",
    contents_directory="_internal",
)
collection = COLLECT(
    executable, analysis.binaries, analysis.datas, strip=False, upx=False, name=name,
)
