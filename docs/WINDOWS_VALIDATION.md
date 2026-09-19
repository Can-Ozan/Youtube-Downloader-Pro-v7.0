# Windows distribution validation — 2026-09-10

> Historical pre-localization validation. The current result is in [FEATURE_AUDIT.md](FEATURE_AUDIT.md).

Continued the existing working tree and packaging helpers. No application
architecture rewrite, commit, tag, push or GitHub Release publication was made.

## Result

- Windows 11 x64, Python 3.12.14, PyInstaller 6.22.2.
- `python -m pytest`: **103 passed**, including local real yt-dlp/FFmpeg media
  conversions, process cancellation and the added packaging tests. FFmpeg 9.0
  was available from the system for source integration tests; it was not bundled.
- `ruff check .`: passed. `ruff format --check .`: passed.
- `python -m compileall youtube_downloader_pro`: passed.
- Source startup: passed, including Qt imports, a spawned yt-dlp process,
  settings round trip and SQLite Unicode write/rollback.
- `scripts/build_windows.ps1`: created the actual windowed x64 ONEDIR EXE with
  version 7.0.0, product/company/original filename metadata and UPX disabled.
- Packaged offscreen startup: passed with the runtime copied to a path containing
  spaces, Turkish and Japanese characters, an unrelated working directory and
  only Windows System32 in PATH. The report confirmed `frozen=true`, correct
  `_internal` resource lookup, engine imports in a spawned child and persistence
  outside the installation folder. No system Python was used to launch the EXE.
- Native EXE startup and graceful exit: passed (exit 0). Captured and inspected
  the real window. Settings, history and a nonempty log file were verified.
- The earlier session's WinError 4551 did **not** recur on this artifact. No
  security policy was changed. The build allowed recording a policy block if
  one occurred, but the generated report records a real successful startup.
- `scripts/package_release.ps1`: succeeded with normal verification required;
  the unverified-candidate flag was not needed.
- Artifact audit: **245 runtime files**, **130,326,415 bytes** uncompressed.
  Embedded application/engine modules, Python/Qt/SQLite runtime files and EXE
  metadata were checked. No loose Python sources, tests, development tools,
  `.env`, Git directories or credential patterns were found. ZIP member count
  and CRC integrity passed. PowerShell Get-FileHash matched the checksum file.
- PowerShell scripts parsed successfully. Cleanup was tested in an isolated
  fixture and preserved `build/windows.spec` and existing release files.
- Final `git diff --check`: passed; source spec is visible to Git, generated
  work/cache/dist/release paths are ignored. Reviewed the final diff and scanned
  packaging/application code for bare except, silent stubs, shell execution,
  unsafe ZIP extraction and obsolete stack references. The platform-guarded
  `os.startfile` helper and explicit developer dependency installs are intentional.

The first test attempt hit old temporary-directory permissions from the previous
sandbox session. Tests were rerun with a fresh repository-local pytest temp/cache
directory. One existing UI integration assertion assumed a byte-identical WAV
container; with system FFmpeg now present, metadata chunks changed. It now checks
the decoded PCM and audio parameters, preserving the meaningful media assertion.

## Artifacts

```text
dist/YouTube Downloader Pro/YouTube Downloader Pro.exe
release/YouTube-Downloader-Pro-v7.0.0-Windows-x64.zip
release/YouTube-Downloader-Pro-v7.0.0-Windows-x64.zip.sha256
release/YouTube-Downloader-Pro-v7.0.0-Windows-x64.zip.validation.json
```

ZIP: **55,321,056 bytes** (52.76 MiB).

SHA256:

```text
d3a41722d488fc243e52446808450bdc26f9eebc1ca4c6ba7a579b2f2a9399a7
```

Generated evidence is kept outside the distribution in
`build/.work/distribution-audit.json`, `build/.work/packaged-smoke.json`,
`.test-artifacts/source-startup.json` and
`.test-artifacts/packaged-native-current/{startup.json,home.png,data/logs/app.log}`.
Temporary Unicode installation copies are removed after the automated test.

## Remaining release work

- No `assets/icons/app.ico` was supplied; no fake icon was generated.
- FFmpeg/ffprobe are not bundled. Their detection priority and the provenance-
  checked bundling path are implemented. A real bundled FFmpeg build remains to
  be supplied and tested; the missing-FFmpeg message was correct with minimal PATH.
- Test the ZIP on clean Windows 10 and Windows 11 x64 machines without Python,
  including real media processing with the chosen FFmpeg distribution. Local
  startup checks do not establish all supported OS configurations or real-site
  behavior. Windows 10 and remote GitHub Actions have not run in this session.
- Add signing/reputation and complete project/dependency/FFmpeg licensing and
  notice/source distribution decisions before public release. The current Qt
  wheel notices alone are not a completed licensing review.
- ONEFILE, an installer and automatic Release publication are deliberately not
  configured. The tag workflow uploads reviewable artifacts only.

See [WINDOWS_BUILD.md](WINDOWS_BUILD.md) for the build/release procedure.
