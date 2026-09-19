# Runtime components and distribution notices

This test distribution contains Python, PySide6/Qt/Shiboken, yt-dlp, psutil and
platformdirs, plus mutagen for media cover artwork. Exact versions are recorded in BUILD-INFO.json. Notices supplied
by their installed wheels are retained in licenses/ and package metadata.

The repository owner has not yet selected a project license. Do not interpret
this candidate as a completed licensing review or a published release.

Qt for Python offers LGPL/GPL and commercial licensing options. Check the exact
Qt modules and third-party libraries in the artifact and provide applicable
license texts, notices and corresponding sources before public redistribution.
The currently installed Qt wheels contain only the commercial-reference notice;
copying that notice alone does not establish open-source license compliance.
See https://doc.qt.io/qtforpython-6/licenses.html and
https://doc.qt.io/qt-6/licensing.html.

Python licensing: https://docs.python.org/3/license.html.
yt-dlp: https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE.
psutil: https://github.com/giampaolo/psutil/blob/master/LICENSE.
platformdirs: https://github.com/tox-dev/platformdirs/blob/main/LICENSE.
Mutagen: https://github.com/quodlibet/mutagen/blob/main/COPYING.
PyInstaller's bootloader exception: https://pyinstaller.org/en/stable/license.html.

FFmpeg is absent unless BUILD-INFO.json contains its provenance record. When
included, ffmpeg/provenance.json identifies the supplier, binary hashes, exact
source archive, configuration and verification; ffmpeg/licenses/ holds notices.
This application invokes FFmpeg as a separate executable. FFmpeg is generally
LGPL 2.1 or later; enabling GPL components changes the applicable FFmpeg license.
Nonfree configurations are rejected by the packaging script. Match notices and
source distribution obligations to the actual build and its external libraries;
a link to upstream development sources alone is not an exact-source record.
See https://ffmpeg.org/legal.html for the project's licensing guidance.
