"""Non-serializing XML syntax checks without loading DTDs or entities."""

import re
from xml.parsers import expat

from document.tokenizer import _find_markup_end


_NAMED_REFERENCE = re.compile(r"&[A-Za-z_:][A-Za-z0-9_.:-]*;")
_VALIDATION_ROOT = "<validation-root>"


class XHTMLSyntaxError(ValueError):
    """An XHTML parse error mapped back to the original source coordinates."""

    def __init__(self, message: str, *, line: int, column: int) -> None:
        self.line = line
        self.column = column
        super().__init__(message)


def validate_xhtml_syntax(source: str) -> None:
    """Check source/fragments, retaining entity spellings in the real document.

    Declarations are excluded from the validation copy; named references are
    represented by a harmless character there. No DTD lookup or entity
    expansion is performed. Numeric references still receive XML validation.
    Wrapping permits the fragment fixtures and Sigil text API fragments.
    """
    fragments = []
    cursor = 0
    while cursor < len(source):
        start = source.find("<", cursor)
        if start < 0:
            fragments.append(source[cursor:])
            break
        fragments.append(source[cursor:start])
        if source.startswith("<!--", start):
            close = source.find("-->", start + 4)
            end = len(source) if close < 0 else close + 3
        elif source.startswith("<![CDATA[", start):
            close = source.find("]]>", start + 9)
            end = len(source) if close < 0 else close + 3
        else:
            end = _find_markup_end(source, start + 1, bracket_aware=True)
        markup = source[start:end]
        if (re.match(r"<!DOCTYPE\s", markup, re.IGNORECASE) or
                re.match(r"<\?xml\s", markup)):
            fragments.append(_preserve_line_columns(markup))
        else:
            fragments.append(markup)
        cursor = max(start + 1, end)
    validation_copy = _NAMED_REFERENCE.sub(_preserve_named_reference, "".join(fragments))
    parser = expat.ParserCreate(namespace_separator="|")
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.ExternalEntityRefHandler = lambda *_args: 0
    try:
        parser.Parse(_VALIDATION_ROOT + validation_copy + "</validation-root>", True)
    except expat.ExpatError as exc:
        line = max(int(exc.lineno), 1)
        column = max(int(exc.offset) - (len(_VALIDATION_ROOT) if line == 1 else 0), 0)
        detail = str(exc).split(": line ", 1)[0]
        message = f"invalid XHTML syntax: {detail}: line {line}, column {column}"
        raise XHTMLSyntaxError(message, line=line, column=column) from exc


def _preserve_line_columns(declaration: str) -> str:
    """Blank a removed declaration without shifting later source positions."""

    return "".join(character if character in "\r\n" else " " for character in declaration)


def _preserve_named_reference(match: re.Match[str]) -> str:
    """Replace a named entity with harmless text of the same source width."""

    value = match.group()
    return "x" + " " * (len(value) - 1)
