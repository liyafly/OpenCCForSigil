from types import SimpleNamespace

from app.controller import Controller
from opencc_backend.backend import SelfTestResult
from opencc_backend.configs import V1_CONFIGS
from sigil.scope import Scope, TargetSelection
from ui.preview_window import ScopeOutcome


class Book:
    def text_iter(self):
        yield "a", "Text/a.xhtml"

    def readfile(self, _file_id):
        return "<p>汉字</p>"

    def writefile(self, *_args):
        raise AssertionError("configuration cancellation must not write")


def test_controller_starts_optional_probe_before_scope_and_opens_settings_pending(
    monkeypatch, tmp_path
):
    events = []

    class Backend:
        config = "s2t"
        jieba_error = None

        def __init__(self, _config):
            pass

        def self_test(self, *, include_optional):
            assert include_optional is False
            return SelfTestResult(True, {})

        def provenance(self):
            return SimpleNamespace(as_dict=lambda: {"test": True})

        def start_jieba_probe(self, on_complete=None):
            events.append("probe-start")

        def jieba_probe_state(self):
            return "pending", None, None

        def available_configs_nonblocking(self):
            return V1_CONFIGS

        def close(self):
            pass

    def choose_scope(adapter, initial_language, **_kwargs):
        events.append("scope")
        return ScopeOutcome(True, TargetSelection(Scope.SINGLE, ("a",)), initial_language)

    def choose_config(_configs, *, default_config, jieba_probe):
        assert events[:2] == ["probe-start", "scope"]
        assert default_config == "s2t"
        assert jieba_probe.jieba_probe_state()[0] == "pending"
        events.append("settings-pending")
        return None

    monkeypatch.setattr("app.controller.OpenCCBackend", Backend)
    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr("ui.preview_window.choose_conversion_config", choose_config)

    assert Controller(Book(), data_dir=tmp_path).run() == 1
    assert events == ["probe-start", "scope", "settings-pending"]
