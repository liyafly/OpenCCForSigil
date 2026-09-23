import hashlib

import pytest

from tools.build_opencc_jieba import (
    JIEBA_CONFIGS,
    _cmake_generator_options,
    _copy_plugin_payload,
)


def _copy_with_dictionary(tmp_path, dictionary_files):
    payload = tmp_path / "payload"
    install_share = tmp_path / "install" / "share" / "opencc"
    dictionary = install_share / "jieba_dict"
    dictionary.mkdir(parents=True)
    for config in JIEBA_CONFIGS:
        (install_share / f"{config}.json").write_text("{}\n", encoding="utf-8")
    for name, value in dictionary_files.items():
        (dictionary / name).write_bytes(value)
    library = tmp_path / "libopencc-jieba.so"
    library.write_bytes(b"test native library")
    expected = {
        name: hashlib.sha256((dictionary / name).read_bytes()).hexdigest()
        for name in ("jieba_merged.ocd2", "hmm_model.utf8", "idf.utf8", "stop_words.utf8")
        if (dictionary / name).is_file()
    }
    return _copy_plugin_payload(
        payload_root=payload,
        runtime_os="linux",
        plugin_library=library,
        install_root=tmp_path / "install",
        expected_jieba_hashes=expected,
    )


def _valid_dictionary(**overrides):
    values = {
        "jieba_merged.ocd2": b"merged data",
        "hmm_model.utf8": b"model\n",
        "idf.utf8": b"idf\n",
        "stop_words.utf8": b"stop\n",
        "jieba.dict.utf8": b"fallback\n",
    }
    values.update(overrides)
    return values


def test_plugin_copy_rejects_a_missing_merged_dictionary(tmp_path):
    files = _valid_dictionary()
    del files["jieba_merged.ocd2"]

    with pytest.raises(SystemExit, match="official Jieba merged dictionary is missing"):
        _copy_with_dictionary(tmp_path, files)


def test_plugin_copy_rejects_crlf_in_any_text_dictionary(tmp_path):
    with pytest.raises(SystemExit, match="official Jieba resource contains CRLF"):
        _copy_with_dictionary(tmp_path, _valid_dictionary(**{"idf.utf8": b"idf\r\n"}))


def test_windows_uses_ninja_and_other_builds_keep_the_default_generator():
    assert _cmake_generator_options("windows") == ["-G", "Ninja"]
    assert _cmake_generator_options("linux") == []
    assert _cmake_generator_options("macos") == []
