"""Read-only synthetic probes for the 2026-09-27 follow-up plan.

Print measurements, not a pass/fail claim. No real book or user settings are opened.
"""

import argparse
import json
from pathlib import Path
import platform
import sys
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
    dialog, preview = dialog_for((change(0, "rules:occurrence-1"),))
    label = dialog.accept_group_button.text()
    dialog._accept_file()
    after_file = preview.decision("change-0")
    dialog.accept_group_button.click()
    after_language_button = preview.decision("change-0")
    mixed, mixed_preview = dialog_for((
        change(0, "language_metadata", language=True), change(1, "rules:occurrence-2"),
    ))
    mixed.accept_group_button.click()
    return {
        "rule_only_group_button_label": label,
        "rule_only_after_accept_file": after_file.value if after_file else None,
        "rule_only_after_language_button": (
            after_language_button.value if after_language_button else None),
        "mixed_language_button_decisions": {
            item.change_id: (mixed_preview.decision(item.change_id).value
                             if mixed_preview.decision(item.change_id) else None)
            for item in mixed_preview.changes
        },
    }


def probe_group_scans(groups):
    dialog, preview = dialog_for(
        change(index, f"rules:occurrence-{index // 2}") for index in range(groups * 2))
    counted = CountedEntries(dialog._entries)
    dialog._entries = counted
    # Isolate the decision operation; exclude table refresh/recount from this measurement.
    dialog._refresh = lambda **_kwargs: None
    started = perf_counter()
    dialog._decide_filtered(True)
    elapsed = perf_counter() - started
    assert preview.summary()["accepted"] == groups * 2
    return {"groups": groups, "changes": groups * 2,
            "entry_visits": counted.visits, "decision_seconds": elapsed}


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
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = {
        "python": platform.python_version(), "platform": platform.platform(),
        "group_semantics": probe_group_semantics(),
        "group_scans": [probe_group_scans(size) for size in (100, 200, 400)],
        "mathml_targets": probe_mathml(),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
