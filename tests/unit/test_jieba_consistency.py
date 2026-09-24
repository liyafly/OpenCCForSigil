import json

from tools.compare_jieba_outputs import compare_json_files
from tools.differential_jieba_test import write_output_json


def test_identical_platform_json_outputs_match_and_report_first_character_difference(tmp_path):
    linux = tmp_path / "linux.json"
    windows = tmp_path / "windows.json"
    outputs = [{"config": "s2t_jieba", "input": "汉字", "output": "漢字"}]
    for path in (linux, windows):
        path.write_text(json.dumps(outputs, ensure_ascii=False), encoding="utf-8")

    assert compare_json_files({"linux-x86_64": linux, "windows-x86_64": windows}) is None

    changed = [{"config": "s2t_jieba", "input": "汉字", "output": "汉字"}]
    windows.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    assert compare_json_files({"linux-x86_64": linux, "windows-x86_64": windows}) == {
        "reference_platform": "linux-x86_64",
        "platform": "windows-x86_64",
        "config": "s2t_jieba",
        "input": "汉字",
        "reference_output": "漢字",
        "platform_output": "汉字",
    }


def test_differential_jieba_output_json_is_sorted_by_input(tmp_path):
    output = tmp_path / "nested" / "results.json"
    cases = [
        {"id": "second", "config": "s2t_jieba", "source": "z"},
        {"id": "first", "config": "s2t_jieba", "source": "a"},
    ]

    write_output_json(output, cases, ["two", "one"])

    assert json.loads(output.read_text(encoding="utf-8")) == [
        {"config": "s2t_jieba", "input": "a", "output": "one"},
        {"config": "s2t_jieba", "input": "z", "output": "two"},
    ]
