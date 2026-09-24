"""A-06: <m:math> and <svg:svg> are not protected (expect: 数学汉字 / 图形汉字 unchanged)."""

from common import run

source = ('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:m="http://www.w3.org/1998/Math/MathML" '
          'xmlns:svg="http://www.w3.org/2000/svg"><body><m:math><m:mtext>数学汉字</m:mtext></m:math>'
          '<svg:svg><svg:text>图形汉字</svg:text></svg:svg><p>正文</p></body></html>')
book, *_ = run(source)
print(book.writes[0][1] if book.writes else "no writes")
