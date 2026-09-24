"""A-03: entity scan is O(entities x tags), even when quotation_mode="keep".

Expect after the fix: 16000 paragraphs plan in well under 3 s.
"""

import time

from common import XHTML, backend, request
from core.planner import build_conversion_plan
from document.tokenizer import tokenize_xhtml

for count in (4000, 8000, 16000):
    source = XHTML.format("".join(f"<p>&#12288;&#12288;第{i}段正文说明。</p>" for i in range(count)))
    document = tokenize_xhtml(source)
    start = time.perf_counter()
    build_conversion_plan(file_id="a", source=source, document=document,
                          backend=backend("s2t"), request=request("s2t"))
    print(f"{count:6d} paragraphs {len(source) / 1024:5.0f} KiB  plan {time.perf_counter() - start:5.1f} s")
