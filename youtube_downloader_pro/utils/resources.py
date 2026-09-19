"""Read-only application resources; writable user data lives in utils.paths."""

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen():
        # PyInstaller ONEDIR places dependencies in _internal; ONEFILE extracts them.
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    root = resource_root()
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Resource paths must stay inside the application resources")
    return path


def application_icon() -> Path | None:
    path = resource_path("assets", "icons", "app.ico")
    return path if path.is_file() else None
