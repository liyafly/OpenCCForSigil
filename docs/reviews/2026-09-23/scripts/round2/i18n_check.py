import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import ast
import json
import re
from pathlib import Path

root = Path("plugin/OpenCCForSigil")
cats = {
    lang: json.loads((root / "resources/i18n" / f"{lang}.json").read_text("utf-8"))
    for lang in ("en", "zh-Hans", "zh-Hant")
}
en = cats["en"]


def ph(s):
    return set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", s))


keyre = re.compile(r"^[a-z][a-z0-9_]*(\.[A-Za-z0-9_\-]+)+$")
missing = []
phbad = []
used = set()
fprefix = []
for path in sorted(root.rglob("*.py")):
    if "vendor" in path.parts:
        continue
    src = path.read_text("utf-8")
    tree = ast.parse(src)
    ns_for_labels = "rules" if path.name == "rules_window.py" else None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("text",)
            and node.args
        ):
            a = node.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                k = a.value
                used.add(k)
                kws = {kw.arg for kw in node.keywords if kw.arg}
                star = any(kw.arg is None for kw in node.keywords)
                if k not in en:
                    missing.append((str(path), node.lineno, k))
                else:
                    need = ph(en[k])
                    if not star and need - kws:
                        phbad.append((str(path), node.lineno, k, sorted(need - kws), sorted(kws)))
            elif isinstance(a, ast.JoinedStr):
                fprefix.append((str(path), node.lineno, ast.unparse(a)))
        if isinstance(node, ast.Subscript) and ns_for_labels:
            base = ast.unparse(node.value)
            if (
                "labels" in base
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                k = f"{ns_for_labels}.{node.slice.value}"
                used.add(k)
                if k not in en:
                    missing.append((str(path), node.lineno, k))
            elif "labels" in base and isinstance(node.slice, ast.JoinedStr):
                fprefix.append((str(path), node.lineno, "labels[" + ast.unparse(node.slice) + "]"))
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and keyre.match(node.value)
        ):
            v = node.value
            top = v.split(".")[0]
            if top in {k.split(".")[0] for k in en} and v not in en:
                missing.append((str(path), node.lineno, "(literal) " + v))
            used.add(v)
print("MISSING KEYS:")
[print(" ", m) for m in missing]
print("PLACEHOLDER kwargs missing:")
[print(" ", m) for m in phbad]
print("F-STRING KEY USES:")
[print(" ", m) for m in fprefix]
unused = sorted(k for k in en if k not in used)
print("catalog keys not referenced literally:", len(unused))
print(unused)
