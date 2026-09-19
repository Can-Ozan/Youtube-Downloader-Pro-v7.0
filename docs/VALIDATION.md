> The Windows distribution follow-up is recorded in [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md). Its current EXE startup results supersede the historical packaging blocker below.

> Historical pre-localization validation. The current result is in [FEATURE_AUDIT.md](FEATURE_AUDIT.md).

# v7 validation and delivery status

## Environment and commands

Validated locally on Windows 11, Python 3.12.14, PySide6 6.11.2, yt-dlp 2026.08.19,
pytest 9.1.1, Ruff 0.16.6, and PyInstaller 6.22.2. Generated-media tests used the
FFmpeg 7.1 binary from the imageio-ffmpeg 0.6.0 PyPI development fixture, stored only
in ignored `.test-tools/`. It is not bundled into the application or a runtime dependency.

| Check | Result |
| --- | --- |
| `python -m pytest` with `YDP_TEST_FFMPEG` set | **84 passed**, no skips |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed for all project Python files |
| `python -m compileall youtube_downloader_pro` | Passed |
| Import every application module | 42 modules imported; application version 7.0.0 |
| `python -m pip check` | No broken requirements |
| Native Windows source startup and graceful close | Passed; screenshot in `docs/screenshots/home.png` |
| Headless Qt tests | Passed, including 3,000 queue rows and a real UI-to-engine download |
| Windows PyInstaller build | Completed from the final source tree |
| Packaged executable startup | **Not verified successfully**; see blocker below |
| `git diff --check` | Passed |
| Windows/macOS/Linux CI | Configured; not dispatched or observed remotely |

Integration tests generated their own tone/video and used a local HTTP server.
They verified actual MP3/M4A/OPUS/FLAC/WAV conversion by decoding the outputs,
MP4/WebM transfer, separate audio/video merging, SRT conversion, chapter processing,
local HTML playlist analysis, progress events, and cancellation of an actual FFmpeg
child process. The UI integration test analyzed a URL, enqueued it via Home, ran
the real process-backed manager, verified output bytes, and checked saved history.

Unit tests cover unsafe URLs/templates, Unicode/reserved/long names, output
containment and collision handling, filesystems without hard links, disk estimates,
settings corruption/round trips, SQLite filters and concurrent writes, archives,
state transitions, bounded retries, queue operations, schedule validation, clipboard
deduplication, FFmpeg discovery, and cross-platform opening with mocked OS calls.

## Packaged startup blocker

The first packaged startup exposed an incompatible ICU DLL pulled from the host's
embedded Python distribution. The build specification now checks that DLL's exports
and excludes the incompatible copy so Qt can use the Windows system ICU library.
The subsequent diagnostic build was rejected by Windows Application Control with
`WinError 4551` before startup. No security-policy bypass was attempted. The final
windowed build completed, but its startup must still be validated on an authorized
Windows test machine or through the configured build CI. Compilation alone does
not establish packaged runtime correctness. Signing is not configured.

## Implementation status

**Completed:** modular architecture and compatibility entry point; PySide6 pages and
signal wiring; analysis-first workflow; dynamic source formats; real conversion and
merging; queue progress/state/cancel/retry; paged playlist selection; settings/history;
FFmpeg discovery; platform opening helper; safe staged publication; metadata,
subtitles, chapters/artwork options; archive; clipboard banner; Mini Mode; scheduler;
logging/version status; README/CHANGELOG; tests; CI and standalone build configuration.

**Partially completed or unverified:** native Linux/macOS execution and packaging;
OS notification delivery on every desktop environment; all platform-specific media
extractors and artwork/container combinations; and packaged Windows startup under
Application Control. FFmpeg discovery is tested with fixtures; this machine has no
normal FFmpeg+ffprobe installation on PATH, so the source UI correctly reports it
unavailable. Tests supply their development FFmpeg explicitly.

**Not implemented:** pause/resume, persistent live queue or schedules across restart,
translations beyond English, OS background services, automatic application updates,
installers, signing/notarization, or release publishing. DRM/authentication/CAPTCHA
and access-control bypasses are deliberately excluded. Live streams and external
archive-file import are also outside this implementation.

Real YouTube or other remote-platform downloads were not tested. Remote challenge
components and JavaScript runtime auto-discovery are disabled, so sources requiring
those mechanisms can be unavailable. The generated-media suite does not prove
compatibility with a changing remote platform.

## Final legacy and security review

- The old application is replaced by a six-line `youtube_indirici.py` launcher.
  No Tkinter imports or duplicate download engine remain in production code.
- The accidental `.gitignoregit` file was removed; `.gitignore` now excludes local
  environments, test media, caches, and build products while retaining the build spec.
- No bare `except`, unfinished `pass`, TODO/FIXME markers, unsafe ZIP extraction,
  `shell=True`, embedded credentials, or runtime package-install commands were found.
- `os.startfile` remains only inside the guarded Windows branch of the cross-platform
  file-opening helper. Linux/macOS use argument lists with `xdg-open`/`open`.
- Qt's `app.exec()` and context-menu `exec()` are event-loop calls, not code execution.
- The outdated web-stack claims and unsupported license badge were removed from README.
- No project license was selected. No commits, pushes, releases, or publishing were performed.

## Cleanup and next steps

No additional production source files need removal. Keep the compatibility launcher.
Ignored `.test-artifacts/`, `.test-tools/`, `build/`, and `dist/` can be deleted after
review if their diagnostics/test fixture/build output is no longer needed. Removing
`.test-tools/` means conversion tests need a normal FFmpeg installation or another
explicit `YDP_TEST_FFMPEG` path.

Next: install trusted FFmpeg+ffprobe for normal desktop use; run the configured CI
matrix; test the packaged build on an authorized/signing-enabled Windows machine;
and validate representative media you own on the desired source platforms. Review
dependency redistribution terms and select the project license before distributing.

## File inventory

Modified: `.gitignore`, `README.md`, `youtube_indirici.py`.
Removed: `.gitignoregit`.

Created files:

- `.github/workflows/ci.yml`
- `CHANGELOG.md`
- `YouTubeDownloaderPro.spec`
- `docs/AUDIT.md`
- `docs/screenshots/home.png`
- `pyproject.toml`
- `scripts/build.py`
- `tests/conftest.py`
- `tests/test_engine.py`
- `tests/test_integration.py`
- `tests/test_manager.py`
- `tests/test_open_paths.py`
- `tests/test_persistence.py`
- `tests/test_process_cancellation.py`
- `tests/test_ui.py`
- `tests/test_validation.py`
- `youtube_downloader_pro/__init__.py`
- `youtube_downloader_pro/__main__.py`
- `youtube_downloader_pro/core/__init__.py`
- `youtube_downloader_pro/core/clipboard_service.py`
- `youtube_downloader_pro/core/download_manager.py`
- `youtube_downloader_pro/core/errors.py`
- `youtube_downloader_pro/core/ffmpeg_manager.py`
- `youtube_downloader_pro/core/scheduler.py`
- `youtube_downloader_pro/core/worker.py`
- `youtube_downloader_pro/core/ytdlp_service.py`
- `youtube_downloader_pro/main.py`
- `youtube_downloader_pro/models/__init__.py`
- `youtube_downloader_pro/models/download_item.py`
- `youtube_downloader_pro/models/download_status.py`
- `youtube_downloader_pro/models/settings.py`
- `youtube_downloader_pro/services/__init__.py`
- `youtube_downloader_pro/services/archive_service.py`
- `youtube_downloader_pro/services/history_service.py`
- `youtube_downloader_pro/services/notification_service.py`
- `youtube_downloader_pro/services/settings_service.py`
- `youtube_downloader_pro/services/update_service.py`
- `youtube_downloader_pro/ui/__init__.py`
- `youtube_downloader_pro/ui/main_window.py`
- `youtube_downloader_pro/ui/pages/__init__.py`
- `youtube_downloader_pro/ui/pages/about_page.py`
- `youtube_downloader_pro/ui/pages/history_page.py`
- `youtube_downloader_pro/ui/pages/home_page.py`
- `youtube_downloader_pro/ui/pages/queue_page.py`
- `youtube_downloader_pro/ui/pages/settings_page.py`
- `youtube_downloader_pro/ui/theme.py`
- `youtube_downloader_pro/ui/widgets/__init__.py`
- `youtube_downloader_pro/ui/widgets/common.py`
- `youtube_downloader_pro/ui/widgets/download_card.py`
- `youtube_downloader_pro/ui/widgets/media_preview.py`
- `youtube_downloader_pro/ui/widgets/mini_window.py`
- `youtube_downloader_pro/ui/widgets/playlist_selector.py`
- `youtube_downloader_pro/ui/widgets/progress_widget.py`
- `youtube_downloader_pro/utils/__init__.py`
- `youtube_downloader_pro/utils/formatting.py`
- `youtube_downloader_pro/utils/logger.py`
- `youtube_downloader_pro/utils/paths.py`
- `youtube_downloader_pro/utils/staged_output.py`
- `youtube_downloader_pro/utils/validators.py`
- `docs/VALIDATION.md`
