"""Capture real-Qt preview screens showing aligned undecided terminology."""

import argparse
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from ui.i18n import Translator
from ui.preview_window import _PreviewDialog
from ui.qt import ensure_application, load_qt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    qt = load_qt()
    app = ensure_application(qt)
    results = []
    for language in ("en", "zh-Hans", "zh-Hant"):
        translator = Translator(language)
        change = TokenChange(
            source="软件", target="軟體", span=SourceSpan(0, 2),
            rule_source="UserRule:example", change_id="change-0", file_id="chapter",
            category="user_rule", risk="HIGH",
        )
        plan = ConversionPlan(source_sha256="", file_id="chapter", changes=(change,))
        planned = (SimpleNamespace(
            source=SimpleNamespace(file_id="chapter", href="chapter.xhtml",
                                   document_kind="xhtml"),
            plan=plan,
        ),)
        dialog = _PreviewDialog(
            qt, planned, (PreviewSession(plan),), translator)
        dialog.dialog.resize(args.width, args.height)
        dialog.dialog.show()
        app.processEvents()

        filter_index = dialog.status_filter.findData("undecided")
        assert filter_index >= 0
        filter_text = dialog.status_filter.itemText(filter_index)
        expected = translator.text("preview.status.pending")
        dialog.status_filter.setCurrentIndex(filter_index)
        app.processEvents()
        model = dialog.table_view.model()
        table_status = model.data(model.index(0, 0), qt.Qt.DisplayRole)
        next_label = dialog.next_undecided_button.text()

        assert filter_text == translator.text("preview.filter_status.undecided")
        assert filter_text == expected
        assert table_status == expected
        assert expected.casefold() in next_label.casefold()
        image_path = args.output / f"preview-undecided-filter-{language}.png"
        assert dialog.dialog.grab().save(str(image_path))
        results.append({
            "language": language,
            "status_filter_item": filter_text,
            "status_column": table_status,
            "next_button": next_label,
            "screenshot": image_path.name,
        })
        dialog.dialog.hide()

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    report = {"head": head, "results": results, "status": "PASS"}
    (args.output / "terms.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
