import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)

from opencc_backend.backend import OpenCCBackend
from core.converter import OfficialBackendConverter
from core.models import ConvertRequest
from core.diagnostics import diagnose_mixed_script

b = OpenCCBackend("s2t")
for text in ("裡面", "著作", "乾淨", "於是", "麪條", "綫索", "衆人", "台灣", "嘆息"):
    s = b.convert_for_config("s2t", text)
    t = b.convert_for_config("t2s", text)
    piv = b.convert_for_config("s2t", t)
    print(text, "s2t:", s, "t2s:", t, "pivot:", piv)
text = "裡面"
req_plain = ConvertRequest("s2t", detailed_classification=False)
req_pivot = ConvertRequest("s2t", pivot_chain=("t2s", "s2t"), detailed_classification=False)
conv = OfficialBackendConverter(b)
print("plain diagnostics:", [d.code for d in conv.convert(text, req_plain).diagnostics])
print("pivot diagnostics:", [d.code for d in conv.convert(text, req_pivot).diagnostics])
print("true diagnosis:", diagnose_mixed_script(text, b.convert_for_config).status)
