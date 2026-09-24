"""A-01: U+0130 before <style> hangs the tokenizer (expect: returns in < 1 s)."""

import time

import common  # noqa: F401
import faulthandler

from document.tokenizer import tokenize_xhtml

faulthandler.dump_traceback_later(5, exit=True)
source = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>İstanbul 游记</title>'
          '<style>p{}</style></head><body><p>汉字</p></body></html>')
start = time.perf_counter()
targets = tokenize_xhtml(source).targets
print(f"OK: {len(targets)} targets in {time.perf_counter() - start:.3f} s")
