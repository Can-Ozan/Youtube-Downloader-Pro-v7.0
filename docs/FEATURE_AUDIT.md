# Final feature and release audit — 2026-09-10

This audit supersedes the earlier AUDIT/VALIDATION/WINDOWS_VALIDATION implementation
reports. Work continued in the existing checkout. No commit, push, tag or release
publication was performed. The application remains v7.0.0.

## Live language switching update — 2026-09-12

Save settings now applies Turkish/English immediately through one Qt
`languageChanged` signal. Existing pages, navigation, tabs, placeholders,
accessibility labels, tooltips, menus, playlist/folder dialogs, banners, Mini Mode,
cached media details and queue/history rows retranslate in place. Widgets created
after switching use the current catalog. Language restart instructions and their
two obsolete catalog entries were replaced by an immediate-application hint.

Language-only saves preserve analyzed media, per-media format/subtitle choices,
selections, history, queue records and running workers. Settings writes run in order
on a dedicated executor so analysis cannot delay persistence; closing immediately
after Save drains pending settings writes. The download engine was not modified.

Validation: **124 tests passed** (including six new live-language cases),
`ruff check .` passed, and `python -m compileall youtube_downloader_pro` passed.
Existing startup/import smoke tests passed in both languages with isolated profiles,
SQLite/settings round trips and spawned yt-dlp imports. Evidence is in
`.test-artifacts/live-language-full.xml` and
`.test-artifacts/live-language-smoke/{tr,en}/report.json`.
Qt tests and these smoke runs used Windows with the offscreen platform.
Previously delivered OS notifications cannot be rewritten; future notifications
use the current language and existing in-app banners update immediately.
The earlier EXE/ZIP described below were not rebuilt during this language-only pass.

## Scope and evidence

The original 591-line Tkinter application has already become a six-line compatibility
launcher. `youtube_indirici.py`, the module entry point and the GUI script all call
`youtube_downloader_pro.main.main`. There is one DownloadManager and one yt-dlp adapter.
Most v7 files remain untracked in the user's working tree, so ordinary `git diff`
does not display their contents. They were inspected separately; the tracked diff
already contains substantial legacy deletions.

| Feature | Result and evidence |
| --- | --- |
| URL analysis | Real loopback analysis and Qt-to-spawned-worker integration pass. A live YouTube analysis returned 49 formats for the Blender Foundation's Big Buck Bunny video. An older yt-dlp test video returned unavailable; this is not a download success. |
| Video / dynamic quality | MP4 and WebM downloads decode successfully; separate video/audio streams merge. Analysis discovers actual heights and format IDs; playlist choices are upper limits resolved per entry. Unavailable selections fail visibly. |
| Audio | MP3, M4A, OPUS, FLAC and WAV conversion tests decode the resulting media with real FFmpeg. Lossless formats ignore bitrate. |
| Artwork / thumbnails / descriptions | Added real MP3/M4A/OPUS/FLAC embedding tests, verified embedded tags, saved PNGs and description contents. Added the missing mutagen dependency and packaged notices/import checks. WAV and WebM reject unsupported embedding. Preview loading, cache reuse and cancellation are tested. |
| Subtitles / metadata / chapters | Real separate-stream merge with VTT-to-SRT conversion; ffprobe verifies title metadata and chapter tags. Automatic/manual subtitle selection is covered by option tests; availability depends on the source. |
| Playlist | Real local HTML playlist extraction and selection across 100-entry pages. Each selected URL becomes a normal queue job. Remote YouTube playlist downloads were not exercised. |
| Queue / parallelism | Bounded 1–5-worker executor, queue state/duplicate/removal tests, and 3,000-row UI test. Queue search and status filtering pass. |
| Cancel / retry | Waiting and active cancellation, process-tree termination, bounded transient retries, manual retry and archive override pass. Real history retry starts another download and preserves the original output. |
| Progress / speed / ETA | Engine callbacks limited to 5 Hz; Qt presentation batches at 125 ms. Immediate state changes retain sequence ordering; stale progress cannot restore removed rows. Unknown size/speed/ETA remain unavailable rather than invented. |
| History | Per-operation SQLite connections in background work; title/status/type/date/format filters and 100-row pagination. Persistence, concurrent writes, escaping and non-overlapping pages pass. History records attempts that reached a worker; cancelling a never-started item does not create an attempt. |
| Open file / folder | Windows/macOS/Linux dispatch and media-file restrictions tested with mocked OS launching. Windows-only `os.startfile` is inside the platform guard. Actual external players were not opened by the tests. |
| Scheduler | Valid time, next-day rollover, replacement/cancellation and one-shot due logic tested. App must remain open; no persistent/background schedule. |
| Clipboard watcher | Opt-in host validation and duplicate suppression tested. Qt clipboard changes trigger suggestions; nothing downloads automatically. |
| Mini mode | Show/restore and always-on-top persistence tested through Qt. Closing Mini restores the main window. |
| Notifications | Implemented via Qt system tray with availability/user-setting checks and localized banners. Desktop delivery is OS/session dependent and is not proven by offscreen tests. |
| Settings / language | Live TR/EN switching and persistence after closing/reopening pass, including busy background work and rapid saves. Existing queue entries and media choices retain their options. Concurrency changes require idle workers. |
| Dark / Light / System | All theme paths exercised. System changes update the palette and queue/history paint; both languages visually inspected at 760×480. About content now scrolls at small sizes. |
| FFmpeg | Bundled/managed/PATH detection and fallback tests pass. System FFmpeg 9.0 used for real source tests. No FFmpeg executable bundled by default. |
| yt-dlp | Installed 2026.8.19; real extraction/downloads and spawned imports tested. JavaScript runtimes/remote challenge downloads remain disabled; some YouTube formats can be missing. |
| Graceful shutdown | Cancels analysis/downloads, aborts thumbnail requests, drains decode/background work and joins processes/executors. Thumbnail exceptions now always signal completion. Tested source exit is clean. |
| Windows packaging | Real x64 windowed ONEDIR build, explicit JSON/Qt catalog resources, version metadata, archive audit and release scripts. See the artifact result below. |

## Fixes and deletions in this pass

- Sequence-aware progress delivery fixes stale state and removed-row resurrection.
- Thumbnail decoding always signals completion, even on exceptions; finished network
  replies are not aborted again. Empty thumbnail-row mappings are discarded.
- Both Home enqueue actions are unavailable while analysis is busy, preventing use
  of stale media. Start Download and history retry are exercised against real media.
- History retry now starts the queue; the date filter uses the user's local day
  converted to UTC for database comparison.
- Added mutagen for the existing OPUS/FLAC cover option; verified four cover formats.
- Localized missing validation, completion, archive, retry, settings and engine
  messages. FFmpeg shows its version identifier rather than an untranslated banner.
  Custom-format tooltips use application translations rather than extractor notes.
  Raw upstream diagnostics stay in logs.
- Playlist titles remain literal media text, never translated as navigation labels.
- Removed the unused PAUSED enum/transition, old progress delegate module, six hidden
  legacy table columns and their rendering logic, duplicate event bridge, unreachable
  Windows metadata/ICU implementations in the non-Windows spec, and 34 unused catalog
  entries/aliases. No working core feature was removed.
- Kept the functional compatibility launcher. No additional source file is currently
  marked for deletion. Generated build/cache/dist/release/test artifacts can be cleaned
  using the existing scoped scripts; do not delete build/windows.spec.

## Localization

268 matching UTF-8 keys per language, with matching format placeholders. Tests cover
English fallback for a missing Turkish entry and a malformed substitution, system
language selection, raw engine combo values, saving language, closing and reopening
with the new language, live switching in both directions, preserved active downloads,
and widgets created after switching. Standard Qt controls use qtbase_tr.qm; folder
selection uses Qt's translated dialog. Language changes apply immediately on Save.

Static user-facing strings are centralized in catalogs. UI titles, buttons, banners,
settings, status/delegate labels, tooltips and menus were audited. Media titles,
uploader names, paths, codec identifiers and technology names retain their source
text; raw external diagnostics are in logs. No accidental Turkish text is used as an
English engine value. Qt catalog loading and packaged catalog equality are validated.

## Performance

Measured with scripts/benchmark_ui.py on this Windows machine, using 1,000 synthetic
rows and 20,000 submitted progress events. Same workload before/after; individual runs
are observations, not portable performance guarantees.

| Metric | Before | After |
| --- | ---: | ---: |
| Startup to first processed show (seconds) | 0.9449 | 0.7407 |
| Flood duration (seconds) | 0.4606 | 0.2613 |
| Row notifications | 20,000 | 2,000 |
| Largest 16 ms timer gap (ms) | 230.46 | 123.76 |
| Idle CPU seconds in one second | 0.0312 | 0.0156 |
| Graceful exit | true | true |

There is still a 124 ms stall in this exaggerated workload; it is not a claim of
60 FPS under all loads. The production manager runs at most five active downloads.
No page or complete list is rebuilt for a progress event. History is paged/debounced;
queries, FFmpeg probes, version checks and media work run off the Qt thread. Network
thumbnails use Qt async requests; decode/resize runs in a bounded two-thread pool with
four active requests, a 100-entry/32 MiB cache and 4 MB response limit. The source-text
translation catalog and a small settings file are loaded locally during initialization.
Explicit smoke diagnostics may perform synchronous checks; normal UI paths do not.

## Repository scan

Reviewed TODO, FIXME, HACK, XXX, NotImplementedError, Coming soon, placeholder, stub,
bare except, swallowed exceptions, shell=True, os.startfile, pip install, developer
paths, secrets, ZIP extraction, versions and obsolete stack references.

No unfinished methods, bare except, pass-based stubs, shell=True, executable ZIP
extraction, embedded secrets or hardcoded user development paths were found in
application/build source. Remaining matches are intentional: QLineEdit placeholder
prompts, documentation of absent icons, explicit development/CI dependency installation,
and the guarded platform file opener. No application path invokes pip. An already
exited child process is ignored only for the expected psutil.NoSuchProcess race;
other failures are logged/reported. Runtime artifact auditing checks for development
files and targeted credential patterns; it is not a universal secret-detection guarantee.

## Release blockers and limits

The project still has no LICENSE selected by its owner. Packaged dependencies need a
completed license/notice/source-distribution inventory for the chosen release terms;
copying the installed Qt commercial-reference notice alone is not that inventory.
Mutagen's shipped GPL notice is now included and must be considered in that decision.
This pass does not choose a project license on the owner's behalf.

A clean-machine Windows acceptance run remains outstanding: final ZIP, no Python,
chosen FFmpeg/ffprobe installation, authorized real-platform video/audio/playlist
processing, cancellation and notifications. Local source integration and an EXE
startup smoke test do not establish that entire release scenario. Remote GitHub
Actions and native macOS/Linux were not run in this session. No icon/signing identity
or FFmpeg distribution was supplied; no substitute icon or automatic binary installer
was created. Signing and icon work are distribution choices, not proof of media behavior.

Pause/resume, persistent live queues, restart-persistent schedules, live streams,
background OS scheduling, installers and automatic publication are not advertised as
implemented. No account cookies, credentials, access-control workarounds or protection
bypasses are provided.
