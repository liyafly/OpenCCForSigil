import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import ast
import re
from pathlib import Path

root = Path("plugin/OpenCCForSigil")
NAMES = {
    "QLabel",
    "QPushButton",
    "QCheckBox",
    "setText",
    "setWindowTitle",
    "setToolTip",
    "addItem",
    "warning",
    "information",
    "critical",
    "question",
    "setPlaceholderText",
    "QGroupBox",
    "addButton",
    "setHorizontalHeaderLabels",
    "QRadioButton",
    "QAction",
    "addAction",
    "addMenu",
    "setPlainText",
    "QToolButton",
    "setDetailedText",
    "setInformativeText",
    "getItem",
    "getText",
    "QMenu",
    "setTitle",
    "insertRow",
    "QTableWidgetItem",
    "QListWidgetItem",
    "setStatusTip",
    "showMessage",
    "getOpenFileName",
    "getSaveFileName",
    "addRow",
}


def has_letters(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return bool(re.search(r"[A-Za-z一-鿿]{2,}", node.value)), node.value
    if isinstance(node, ast.JoinedStr):
        lits = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
        return bool(re.search(r"[A-Za-z一-鿿]{2,}", lits)), ast.unparse(node)
    if isinstance(node, ast.BinOp):
        a = has_letters(node.left)
        b = has_letters(node.right)
        return a[0] or b[0], ast.unparse(node)
    return False, None


for path in sorted((root / "ui").glob("*.py")) + [
    root / "app/settings.py",
    root / "app/controller.py",
    root / "plugin.py",
]:
    tree = ast.parse(path.read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = (
                f.attr
                if isinstance(f, ast.Attribute)
                else f.id
                if isinstance(f, ast.Name)
                else None
            )
            if name in NAMES:
                for a in node.args:
                    ok, s = has_letters(a)
                    if ok:
                        print(f"{path}:{node.lineno}: {name}({s!r})")
        if isinstance(node, ast.Raise) and node.exc is not None and isinstance(node.exc, ast.Call):
            for a in node.exc.args:
                ok, s = has_letters(a)
                if ok and "ui/" in str(path):
                    print(f"{path}:{node.lineno}: raise {ast.unparse(node.exc.func)}({s!r})")
