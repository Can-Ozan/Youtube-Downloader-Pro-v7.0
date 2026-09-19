import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from youtube_downloader_pro.ui.design import (
    CONTROL_HEIGHT,
    FONT_BODY,
    FONT_META,
    FONT_SECTION,
    FONT_TITLE,
    RADIUS,
    set_palette,
    tokens,
)
from youtube_downloader_pro.ui.icons import refresh_icons


def apply_theme(app: QApplication, theme: str) -> None:
    light = theme == "light" or (
        theme == "system" and app.styleHints().colorScheme() == Qt.ColorScheme.Light
    )
    set_palette(light)
    c = tokens()
    if app.style().objectName().lower() != "fusion":
        app.setStyle("Fusion")
    # Windows' offscreen Qt backend does not enumerate native fonts. Load the
    # installed system font for headless checks; no font is bundled or downloaded.
    if (
        os.name == "nt"
        and app.platformName() == "offscreen"
        and "Segoe UI" not in QFontDatabase.families()
    ):
        QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / "segoeui.ttf"))
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    if os.name == "nt":
        font.setFamily("Segoe UI")
    font.setPixelSize(FONT_BODY)
    app.setFont(font)
    palette = app.palette()
    for role, key in (
        (QPalette.ColorRole.Window, "background"),
        (QPalette.ColorRole.Base, "surface"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.Button, "raised"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.Highlight, "selected"),
        (QPalette.ColorRole.HighlightedText, "text"),
    ):
        palette.setColor(role, QColor(c[key]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["muted"]))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        QWidget {{ color: {c["text"]}; font-size: {FONT_BODY}px; }}
        QMainWindow, QDialog, QWidget#page, QScrollArea > QWidget > QWidget {{
  background: {c["background"]};
        }}
        QFrame#sidebar {{ background: {c["surface"]}; border-right: 1px solid {c["border"]}; }}
        QFrame#card {{ background: {c["surface"]}; border-radius: {RADIUS}px; border: none; }}
        QFrame#banner {{ background: {c["raised"]}; border-radius: {RADIUS}px; border: none; }}
        QLabel {{ background: transparent; }}
        QLabel#heading {{ font-size: {FONT_TITLE}px; font-weight: 600; }}
        QLabel#section {{ font-size: {FONT_SECTION}px; font-weight: 600; }}
        QLabel#muted {{ color: {c["muted"]}; }}
        QLabel#caption {{ font-size: {FONT_META}px; color: {c["muted"]}; }}
        QLabel#brand {{ font-size: {FONT_BODY}px; font-weight: 600; }}
        QPushButton {{ background: {c["raised"]};
        border: 1px solid transparent;
        border-radius: {RADIUS}px;
            padding: 4px 12px; min-height: {CONTROL_HEIGHT - 12}px; font-weight: 500; }}
        QPushButton:hover {{ background: {c["hover"]}; }}
        QPushButton:focus {{ border-color: {c["accent"]}; }}
        QPushButton:pressed {{ background: {c["selected"]}; }}
        QPushButton:disabled {{ color: {c["muted"]}; background: {c["surface"]}; }}
        QPushButton#primary {{ background: {c["accent_fill"]}; color: {c["on_accent"]}; }}
        QPushButton#primary:hover {{ background: {c["accent_hover"]}; }}
        QPushButton#primary:pressed {{ background: {c["accent_fill"]};
            border-color: {c["accent"]}; }}
        QPushButton#primary:disabled {{ background: {c["raised"]}; color: {c["muted"]}; }}
        QPushButton#nav {{ text-align: left; padding: 4px 12px; border-radius: 6px;
            border-left: 2px solid transparent; background: transparent; color: {c["muted"]}; }}
        QPushButton#nav:checked {{ background: {c["selected"]};
        border-left-color: {c["accent"]};
        color: {c["text"]};
        }}
        QPushButton#nav:hover {{ background: {c["hover"]}; }}
        QPushButton#quiet {{ background: transparent; color: {c["muted"]}; text-align: left; }}
        QPushButton#quiet:hover {{ background: {c["hover"]}; color: {c["text"]}; }}
        QPushButton#disclosure {{ background: transparent; color: {c["muted"]};
            text-align: left; padding: 4px 8px; }}
        QPushButton#disclosure:hover, QPushButton#disclosure:checked {{
            background: {c["raised"]}; color: {c["text"]}; }}
        QLineEdit, QComboBox, QSpinBox, QDateEdit, QTextEdit {{ background: {c["surface"]};
            border: 1px solid {c["border"]}; border-radius: {RADIUS}px; padding: 8px;
            selection-background-color: {c["selected"]}; }}
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
            background: {c["background"]}; color: {c["muted"]}; }}
        QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {c["muted"]}; }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {c["accent"]}; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QSpinBox {{ padding-right: 24px; }}
        QSpinBox::up-button, QSpinBox::down-button {{ width: 24px; border: none;
            background: transparent; }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {c["hover"]}; }}
        QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
            background: {c["selected"]}; }}
        QComboBox QAbstractItemView {{ background: {c["surface"]}; color: {c["text"]};
            selection-background-color: {c["selected"]}; padding: 4px; }}
        QCheckBox {{ spacing: 8px; padding: 4px 0; }}
        QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {c["border"]};
            border-radius: 4px; background: {c["surface"]}; }}
        QCheckBox::indicator:checked {{ background: {c["accent_fill"]};
        border-color: {c["accent"]};
        }}
        QCheckBox:focus {{ color: {c["accent"]}; }}
        QTableView, QListView, QListWidget {{ background: {c["background"]}; border: none;
            outline: none; selection-background-color: {c["selected"]}; }}
        QTableView::item, QListWidget::item {{ padding: 8px; }}
        QHeaderView::section {{ background: {c["background"]}; color: {c["muted"]}; border: none;
            padding: 8px; font-size: {FONT_META}px; }}
        QTabBar::tab {{ padding: 8px 24px; margin-right: 4px; background: {c["surface"]};
            color: {c["muted"]}; border: 1px solid {c["border"]}; border-radius: {RADIUS}px; }}
        QTabBar::tab:selected {{ color: {c["text"]}; background: {c["selected"]};
            border-color: {c["accent"]}; }}
        QTabBar::tab:hover {{ background: {c["raised"]}; }}
        QProgressBar {{ background: {c["raised"]}; border: none; border-radius: 3px;
            min-height: 6px; max-height: 6px; }}
        QProgressBar::chunk {{ background: {c["accent"]}; border-radius: 3px; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {c["border"]};
        border-radius: 4px;
        min-height: 32px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QMenu {{ background: {c["surface"]}; border: 1px solid {c["border"]}; padding: 4px; }}
        QMenu::item {{ padding: 8px 24px; }}
        QMenu::item:selected {{ background: {c["selected"]}; }}
        QToolTip {{ background: {c["raised"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        padding: 8px;
        }}
    """)
    refresh_icons(app)
