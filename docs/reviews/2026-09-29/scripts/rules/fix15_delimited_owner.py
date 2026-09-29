# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-15: TSV/CSV/TXT import fills both owner fields regardless of scope.

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

import sys
from rules.importers import import_rules
for fmt, payload in (("tsv", "软件\t軟體\n"), ("csv", "direction,source,target\ns2t,软件,軟體\n"), ("txt", "软件\t軟體\n")):
    r = import_rules(payload, format=fmt, direction="s2t", scope="global",
                     profile_id="CURRENT-PROFILE", book_fingerprint="CURRENT-BOOK").rules[0]
    print(fmt, "scope=global ->", "profile_id=%r book_fingerprint=%r" % (r.profile_id, r.book_fingerprint))
    r = import_rules(payload, format=fmt, direction="s2t", scope="book",
                     profile_id="CURRENT-PROFILE", book_fingerprint="CURRENT-BOOK").rules[0]
    print(fmt, "scope=book   ->", "profile_id=%r book_fingerprint=%r" % (r.profile_id, r.book_fingerprint))
