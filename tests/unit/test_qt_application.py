import sys
from types import ModuleType, SimpleNamespace

from ui import qt as qt_helpers


class _FakeApplication:
    current = None
    created_with = None
    installed_translators = None

    @classmethod
    def instance(cls):
        return cls.current

    def __init__(self, args):
        type(self).created_with = args
        type(self).installed_translators = []
        type(self).current = self

    def installTranslator(self, translator):
        self.installed_translators.append(translator)
        return True


class _FakeTranslator:
    instances = []

    def __init__(self, _parent):
        self.load_request = None
        self.instances.append(self)

    def load(self, name, path):
        self.load_request = (name, path)
        return True


def test_ensure_application_prefers_sigil_plugin_application(monkeypatch):
    monkeypatch.setattr(qt_helpers, "_application", None)
    monkeypatch.setattr(qt_helpers, "_host_bk", None)
    _FakeApplication.current = None
    _FakeApplication.created_with = None
    _FakeApplication.installed_translators = None
    book = object()
    calls = []
    plugin_utils = ModuleType("plugin_utils")

    def plugin_application(args, **kwargs):
        calls.append((args, kwargs))
        application = object()
        _FakeApplication.current = application
        return application

    plugin_utils.PluginApplication = plugin_application
    monkeypatch.setitem(sys.modules, "plugin_utils", plugin_utils)
    qt_helpers.set_host_book(book)

    application = qt_helpers.ensure_application(
        SimpleNamespace(QApplication=_FakeApplication))
    assert qt_helpers.ensure_application(
        SimpleNamespace(QApplication=_FakeApplication)) is application

    assert calls == [(sys.argv, {"bk": book, "match_dark_palette": True})]
    assert application is qt_helpers._application
    assert _FakeApplication.created_with is None


def test_ensure_application_falls_back_when_plugin_utils_is_unavailable(monkeypatch):
    monkeypatch.setattr(qt_helpers, "_application", None)
    monkeypatch.setattr(qt_helpers, "_host_bk", None)
    _FakeApplication.current = None
    _FakeApplication.created_with = None
    _FakeApplication.installed_translators = None
    monkeypatch.setitem(sys.modules, "plugin_utils", None)
    qt_helpers.set_host_book(object())

    application = qt_helpers.ensure_application(
        SimpleNamespace(QApplication=_FakeApplication))

    assert isinstance(application, _FakeApplication)
    assert _FakeApplication.created_with is sys.argv
    assert qt_helpers._application is application


def test_fallback_application_loads_simplified_chinese_qt_base_translation(monkeypatch):
    monkeypatch.setattr(qt_helpers, "_application", None)
    monkeypatch.setattr(qt_helpers, "_host_bk", None)
    monkeypatch.setattr(qt_helpers, "_qt_base_translators", [])
    _FakeApplication.current = None
    _FakeApplication.created_with = None
    _FakeApplication.installed_translators = None
    _FakeTranslator.instances = []
    monkeypatch.setitem(sys.modules, "plugin_utils", None)

    class LibraryInfo:
        class LibraryPath:
            TranslationsPath = 11

        @staticmethod
        def path(path_id):
            assert path_id == 11
            return "/Sigil/translations"

    qt_widgets = SimpleNamespace(
        QApplication=_FakeApplication,
        QtCore=SimpleNamespace(QLibraryInfo=LibraryInfo, QTranslator=_FakeTranslator),
    )

    application = qt_helpers.ensure_application(qt_widgets, language="zh-Hans")
    assert qt_helpers.ensure_application(qt_widgets, language="zh-Hans") is application

    assert _FakeTranslator.instances[0].load_request == (
        "qtbase_zh_CN", "/Sigil/translations")
    assert application.installed_translators == [_FakeTranslator.instances[0]]


def test_fallback_application_supports_qt5_translation_location_api(monkeypatch):
    monkeypatch.setattr(qt_helpers, "_application", None)
    monkeypatch.setattr(qt_helpers, "_host_bk", None)
    monkeypatch.setattr(qt_helpers, "_qt_base_translators", [])
    _FakeApplication.current = None
    _FakeApplication.created_with = None
    _FakeApplication.installed_translators = None
    _FakeTranslator.instances = []
    monkeypatch.setitem(sys.modules, "plugin_utils", None)

    class LibraryInfo:
        TranslationsPath = 17

        @staticmethod
        def location(path_id):
            assert path_id == 17
            return "/Sigil/Qt5/translations"

    qt_widgets = SimpleNamespace(
        QApplication=_FakeApplication,
        QtCore=SimpleNamespace(QLibraryInfo=LibraryInfo, QTranslator=_FakeTranslator),
    )

    application = qt_helpers.ensure_application(qt_widgets, language="zh-Hant")

    assert _FakeTranslator.instances[0].load_request == (
        "qtbase_zh_TW", "/Sigil/Qt5/translations")
    assert application.installed_translators == [_FakeTranslator.instances[0]]
