"""Shared dimensions and semantic palettes for native widgets and delegates."""

SPACING = (4, 8, 12, 16, 24, 32)
RADIUS = 8
CONTROL_HEIGHT = 36
SIDEBAR_WIDTH = 176
NAV_HEIGHT = 36
ICON_SIZE = 18
DOWNLOAD_ROW_HEIGHT = 104
HISTORY_ROW_HEIGHT = 72
PREVIEW_SIZE = (160, 90)
FONT_BODY = 13
FONT_META = 11
FONT_SECTION = 16
FONT_TITLE = 22

DARK = {
    "background": "#0d0f12",
    "surface": "#15181d",
    "raised": "#1b1f26",
    "hover": "#242831",
    "border": "#2b3039",
    "text": "#f0f1f5",
    "muted": "#a6aebb",
    "accent": "#a28bf4",
    "accent_fill": "#7052c7",
    "accent_hover": "#8061d2",
    "on_accent": "#ffffff",
    "success": "#75d2a4",
    "warning": "#e6c579",
    "danger": "#f193a3",
    "selected": "#292438",
}
LIGHT = {
    "background": "#f7f8fa",
    "surface": "#ffffff",
    "raised": "#edf0f4",
    "hover": "#e5e8ef",
    "border": "#d7dce5",
    "text": "#222630",
    "muted": "#5d6677",
    "accent": "#6543b9",
    "accent_fill": "#7052c7",
    "accent_hover": "#6243b4",
    "on_accent": "#ffffff",
    "success": "#21754c",
    "warning": "#876013",
    "danger": "#b8324c",
    "selected": "#ebe5fa",
}
_tokens = DARK


def tokens() -> dict[str, str]:
    return _tokens


def set_palette(light: bool) -> None:
    global _tokens
    _tokens = LIGHT if light else DARK
