# Windows x64 distribution

The primary build is PyInstaller ONEDIR for Windows 10/11 x64. The entire
`dist/YouTube Downloader Pro/` folder is required. `YouTube Downloader Pro.exe`
calls the existing compatibility launcher and the same `main()` as
`python -m youtube_downloader_pro`. Python, Qt, yt-dlp, mutagen and SQLite are bundled.
The user does not need Python, pip or development tools.

## Build and package

Use Windows with Python 3.11 or 3.12 x64 (3.12 is used for release CI):

```powershell
py -3.12 -m venv .venv
./scripts/build_windows.ps1 -InstallDependencies
./scripts/package_release.ps1
```

Dependency installation is optional and explicit; it only installs the project
and the bounded `.[dev]` requirements into a virtual environment. Subsequent
builds can omit `-InstallDependencies`. `-Python PATH` selects a different build
interpreter. Build scripts locate the repository using their own path; invoke
them from any working directory. `-DebugConsole` creates a diagnostic build;
rebuild without it before packaging a production ZIP.

`build/windows.spec` is source. `build/.work/`, `build/.cache/`, `dist/` and
`release/` are generated and ignored. `scripts/clean_build.ps1` deletes only the
first three directories; `-IncludeRelease` also clears release archives. It
validates repository containment and refuses links/junctions. `-WhatIf` previews
cleanup. It never deletes `build/` itself, the spec or user data. Older generated
`build/YouTubeDownloaderPro/` output is not used and is deliberately left alone.

The spec uses windowed mode, no UPX, no administrator request and no installer,
registry modifications or updater. Python's multiprocessing freeze support is
executed before application startup. Metadata and archive names read the sole
version source: `youtube_downloader_pro/__init__.py`.

Place the finished icon at `assets/icons/app.ico`. The EXE and application use
that same file; no icon is generated when absent. Runtime icons, QSS themes and
QM translations under `assets/` are collected if present. Current themes are
Python code. The English/Turkish JSON catalogs and Qt’s Turkish standard-control
translations are explicitly collected and checked against source. Standard PyInstaller Qt hooks
collect the required platform/image plugins; yt-dlp's dynamic modules are
explicitly collected without unrelated installed packages. BUILD-INFO.json
records actual build dependency versions. This is not a pinned/reproducible
dependency lock or a claim that every dependency notice is complete.

## Runtime paths and checks

`utils/resources.py` centralizes source/frozen resource lookup. ONEDIR resources,
including optional FFmpeg, live in `_internal/`. Settings/history/archive and
logs retain their platformdirs locations under the user's profile; the app
never defaults to storing user data in its installation directory. `--data-dir`
is an explicit developer/test override.

The build runs pytest, Ruff, compileall and source startup before PyInstaller.
The output audit checks x64/windowed metadata, embedded application/engine
modules, Qt/SQLite/Python dependencies, assets, and development/private file
patterns. Each runtime file receives a SHA256 fingerprint. This is a targeted
artifact audit, not a guarantee that arbitrary credentials can be detected.

The packaged smoke test copies the output to a path with spaces, Turkish and
Japanese characters, starts it from an unrelated folder with only Windows
System32 in PATH, and checks Qt startup, a spawned child importing yt-dlp,
resource lookup, settings persistence and a SQLite write/rollback. It uses Qt's
offscreen platform, so it does not substitute for native visual testing on a
clean Windows 10/11 machine without Python. Diagnostics are under `build/.work/`.

Windows Application Control has blocked locally generated unsigned executables
with WinError 4551 on this machine. A failed startup fails a normal build. To
retain a local test candidate when an OS security policy specifically blocks
execution, use `-AllowBlockedSmokeTest`, then `package_release.ps1 -AllowUnverified`.
These flags do not change security policy, retry through another launcher or
mark startup passed. The ZIP's adjacent validation JSON records the failure.
CI never uses either flag. Do not publish an unverified candidate as tested.

Unsigned executables can trigger SmartScreen/antivirus reputation warnings.
Verify the publisher and checksum, investigate detections, and obtain trusted
signing/reputation before release. Do not blindly bypass Windows protections.

## FFmpeg distribution

Default builds include **no FFmpeg**. Full audio conversion/stream merging needs
both FFmpeg and ffprobe. Detection order is bundled `_internal/ffmpeg/`,
application-managed `%LOCALAPPDATA%/YouTubeDownloaderPro/ffmpeg/bin/`, then system
PATH. Legacy source `ffmpeg/bin/` is still supported. A bundled pair works
without PATH. The application never downloads or installs binaries.

To bundle a trusted Windows x64 build, provide a directory with `ffmpeg.exe`,
`ffprobe.exe`, their required DLLs, `licenses/` notices, and `provenance.json`:

```json
{
  "source_url": "https://supplier.example/exact-binary-release",
  "source_archive_url": "https://supplier.example/exact-corresponding-source",
  "license": "The actual license expression for this build",
  "build_configuration": "The exact FFmpeg configuration flags",
  "verification": "How the supplier signature/checksums were verified",
  "sha256": {
    "ffmpeg.exe": "64 hexadecimal characters from the verified binary",
    "ffprobe.exe": "64 hexadecimal characters from the verified binary"
  }
}
```

These are documentation examples, not download addresses or working hashes.
Record every required DLL in the hash map too. The builder verifies hashes and
x64 architecture before bounded version probes and retains provenance/notices.
It rejects nonfree configurations. This validates identity, not the supplier's
trustworthiness or completion of legal obligations.

```powershell
./scripts/build_windows.ps1 -FFmpegDirectory 'C:\Verified FFmpeg'
./scripts/package_release.ps1
```

FFmpeg licensing depends on its enabled components: LGPL normally, GPL when
GPL components are enabled. Match the binaries, configuration, source and
notices, including external libraries, before redistribution. See the
[official FFmpeg licensing guidance](https://ffmpeg.org/legal.html) and
[runtime dependency notes](THIRD_PARTY.md). No unverified test binary is bundled.

## Release workflow

`.github/workflows/windows-build.yml` runs the same pipeline on Windows x64 for
pushes, pull requests, manual dispatch and version tags. A tag must equal `v`
plus the package version. It uploads the ZIP, checksum and validation report as
workflow artifacts with read-only repository permissions. It **does not create
or publish a GitHub Release**. Test-only CI FFmpeg is not bundled.

The ZIP is `release/YouTube-Downloader-Pro-v<version>-Windows-x64.zip`, alongside
`.zip.sha256` and `.zip.validation.json`. It contains only the runtime ONEDIR
folder; Qt/Shiboken support `.py` files are retained because they are required.
Packaging refuses stale or missing smoke evidence unless explicitly making an
unverified test candidate. The archive is read back for integrity checking.

For the next release: update the single package version, run the build and
package scripts, review the validation report and dependency/provenance
notices, test on clean Windows 10 and 11 x64, then have the owner sign and
publish the reviewed ZIP/checksum from a matching tag. If signing changes a
runtime file, rerun the smoke test and packaging so fingerprints/hashes match.
Select the project license and complete Qt/FFmpeg source/notice obligations
before public distribution. ONEFILE remains deferred until ONEDIR is verified;
no second application implementation or onefile spec has been added.

Users can compare the published SHA256 with:

```powershell
Get-FileHash '.\YouTube-Downloader-Pro-v7.0.0-Windows-x64.zip' -Algorithm SHA256
```
