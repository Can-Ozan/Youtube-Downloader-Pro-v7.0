"""Translate Qt's standard controls alongside the application's own catalogs."""

from PySide6.QtCore import QLibraryInfo, QLocale, QObject, QTranslator, Signal, Slot
from PySide6.QtWidgets import QApplication, QToolTip

from youtube_downloader_pro.i18n import set_language, tr


class LanguageEvents(QObject):
    languageChanged = Signal(str)


def language_events() -> LanguageEvents:
    app = QApplication.instance()
    if not hasattr(app, "_language_events"):
        app._language_events = LanguageEvents(app)
    return app._language_events


class TranslationBinding(QObject):
    def __init__(self, owner, callback):
        super().__init__(owner)
        self.callback = callback
        language_events().languageChanged.connect(self.refresh)

    @Slot(str)
    def refresh(self, _language):
        self.callback()


def watch_language(owner, callback):
    # QObject ownership disconnects bindings when dialogs or menus are destroyed.
    return TranslationBinding(owner, callback)


def bind_text(owner, setter, key, **values):
    def refresh():
        getattr(owner, setter)(tr(key, **values))

    binding = watch_language(owner, refresh)
    refresh()
    return binding


def install_qt_language(app, code: str) -> None:
    code = code if code in {"en", "tr"} else "en"
    if getattr(app, "_ui_language", None) == code:
        set_language(code)
        return
    translator = QTranslator(app)
    if code == "tr":
        directory = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if not translator.load("qtbase_tr", directory):
            translator.deleteLater()
            raise RuntimeError("Qt Turkish translations are missing")
    previous = getattr(app, "_language_translator", None)
    set_language(code)
    if previous is not None:
        app.removeTranslator(previous)
        previous.deleteLater()
    if code == "tr":
        app.installTranslator(translator)
    app._language_translator = translator
    QLocale.setDefault(QLocale("tr_TR" if code == "tr" else "en_US"))

    app._ui_language = code
    QToolTip.hideText()
    language_events().languageChanged.emit(code)
