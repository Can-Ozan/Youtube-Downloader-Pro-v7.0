"""Developer-only PyInstaller build. No dependency installation or release publication."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-ffmpeg",
        type=Path,
        help="Explicit directory containing trusted ffmpeg and ffprobe binaries",
    )
    parser.add_argument(
        "--debug-console", action="store_true", help="Build with a diagnostic console"
    )
    args = parser.parse_args()
    if sys.platform == "win32":
        # Keep the old developer command on the one Windows build pipeline.
        command = [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(Path(__file__).resolve().parent / "build_windows.ps1"),
            "-Python",
            sys.executable,
        ]
        if args.with_ffmpeg:
            command.extend(["-FFmpegDirectory", str(args.with_ffmpeg.resolve(strict=True))])
        if args.debug_console:
            command.append("-DebugConsole")
        return subprocess.call(command)
    environment = os.environ.copy()
    environment.pop("YDP_BUNDLE_FFMPEG", None)
    environment.pop("YDP_DEBUG_CONSOLE", None)
    if args.debug_console:
        environment["YDP_DEBUG_CONSOLE"] = "1"
    if args.with_ffmpeg:
        directory = args.with_ffmpeg.resolve(strict=True)
        extension = ".exe" if sys.platform == "win32" else ""
        for name in ("ffmpeg", "ffprobe"):
            binary = directory / (name + extension)
            if not binary.is_file():
                parser.error(f"Missing {binary}")
            subprocess.run([str(binary), "-version"], check=True, capture_output=True, timeout=10)
        environment["YDP_BUNDLE_FFMPEG"] = str(directory)
    root = Path(__file__).resolve().parents[1]
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            str(root / "YouTubeDownloaderPro.spec"),
        ],
        cwd=root,
        env=environment,
    )


if __name__ == "__main__":
    raise SystemExit(main())
