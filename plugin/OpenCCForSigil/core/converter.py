"""Conversion orchestration boundary.

The actual string conversion belongs to `opencc_backend`; this module will
later combine it with locked spans and rule snapshots.
"""

from typing import Protocol

from core.models import ConvertRequest, ConvertResult


class Converter(Protocol):
    def convert(self, text: str, request: ConvertRequest) -> ConvertResult:
        ...
