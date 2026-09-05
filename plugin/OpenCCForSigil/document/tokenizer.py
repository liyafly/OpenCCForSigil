"""Offset-preserving lexical tokenizer for XHTML source strings.

This is deliberately a lexer, not a regular-expression parser and not a
serializer. It scans tag boundaries with quote awareness, keeps absolute
source offsets, and exposes only text/attribute spans allowed by the profile.
The original source is always available for patch application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

from core.models import TextTarget


DEFAULT_PROTECTED_ELEMENTS = ("script", "style", "code", "pre")
DEFAULT_PROTECTED_ATTRIBUTES = ("id", "href", "src", "class", "style")
VOID_ELEMENTS = (
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
)


@dataclass(frozen=True)
class TokenizerOptions:
    """Profile-controlled lexical target policy."""

    protected_elements: Tuple[str, ...] = DEFAULT_PROTECTED_ELEMENTS
    convert_attributes: Tuple[str, ...] = ("alt", "title")
    protected_attributes: Tuple[str, ...] = DEFAULT_PROTECTED_ATTRIBUTES
    svg_text: bool = False
    mathml: bool = False
    document_kind: str = "xhtml"
    context_radius: int = 32

    def normalized(self) -> "TokenizerOptions":
        return TokenizerOptions(
            protected_elements=tuple(name.lower() for name in self.protected_elements),
            convert_attributes=tuple(name.lower() for name in self.convert_attributes),
            protected_attributes=tuple(name.lower() for name in self.protected_attributes),
            svg_text=self.svg_text,
            mathml=self.mathml,
            document_kind=self.document_kind,
            context_radius=max(0, self.context_radius),
        )


@dataclass(frozen=True)
class AttributeSpan:
    name: str
    value_start: int
    value_end: int
    quote: Optional[str]


@dataclass(frozen=True)
class LexicalTag:
    start: int
    end: int
    name: str
    closing: bool
    self_closing: bool
    attributes: Tuple[AttributeSpan, ...] = ()


@dataclass(frozen=True)
class TokenizedDocument:
    source: str
    targets: Tuple[TextTarget, ...]
    tags: Tuple[LexicalTag, ...]

    @property
    def structural_signature(self) -> Tuple[Tuple[object, ...], ...]:
        """Return tag structure while ignoring planned attribute values."""

        return tuple(
            (
                tag.name,
                tag.closing,
                tag.self_closing,
                tuple((attribute.name, attribute.quote) for attribute in tag.attributes),
            )
            for tag in self.tags
        )

    def protected_attribute_signature(
        self,
        names: Iterable[str] = DEFAULT_PROTECTED_ATTRIBUTES,
    ) -> Tuple[Tuple[object, ...], ...]:
        protected = {name.lower() for name in names}
        values = []
        for tag_index, tag in enumerate(self.tags):
            for attribute in tag.attributes:
                if attribute.name in protected:
                    values.append(
                        (
                            tag_index,
                            tag.name,
                            attribute.name,
                            self.source[attribute.value_start : attribute.value_end],
                        )
                    )
        return tuple(values)


def tokenize_xhtml(source: str, options: Optional[TokenizerOptions] = None) -> TokenizedDocument:
    """Tokenize *source* into safe text and explicitly allowed attributes."""

    if not isinstance(source, str):
        raise TypeError("XHTML source must be text")
    policy = (options or TokenizerOptions()).normalized()
    targets = []
    tags = []
    stack = []
    target_ordinal = 0
    cursor = 0

    while cursor < len(source):
        raw_name = _raw_protected_name(stack, policy)
        if raw_name is not None and not _is_closing_tag_at(source, cursor, raw_name):
            closing_start = _find_closing_tag(source, cursor, raw_name)
            if closing_start < 0:
                break
            cursor = closing_start
            continue

        if source[cursor] != "<":
            text_end = source.find("<", cursor)
            if text_end < 0:
                text_end = len(source)
            if not _is_protected(stack, policy):
                for start, end in _split_entity_boundaries(source, cursor, text_end):
                    if start == end:
                        continue
                    target_ordinal += 1
                    targets.append(
                        _make_target(
                            source,
                            start,
                            end,
                            target_ordinal,
                            policy,
                            tag_name=stack[-1] if stack else None,
                        )
                    )
            cursor = text_end
            continue

        if not _looks_like_markup(source, cursor):
            cursor += 1
            continue
        if source.startswith("<!--", cursor):
            cursor = _find_or_end(source, "-->", cursor + 4)
            continue
        if source.startswith("<![CDATA[", cursor):
            cursor = _find_or_end(source, "]]>", cursor + 9)
            continue
        if source.startswith("<?", cursor):
            cursor = _find_markup_end(source, cursor + 2)
            continue
        if source.startswith("<!", cursor):
            cursor = _find_markup_end(source, cursor + 2, bracket_aware=True)
            continue

        tag_end = _find_markup_end(source, cursor + 1)
        tag = _parse_tag(source, cursor, tag_end)
        if tag is None:
            cursor = max(cursor + 1, tag_end)
            continue
        tags.append(tag)

        if not tag.closing:
            if _element_is_writable(tag.name, stack, policy):
                for attribute in tag.attributes:
                    if attribute.name in policy.convert_attributes:
                        target_ordinal += 1
                        targets.append(
                            _make_target(
                                source,
                                attribute.value_start,
                                attribute.value_end,
                                target_ordinal,
                                policy,
                                tag_name=tag.name,
                                attribute_name=attribute.name,
                            )
                        )
            if not tag.self_closing and tag.name not in VOID_ELEMENTS:
                stack.append(tag.name)
        else:
            _pop_stack(stack, tag.name)
        cursor = tag_end

    return TokenizedDocument(source=source, targets=tuple(targets), tags=tuple(tags))


def tokenizer_strategy() -> str:
    return "absolute_source_spans"


def _make_target(
    source: str,
    start: int,
    end: int,
    ordinal: int,
    options: TokenizerOptions,
    *,
    tag_name: Optional[str],
    attribute_name: Optional[str] = None,
) -> TextTarget:
    radius = options.context_radius
    context_start = max(0, start - radius)
    context_end = min(len(source), end + radius)
    kind = "attr" if attribute_name is not None else "text"
    node_id = f"{options.document_kind}:{kind}:{ordinal}"
    return TextTarget(
        node_id=node_id,
        source_text=source[start:end],
        source_start=start,
        source_end=end,
        context=source[context_start:context_end],
        tag_name=tag_name,
        attribute_name=attribute_name,
        document_kind=options.document_kind,
    )


def _is_protected(stack: Sequence[str], options: TokenizerOptions) -> bool:
    for name in stack:
        if name in options.protected_elements:
            return True
        if name == "svg" and not options.svg_text:
            return True
        if name == "math" and not options.mathml:
            return True
    return False


def _element_is_writable(name: str, stack: Sequence[str], options: TokenizerOptions) -> bool:
    if name in options.protected_elements:
        return False
    if name == "svg" and not options.svg_text:
        return False
    if name == "math" and not options.mathml:
        return False
    return not _is_protected(stack, options)


def _raw_protected_name(stack: Sequence[str], options: TokenizerOptions) -> Optional[str]:
    if not stack:
        return None
    name = stack[-1]
    return name if name in {"script", "style"} else None


def _find_closing_tag(source: str, start: int, name: str) -> int:
    return source.lower().find("</" + name, start)


def _is_closing_tag_at(source: str, start: int, name: str) -> bool:
    prefix = source[start : start + len(name) + 2]
    return prefix.lower() == "</" + name


def _looks_like_markup(source: str, start: int) -> bool:
    if start + 1 >= len(source):
        return False
    character = source[start + 1]
    if character in {"!", "?", "/"}:
        return True
    return character.isalpha() or character == ":"


def _find_markup_end(source: str, start: int, bracket_aware: bool = False) -> int:
    quote: Optional[str] = None
    bracket_depth = 0
    cursor = start
    while cursor < len(source):
        character = source[cursor]
        if quote is not None:
            if character == quote:
                quote = None
        elif character in {"\"", "'"}:
            quote = character
        elif bracket_aware and character == "[":
            bracket_depth += 1
        elif bracket_aware and character == "]" and bracket_depth:
            bracket_depth -= 1
        elif character == ">" and bracket_depth == 0:
            return cursor + 1
        cursor += 1
    return len(source)


def _find_or_end(source: str, marker: str, start: int) -> int:
    found = source.find(marker, start)
    return len(source) if found < 0 else found + len(marker)


def _parse_tag(source: str, start: int, end: int) -> Optional[LexicalTag]:
    cursor = start + 1
    closing = False
    if cursor < end and source[cursor] == "/":
        closing = True
        cursor += 1
    while cursor < end and source[cursor].isspace():
        cursor += 1
    name_start = cursor
    while cursor < end and _is_name_character(source[cursor]):
        cursor += 1
    if name_start == cursor:
        return None
    name = source[name_start:cursor].lower()
    if closing:
        return LexicalTag(start, end, name, True, False)

    attributes = _parse_attributes(source, cursor, end)
    probe = end - 2
    while probe >= start and source[probe].isspace():
        probe -= 1
    self_closing = probe >= start and source[probe] == "/"
    return LexicalTag(start, end, name, False, self_closing, tuple(attributes))


def _parse_attributes(source: str, start: int, end: int) -> list[AttributeSpan]:
    attributes = []
    cursor = start
    while cursor < end:
        while cursor < end and (source[cursor].isspace() or source[cursor] == "/"):
            cursor += 1
        name_start = cursor
        while cursor < end and _is_attribute_name_character(source[cursor]):
            cursor += 1
        if name_start == cursor:
            cursor += 1
            continue
        name = source[name_start:cursor].lower()
        while cursor < end and source[cursor].isspace():
            cursor += 1
        if cursor >= end or source[cursor] != "=":
            continue
        cursor += 1
        while cursor < end and source[cursor].isspace():
            cursor += 1
        if cursor >= end:
            break
        quote: Optional[str] = None
        if source[cursor] in {"\"", "'"}:
            quote = source[cursor]
            cursor += 1
            value_start = cursor
            while cursor < end and source[cursor] != quote:
                cursor += 1
            value_end = cursor
            if cursor < end:
                cursor += 1
        else:
            value_start = cursor
            while cursor < end and not source[cursor].isspace() and source[cursor] != ">":
                cursor += 1
            value_end = cursor
        attributes.append(AttributeSpan(name, value_start, value_end, quote))
    return attributes


def _pop_stack(stack: list[str], name: str) -> None:
    for index in range(len(stack) - 1, -1, -1):
        if stack[index] == name:
            del stack[index:]
            return


def _split_entity_boundaries(source: str, start: int, end: int) -> Iterable[Tuple[int, int]]:
    cursor = start
    segment_start = start
    while cursor < end:
        if source[cursor] != "&":
            cursor += 1
            continue
        semicolon = source.find(";", cursor + 1, end)
        if semicolon < 0:
            cursor += 1
            continue
        if segment_start < cursor:
            yield segment_start, cursor
        cursor = semicolon + 1
        segment_start = cursor
    if segment_start < end:
        yield segment_start, end


def _is_name_character(character: str) -> bool:
    return character.isalnum() or character in {":", "-", "_"}


def _is_attribute_name_character(character: str) -> bool:
    return character.isalnum() or character in {":", "-", "_", "."}
