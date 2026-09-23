import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import ast
from pathlib import Path

for path in sorted(Path("plugin/OpenCCForSigil/ui").glob("*.py")) + [
    Path("plugin/OpenCCForSigil/app/settings.py"),
    Path("plugin/OpenCCForSigil/app/controller.py"),
]:
    tree = ast.parse(path.read_text("utf-8"))
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        defined = {
            n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assigned = set()
        for n in ast.walk(cls):
            if (
                isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name)
                and n.value.id in ("self", "_self")
                and isinstance(n.ctx, ast.Store)
            ):
                assigned.add(n.attr)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "setattr":
                assigned.add("<dynamic>")
        for n in ast.walk(cls):
            if (
                isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name)
                and n.value.id == "self"
                and isinstance(n.ctx, ast.Load)
            ):
                if n.attr not in defined and n.attr not in assigned and not n.attr.startswith("__"):
                    # base-class methods for Qt subclasses are fine
                    if cls.bases and ast.unparse(cls.bases[0]) not in ("object",):
                        continue
                    print(f"{path}:{n.lineno}: {cls.name}.self.{n.attr} not defined/assigned")
