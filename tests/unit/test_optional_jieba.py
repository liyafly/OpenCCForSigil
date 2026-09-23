from types import SimpleNamespace
import time
from threading import Event

import pytest

from opencc_backend.backend import OpenCCBackend
from opencc_backend.configs import JIEBA_CONFIGS, SUPPORTED_CONFIGS, V1_CONFIGS
from opencc_backend.errors import BackendConversionError


def backend_with_loader(tmp_path, *, fail_optional=True):
    calls = []

    def constructor(config):
        calls.append(config)
        if config in JIEBA_CONFIGS and fail_optional:
            raise RuntimeError("native library requires a newer operating system")
        return SimpleNamespace(
            convert=lambda text: "汉字" if config == "t2s" else "漢字"
        )

    backend = object.__new__(OpenCCBackend)
    backend._config = "s2t"
    backend._comparisons = {}
    backend._module = SimpleNamespace(OpenCC=constructor, __version__="1.4.2")
    backend._selector = SimpleNamespace(manifest=SimpleNamespace(opencc_version="1.4.2"))
    backend._payload_root = tmp_path
    backend._import_origin = "opencc/__init__.py"
    backend._available_configs = SUPPORTED_CONFIGS
    backend._jieba_plugin = SimpleNamespace(config_names=JIEBA_CONFIGS)
    backend._jieba_checked = False
    backend._jieba_error = None
    backend._jieba_future = None
    backend._jieba_executor = None
    backend._jieba_elapsed_ms = None
    backend._converter = constructor("s2t")
    return backend, calls


def test_standard_preflight_does_not_load_optional_library(tmp_path):
    backend, calls = backend_with_loader(tmp_path)
    result = backend.self_test(include_optional=False)
    assert result.passed
    assert not set(calls) & set(JIEBA_CONFIGS)
    assert backend.convert("汉字") == "漢字"


def test_failed_optional_probe_removes_only_jieba_and_is_cached(tmp_path):
    backend, calls = backend_with_loader(tmp_path)
    assert backend.available_configs() == V1_CONFIGS
    count = len(calls)
    assert backend.available_configs() == V1_CONFIGS
    assert len(calls) == count
    assert "newer operating system" in backend.jieba_error
    assert not backend.jieba_available()
    assert backend.self_test(include_optional=False).passed
    assert not backend.self_test().passed


def test_successful_probe_checks_every_advertised_jieba_config(tmp_path):
    backend, calls = backend_with_loader(tmp_path, fail_optional=False)
    assert backend.available_configs() == SUPPORTED_CONFIGS
    assert set(JIEBA_CONFIGS) <= set(calls)
    assert backend.jieba_error is None
    assert backend.self_test().passed


def test_explicit_selected_jieba_never_silently_falls_back(tmp_path):
    backend, _ = backend_with_loader(tmp_path)
    backend._config = "s2t_jieba"
    backend._converter = SimpleNamespace(
        convert=lambda _text: (_ for _ in ()).throw(RuntimeError("load failed"))
    )
    with pytest.raises(BackendConversionError):
        backend.convert("汉字")
    assert not backend.self_test(include_optional=False).passed


def test_background_probe_keeps_standard_configs_available_without_waiting(tmp_path):
    calls = []
    waited = False

    def constructor(config):
        nonlocal waited
        calls.append(config)
        if config in JIEBA_CONFIGS and not waited:
            waited = True
            time.sleep(0.3)
        return SimpleNamespace(convert=lambda text: text)

    backend, _ = backend_with_loader(tmp_path, fail_optional=False)
    backend._module.OpenCC = constructor
    completed = Event()
    result = []
    backend.start_jieba_probe(on_complete=lambda value: (result.append(value), completed.set()))

    assert backend.jieba_probe_state()[0] == "pending"
    assert backend.available_configs_nonblocking() == V1_CONFIGS
    assert backend._jieba_future is not None
    backend._jieba_future.result(timeout=2)
    state, error, elapsed_ms = backend.jieba_probe_state()
    assert state == "available"
    assert error is None
    assert elapsed_ms >= 250
    assert completed.wait(1)
    assert result[0][0] is True
    assert result[0][2] >= 250
    backend.close()
