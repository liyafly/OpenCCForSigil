import time
from threading import Event, Thread
from types import SimpleNamespace

from app.controller import Controller
from opencc_backend.backend import JiebaProbe, SelfTestResult
from opencc_backend.configs import JIEBA_CONFIGS, V1_CONFIGS
from sigil.scope import Scope, TargetSelection
from ui.preview_window import ConfigOutcome, PreviewOutcome, ScopeOutcome
from ui.run_options import ConfigurationChoice


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

    def choose_config(_configs, *, default_config, jieba_probe, **_kwargs):
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


def test_probe_survives_settings_loop_and_preserves_jieba_choice(monkeypatch, tmp_path):
    class MutableBook:
        def __init__(self):
            self.writes = []

        def text_iter(self):
            yield "a", "Text/a.xhtml"

        def readfile(self, _file_id):
            return "<p>汉字</p>"

        def writefile(self, file_id, _value):
            self.writes.append(file_id)

    class NoProgress:
        def update(self, *_args):
            pass

        def cancelled(self):
            return False

        def close(self):
            pass

    probe_runs = []
    original_probe = JiebaProbe._probe_payload

    def count_probe(probe):
        probe_runs.append(probe)
        return original_probe(probe)

    monkeypatch.setattr(JiebaProbe, "_probe_payload", count_probe)
    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda _adapter, initial_language, **_kwargs: ScopeOutcome(
            True, TargetSelection(Scope.SINGLE, ("a",)), initial_language
        ),
    )
    config_calls = []

    def choose_config(available, *, default_config, jieba_probe, **_kwargs):
        config_calls.append((tuple(available), default_config, jieba_probe))
        if len(config_calls) == 1:
            deadline = time.monotonic() + 30
            while jieba_probe.jieba_probe_state()[0] == "pending":
                if time.monotonic() >= deadline:
                    raise AssertionError("native Jieba probe did not finish")
                time.sleep(0.01)
            assert jieba_probe.jieba_probe_state()[0] == "available"
            assert set(JIEBA_CONFIGS) <= set(jieba_probe.available_configs_nonblocking())
            return ConfigOutcome(
                "continue", ConfigurationChoice("s2t_jieba", {})
            )
        assert jieba_probe is config_calls[0][2]
        assert default_config == "s2t_jieba"
        assert set(JIEBA_CONFIGS) <= set(available)
        assert jieba_probe.jieba_probe_state()[0] == "available"
        return ConfigOutcome("cancel")

    monkeypatch.setattr("ui.preview_window.choose_conversion_config", choose_config)
    monkeypatch.setattr(
        "ui.preview_window.show_preview",
        lambda *_args, **_kwargs: PreviewOutcome(False, (), back_to_settings=True),
    )
    monkeypatch.setattr("ui.preview_window.create_progress_reporter", lambda *_a, **_kw: NoProgress())

    book = MutableBook()
    assert Controller(book, data_dir=tmp_path).run() == 1

    assert len(config_calls) == 2
    assert config_calls[1][1] == "s2t_jieba"
    assert len(probe_runs) == 1
    assert book.writes == []


def test_cancel_before_text_ui_does_not_wait_for_daemon_probe(monkeypatch, tmp_path):
    started = Event()
    finished = Event()

    class SlowProbeBackend:
        config = "s2t"

        def __init__(self, _config):
            pass

        def self_test(self, *, include_optional):
            assert include_optional is False
            return SelfTestResult(True, {})

        def provenance(self):
            return SimpleNamespace(as_dict=lambda: {"test": True})

        def start_jieba_probe(self, on_complete=None):
            def wait():
                started.set()
                time.sleep(2)
                finished.set()

            Thread(target=wait, daemon=True).start()

        def close(self):
            pass

    monkeypatch.setattr("app.controller.OpenCCBackend", SlowProbeBackend)
    begin = time.perf_counter()

    assert Controller(object(), data_dir=tmp_path).run() == 0

    elapsed = time.perf_counter() - begin
    assert started.is_set()
    assert elapsed < 0.5
    assert not finished.is_set()
