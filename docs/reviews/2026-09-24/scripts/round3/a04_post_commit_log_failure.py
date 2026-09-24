"""A-04: a logging failure after every file is written makes the run return 2.

Sigil discards all changes on a non-zero return code, so the result must be 0.
Expect after the fix: "return code 0 ... status success".
"""

import tempfile

import common  # noqa: F401
import pytest

import app.controller as controller_module
import plugin
from logging_ext.logger import SessionLogger
from tests.integration.test_error_reporting import Book, _patch_ui

results, errors = [], []
book = Book({"a": "<p>汉字</p>", "b": "<p>简体</p>"})
data_dir = tempfile.mkdtemp()
original_summary = SessionLogger.summary


def failing_summary(self, values):
    if values.get("status") == "success":
        raise OSError("disk full")
    return original_summary(self, values)


with pytest.MonkeyPatch.context() as patch:
    _patch_ui(patch, results=results, errors=errors)
    patch.setattr(SessionLogger, "summary", failing_summary)
    real_controller = controller_module.Controller
    patch.setattr(controller_module, "Controller",
                  lambda bk: real_controller(bk, data_dir=data_dir))
    code = plugin.run(book)

print("return code", code, "writes", book.writes,
      "status", results[-1]["status"] if results else None)
