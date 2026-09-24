from __future__ import annotations

from app.controller import Controller
from app.version import PLUGIN_VERSION
from opencc_backend.errors import RuntimeSelectionError


class _Book:
    sigil_ui_lang = "zh-Hans"

    def __init__(self) -> None:
        self.read_calls = 0

    def readfile(self, _file_id: str) -> bytes:
        self.read_calls += 1
        return b""


def test_runtime_selection_error_shows_one_localized_dialog_without_reading_book(
    monkeypatch, tmp_path
):
    error = RuntimeSelectionError(
        "No OpenCC payload in this package matches CPython 3.14 cp314 macos/x86_64.",
        detected={
            "implementation": "CPython",
            "python_version": "3.14",
            "abi": "cp314",
            "os": "macos",
            "architecture": "x86_64",
        },
        package_flavor="platform",
        package_runtimes=("macos-arm64-cp314",),
        reason="no_payload_in_package",
    )
    calls = []

    def fail_runtime_selection(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr("app.controller.OpenCCBackend", fail_runtime_selection)
    monkeypatch.setattr(
        "app.controller._show_error_safely",
        lambda _logger, **values: calls.append(values),
    )
    book = _Book()

    result = Controller(book, data_dir=tmp_path / "plugin-data").run()

    assert result == 2
    assert len(calls) == 1
    assert book.read_calls == 0
    assert f"OpenCCForSigil_{PLUGIN_VERSION}_macos-x86_64.zip" in calls[0]["summary"]
    assert "转换已停止" not in calls[0]["summary"]
    assert "此安装包适用于" in calls[0]["summary"]


def test_runtime_selection_uses_host_language_when_ui_preferences_are_corrupt(
    monkeypatch, tmp_path
):
    error = RuntimeSelectionError(
        "No OpenCC payload in this package matches CPython 3.14 cp314 macos/x86_64.",
        detected={
            "implementation": "CPython",
            "python_version": "3.14",
            "abi": "cp314",
            "os": "macos",
            "architecture": "x86_64",
        },
        package_flavor="platform",
        package_runtimes=("macos-arm64-cp314",),
        reason="no_payload_in_package",
    )
    calls = []

    def fail_runtime_selection(*_args: object, **_kwargs: object) -> None:
        raise error

    def corrupt_preferences(_store: object, default=None) -> dict:
        return {"last_conversion_config": "s2t", "ui": "corrupt"}

    monkeypatch.setattr("app.controller.OpenCCBackend", fail_runtime_selection)
    monkeypatch.setattr("app.controller.UserDataStore.load_preferences", corrupt_preferences)
    monkeypatch.setattr(
        "app.controller._show_error_safely",
        lambda _logger, **values: calls.append(values),
    )
    book = _Book()

    result = Controller(book, data_dir=tmp_path / "plugin-data").run()

    assert result == 2
    assert len(calls) == 1
    assert book.read_calls == 0
    assert "此安装包适用于" in calls[0]["summary"]
