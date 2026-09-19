# v6 audit and v7 migration

Inspected all four tracked files before implementation: `youtube_indirici.py`
(591 lines), `README.md`, `.gitignore`, and the accidental `.gitignoregit`.
There were no tests, dependency declarations, build configuration, or license.

| Finding in v6 | v7 resolution |
| --- | --- |
| `ignoreerrors=True` plus unconditional completion | Require successful extraction and a nonempty final media file after postprocessing. |
| Worker threads read Tk variables and mutate shared queue dictionaries | Immutable job settings, locked manager state, Qt signal delivery. |
| Abort flags only checked during transfer hooks | Isolated worker processes with process-tree cancellation, including FFmpeg. |
| Manual task counter can diverge; executor replaced while work is pending | Central bounded executor, futures tracked by item ID, deterministic shutdown. |
| A thread per analysis/schedule; invalid times loop forever | Bounded background work and one validated, cancellable queue schedule. |
| M4A label only selects best audio; no conversion | Explicit native FFmpeg audio extraction postprocessor. |
| Hardcoded resolutions, TR/EN subtitles, forced MP4 | Metadata-based format and subtitle discovery, per-job options. |
| Blocking clipboard dialogs and substring hostname checks | Opt-in event-driven clipboard banner and parsed hostname validation. |
| Full playlist materialized with no selection | Bounded flat playlist pages and individual selection. |
| FFmpeg ZIP buffered in memory, unchecked binary download | Detect system/bundled/managed FFmpeg; no application binary downloader. |
| GUI runs pip against the current interpreter | Read-only engine version check; updates belong to source maintenance/releases. |
| Windows Desktop paths, relative FFmpeg path, `os.startfile` | platformdirs, pathlib, platform-specific open helper. |
| Bare exceptions, lost diagnostics, exception variables captured in delayed lambdas | Typed errors, redacted rotating logs, explicit UI error events. |
| Settings/history lost on exit | Atomic validated JSON settings and SQLite history. |
| Mini “Dropzone” has no drop support | URL drag/drop in Home and Mini Mode. |
| Unused `is_downloading`; misplaced ignore patterns | Remove obsolete implementation and repair ignore configuration. |
| README describes an unrelated web stack and claims MIT without a LICENSE | Rewrite to match Python/Qt; leave licensing to the owner. |

Migration preserves the original `python youtube_indirici.py` entry point as a
compatibility launcher. v6 source remains available in Git history. Functional
engine tests use mocks and locally generated media, never third-party media.
