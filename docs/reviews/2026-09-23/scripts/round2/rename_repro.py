import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import tempfile
from pathlib import Path
from types import SimpleNamespace
import fakeqt
from app.settings import RunSettings
from rules.models import Rule
from rules.store import RuleSet, RuleStore
from ui.rules_window import RuleManagerDialog
from ui.i18n import Translator
import ui.rules_window as rw

root = Path(tempfile.mkdtemp())
store = RuleStore(root / "rules")
store.save(RuleSet("A", (Rule(id="r1", source="软件", target="軟體", direction="s2t"),)))
storage = SimpleNamespace(
    paths=SimpleNamespace(root=root, profiles=root / "profiles", rules=root / "rules")
)
settings = RunSettings(
    storage,
    SimpleNamespace(book_fingerprint=lambda: "fp"),
    {"run_options": {"ruleset_ids": ["A"]}},
    language="en",
    session_id="s",
)
settings.bind_run(settings.active, SimpleNamespace(available_configs=lambda: ("s2t",)))


# Drive the real RuleManagerDialog with fake Qt: rename A->B, then create a new set named A with one rule.
def fake_show_rules_window(rules, **kw):
    qt = fakeqt.make()
    answers = iter([("B", True), ("A", True)])
    qt.QInputDialog = SimpleNamespace(getText=lambda *a, **k: next(answers))
    qt.QTableWidget = type(
        "T", (fakeqt.Base,), {"rowCount": lambda s: 0, "currentRow": lambda s: -1}
    )
    qt.QSpinBox = type("Spin", (fakeqt.Base,), {"value": lambda s: 100})
    qt.QTableWidgetItem = lambda v: v
    qt.QListWidgetItem = fakeqt.ListItem
    d = RuleManagerDialog(
        qt,
        tuple(rules),
        translator=Translator("en"),
        config="s2t",
        **{
            k: v
            for k, v in kw.items()
            if k
            in (
                "rulesets",
                "ruleset_id",
                "profile_id",
                "book_fingerprint",
                "available_configs",
                "comparison_configs",
                "storage_errors",
                "official_convert",
            )
        },
    )
    d._rename_ruleset()  # A -> B
    d._new_ruleset()  # new A
    d.rules.append(Rule(id="r2", source="鼠标", target="滑鼠", direction="s2t"))
    d._apply()
    print(
        "dialog result sets:",
        [(s.id, len(s.rules)) for s in d.result.rulesets],
        "renamed:",
        d.result.renamed,
    )
    return d.result


rw.show_rules_window = fake_show_rules_window
qt = SimpleNamespace(
    QMessageBox=SimpleNamespace(Yes=1, No=2, question=lambda *a: 2, information=lambda *a: None)
)
settings.edit_rules("s2t", Translator("en"), qt, None)
print("files on disk:", sorted(p.name for p in (root / "rules").glob("*.json")))
print("active ruleset_ids:", settings.active.ruleset_ids)
