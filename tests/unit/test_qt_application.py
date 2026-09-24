import sys
from types import ModuleType, SimpleNamespace

from ui import qt as qt_helpers


class _FakeApplication:
    current = None
    created_with = None

    @classmethod
    def instance(cls):
        return cls.current

    def __init__(self, args):
        type(self).created_with = args
        type(self).current = self


def test_ensure_application_prefers_sigil_plugin_application(monkeypatch):
    monkeypatch.setattr(qt_helpers, "_application", None)
    monkeypatch.setattr(qt_helpers, "_host_bk", None)
    _FakeApplication.current = None
    _FakeApplication.created_with = None
    book = object()
    calls = []
    plugin_utils = ModuleType("plugin_utils")

    def plugin_application(args, **kwargs):
        calls.append((args, kwargs))
        return object()

    plugin_utils.PluginApplication = plugin_application
    monkeypatch.setitem(sys.modules, "plugin_utils", plugin_utils)
    qt_helpers.set_host_book(book)

    application = qt_helpers.ensure_application(
        SimpleNamespace(QApplication=_FakeApplication))

    assert calls == [(sys.argv, {"bk": book, "match_dark_palette": True})]
    assert application is qt_helpers._application
    assert _FakeApplication.created_with is None


def test_ensure_application_falls_back_when_plugin_utils_is_unavailable(monkeypatch):
    monkeypatch.setattr(qt_helpers, "_application", None)
    monkeypatch.setattr(qt_helpers, "_host_bk", None)
    _FakeApplication.current = None
    _FakeApplication.created_with = None
    monkeypatch.setitem(sys.modules, "plugin_utils", None)
    qt_helpers.set_host_book(object())

    application = qt_helpers.ensure_application(
        SimpleNamespace(QApplication=_FakeApplication))

    assert isinstance(application, _FakeApplication)
    assert _FakeApplication.created_with is sys.argv
    assert qt_helpers._application is application
