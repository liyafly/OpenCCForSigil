import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)

from document.validation import validate_xhtml_syntax

srcs = {
    "multiline doctype, error on line 5 col 10": '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"\n  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n<html><body>\n<p>汉字<br></p>\n</body></html>',
    "line 1 error at col 7 (0-based)": "<p>汉字<br></p>",
}
for k, s in srcs.items():
    try:
        validate_xhtml_syntax(s)
    except ValueError as e:
        print(k, "=>", e)
