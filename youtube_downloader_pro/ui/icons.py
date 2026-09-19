"""Small original SVG stroke icons, one visual family for both themes."""

from functools import lru_cache

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QIcon, QPixmap

from youtube_downloader_pro.ui.design import tokens

PATHS = {
    "home": ('<path d="m3 10 9-7 9 7v11h-6v-7H9v7H3z"/>'),
    "download": ('<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>'),
    "history": ('<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7m2-4v6l4 2"/>'),
    "settings": (
        '<path d="M4 6h16M4 12h16M4 18h16"/>'
        '<circle cx="8" cy="6" r="2"/>'
        '<circle cx="16" cy="12" r="2"/>'
        '<circle cx="10" cy="18" r="2"/>'
    ),
    "info": ('<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>'),
    "more": (
        '<circle cx="5" cy="12" r="1"/>'
        '<circle cx="12" cy="12" r="1"/>'
        '<circle cx="19" cy="12" r="1"/>'
    ),
    "video": ('<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3z"/>'),
    "audio": (
        '<path d="M10 17V5l10-2v12M10 8l10-2"/>'
        '<ellipse cx="7" cy="18" rx="3" ry="2"/>'
        '<ellipse cx="17" cy="16" rx="3" ry="2"/>'
    ),
    "code": ('<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>'),
    "folder": ('<path d="M3 7V4h7l3 3h8v13H3z"/>'),
    "search": ('<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>'),
    "mini": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/>'
        '<rect x="12" y="12" width="7" height="6" rx="1"/>'
    ),
    "close": ('<path d="m6 6 12 12M6 18 18 6"/>'),
    "chevron": ('<path d="m8 5 7 7-7 7"/>'),
    "chevron_down": ('<path d="m5 8 7 7 7-7"/>'),
}


@lru_cache(maxsize=128)
def _icon(name: str, color: str) -> QIcon:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
        f'<g fill="none" stroke="{color}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</g></svg>'
    )
    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(svg.encode()), "SVG")
    return QIcon(pixmap)


def icon(name: str, color: str | None = None) -> QIcon:
    return _icon(name, color or tokens()["muted"])


def refresh_icons(app) -> None:
    from PySide6.QtWidgets import QLabel, QPushButton, QTabBar

    for widget in app.allWidgets():
        if isinstance(widget, QPushButton) and (name := widget.property("icon_name")):
            color = tokens()["on_accent"] if widget.objectName() == "primary" else None
            widget.setIcon(icon(name, color))
        elif isinstance(widget, QLabel) and (name := widget.property("icon_name")):
            widget.setPixmap(icon(name).pixmap(widget.property("icon_size")))
        elif isinstance(widget, QTabBar) and (names := widget.property("icon_names")):
            for index in range(widget.count()):
                widget.setTabIcon(index, icon(names[index]))
