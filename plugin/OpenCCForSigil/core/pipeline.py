"""Phase pipeline boundary for scan → analyze → plan → apply → verify."""

from typing import Protocol


class Pipeline(Protocol):
    def scan(self) -> None:
        ...

    def analyze(self) -> None:
        ...

    def plan(self) -> None:
        ...

    def apply_to_stage(self) -> None:
        ...

    def verify(self) -> None:
        ...
