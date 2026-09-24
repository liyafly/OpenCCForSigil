"""A-11: text inside lang="ja" is converted (expect: 国会図書館の桜 unchanged)."""

from common import XHTML, run

book, *_ = run(XHTML.format('<p>他说：<span lang="ja" xml:lang="ja">国会図書館の桜</span></p>'))
print(book.writes[0][1])
