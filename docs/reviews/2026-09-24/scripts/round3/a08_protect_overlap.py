"""A-08: an earlier overlapping exact rule beats a protect rule (expect: 大乾隆帝)."""

from common import XHTML, run
from rules.models import Rule

rules = [Rule(id="p1", type="protect", direction="*", source="乾隆"),
         Rule(id="e1", type="exact", direction="s2t", source="大乾", target="大幹")]
book, *_ = run(XHTML.format("<p>大乾隆帝</p>"), rules=rules)
print(book.writes[0][1] if book.writes else "no writes")
