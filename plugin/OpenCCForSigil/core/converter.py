"""Conversion orchestration boundary.

The actual conversion remains in :mod:`opencc_backend`.  This module only
turns one backend result into source-relative changes that a planner can move
to absolute document offsets.
"""

from typing import Protocol

from core.diff import bounded_opcodes
from core.models import ConvertRequest, ConvertResult, SourceSpan, TokenChange
from opencc_backend.backend import OpenCCBackend


class Converter(Protocol):
    def convert(self, text: str, request: ConvertRequest) -> ConvertResult:
        ...


class OfficialBackendConverter:
    """Adapt one official backend instance to the core converter contract."""

    def __init__(self, backend: OpenCCBackend) -> None:
        self.backend = backend

    def convert(self, text: str, request: ConvertRequest) -> ConvertResult:
        if not isinstance(text, str):
            raise TypeError("conversion input must be text")
        target = self.backend.convert(text)
        if target == text:
            return ConvertResult(source=text, target=target)
        rule_source = f"OpenCC:{request.config}"
        changes = tuple(
            TokenChange(
                source=text[i1:i2],
                target=target[j1:j2],
                span=SourceSpan(i1, i2),
                rule_source=rule_source,
                category=_change_category(text[i1:i2], target[j1:j2]),
            )
            for tag, i1, i2, j1, j2 in bounded_opcodes(text, target)
            if tag != "equal"
        )
        return ConvertResult(source=text, target=target, changes=changes)


def _change_category(source: str, target: str) -> str:
    return "character" if max(len(source), len(target)) == 1 else "phrase"
