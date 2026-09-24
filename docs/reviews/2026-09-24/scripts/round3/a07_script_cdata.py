"""A-07: '</script>' inside CDATA ends raw-text mode (expect: script unchanged, 正文 -> 正文)."""

from common import run

source = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><script type="text/javascript">'
          '<![CDATA[ var tpl = "<p>x</p></script>"; var msg = "汉字软件"; ]]></script></head>'
          '<body><p>汉字</p></body></html>')
book, *_ = run(source)
print(book.writes[0][1])
