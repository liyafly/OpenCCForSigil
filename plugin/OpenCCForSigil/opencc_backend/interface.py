"""Backend protocol independent from UI, Sigil, and document parsing."""

from typing import Protocol, Tuple, TYPE_CHECKING

from opencc_backend.provenance import BackendProvenance

if TYPE_CHECKING:
    from opencc_backend.backend import SelfTestResult


class OpenCCBackendProtocol(Protocol):
    def __init__(self, config: str):
        ...

    def available_configs(self) -> Tuple[str, ...]:
        ...

    def convert(self, text: str) -> str:
        ...

    def provenance(self) -> BackendProvenance:
        ...

    def self_test(self) -> "SelfTestResult":
        ...

    def comparison_configs(self, config: str) -> Tuple[str, ...]:
        ...

    def close(self) -> None:
        ...
