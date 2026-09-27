"""Read-only synthetic probes for the 2026-09-27 follow-up plan.

Print measurements, not a pass/fail claim. No real book or user settings are opened.
"""

import argparse
import json
from pathlib import Path
import platform
import sys
from statistics import median
from time import perf_counter
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "plugin/OpenCCForSigil")]

from app.profiles import Profile  # noqa: E402
from app.settings import tokenizer_policy  # noqa: E402
from core.models import ConversionPlan, SourceSpan, TokenChange  # noqa: E402
from core.preview import PreviewSession  # noqa: E402
from document.tokenizer import tokenize_xhtml  # noqa: E402
from tests.support.fake_qt import make_with_table  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.preview_window import _PreviewDialog  # noqa: E402


def change(index, group, *, language=False):
    return TokenChange(
        source="zh-CN" if language else "软件",
        target="zh-TW" if language else "軟體",
        span=SourceSpan(index * 8, index * 8 + (5 if language else 2)),
        rule_source="language_metadata" if language else "UserRule:example",
        change_id=f"change-{index}", file_id="chapter", group_id=group,
        category="language_metadata" if language else "user_rule", risk="HIGH",
    )


def dialog_for(changes):
    plan = ConversionPlan(source_sha256="", file_id="chapter", changes=tuple(changes))
    preview = PreviewSession(plan)
    planned = (SimpleNamespace(
        source=SimpleNamespace(file_id="chapter", href="Text/chapter.xhtml",
                               document_kind="xhtml"), plan=plan),)
    dialog = _PreviewDialog(make_with_table(), planned, (preview,), Translator("en"))
    dialog._set_current_row(0)
    return dialog, preview


class CountedEntries:
    def __init__(self, entries):
        self.entries = entries
        self.visits = 0

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, index):
        return self.entries[index]

    def __iter__(self):
        for entry in self.entries:
            self.visits += 1
            yield entry


def probe_group_semantics():
    dialog, preview = dialog_for((
        change(0, "rules:occurrence-1"), change(1, "rules:occurrence-1"),
    ))
    language_button_visible = dialog.accept_group_button.isVisible()
    dialog.accept_group_button.click()
    after_hidden_language_button = {
        item.change_id: preview.decision(item.change_id)
        for item in preview.changes
    }
    dialog._accept_file()
    after_file = {
        item.change_id: preview.decision(item.change_id)
        for item in preview.changes
    }
    mixed, mixed_preview = dialog_for((
        change(0, "language_metadata", language=True), change(1, "rules:occurrence-2"),
    ))
    mixed.accept_group_button.click()
    mixed_decisions = {
        item.change_id: mixed_preview.decision(item.change_id)
        for item in mixed_preview.changes
    }
    passed = (
        not language_button_visible
        and all(value is None for value in after_hidden_language_button.values())
        and all(value is not None and value.value == "accept_this"
                for value in after_file.values())
        and mixed_decisions["change-0"] is not None
        and mixed_decisions["change-0"].value == "accept_this"
        and mixed_decisions["change-1"] is None
    )
    assert passed, "preview group actions do not match the frozen R-01 semantics"
    return {
        "rule_only_language_button_visible": language_button_visible,
        "rule_only_after_hidden_language_button": {
            key: value.value if value else None
            for key, value in after_hidden_language_button.items()
        },
        "rule_only_after_accept_file": {
            key: value.value if value else None for key, value in after_file.items()
        },
        "mixed_language_button_decisions": {
            key: value.value if value else None
            for key, value in mixed_decisions.items()
        },
        "assertions_passed": passed,
    }


def probe_group_scans(groups):
    runs = []
    for _attempt in range(3):
        dialog, preview = dialog_for(
            change(index, f"rules:occurrence-{index // 2}")
            for index in range(groups * 2))
        counted = CountedEntries(dialog._entries)
        dialog._entries = counted
        # Isolate the decision operation; exclude table refresh/recount from this measurement.
        dialog._refresh = lambda **_kwargs: None
        started = perf_counter()
        dialog._decide_filtered(True)
        elapsed = perf_counter() - started
        assert preview.summary()["accepted"] == groups * 2
        assert counted.visits <= 10 * groups * 2, (
            f"bulk group decision scanned {counted.visits} entries for "
            f"{groups * 2} changes (budget: {10 * groups * 2})")
        runs.append({"entry_visits": counted.visits, "decision_seconds": elapsed})
    return {
        "groups": groups, "changes": groups * 2,
        "entry_visit_budget": groups * 2 * 10,
        "entry_visits": int(median(run["entry_visits"] for run in runs)),
        "decision_seconds_median": median(run["decision_seconds"] for run in runs),
        "runs": runs,
    }


def probe_mathml():
    source = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        '<math xmlns="http://www.w3.org/1998/Math/MathML">'
        '<mi>变量</mi><mtext>说明</mtext><annotation encoding="text/plain">备注</annotation>'
        '</math></body></html>'
    )
    payload = Profile(name="synthetic-mathml").to_dict()
    result = {}
    for enabled in (False, True):
        payload["mathml"] = enabled
        profile = Profile.from_dict(payload)
        result[str(enabled).lower()] = [
            {"tag": target.tag_name, "text": target.source_text, "convert": target.convert}
            for target in tokenize_xhtml(source, tokenizer_policy(profile)).targets
        ]
    assert result["false"] == []
    assert [item["tag"] for item in result["true"]] == ["mtext"]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = {
        "python": platform.python_version(), "platform": platform.platform(),
        "group_semantics": probe_group_semantics(),
        "group_scans": [probe_group_scans(size) for size in (1_000, 2_000, 4_000)],
        "mathml_targets": probe_mathml(),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
