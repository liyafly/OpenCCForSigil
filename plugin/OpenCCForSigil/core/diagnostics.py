"""Conversion diagnostics based on independent official config outputs."""

from dataclasses import dataclass
from typing import Callable


OfficialConvert = Callable[..., str]


@dataclass(frozen=True)
class ScriptDiagnostic:
    """Preflight script evidence; it never selects a conversion direction."""

    status: str
    simplified_changed: bool
    traditional_changed: bool
    source_length: int
    evidence_length: int
    warning: str = ""
    simplified_output: str = ""
    traditional_output: str = ""

    @property
    def label(self) -> str:
        return self.status.capitalize()


def diagnose_mixed_script(
    text: str,
    official_convert: OfficialConvert | object,
    *,
    min_evidence: int = 2,
    include_outputs: bool = False,
) -> ScriptDiagnostic:
    """Classify simplified/traditional evidence without a hand-written table.

    ``s2t`` and ``t2s`` are each called with the original input.  Short or
    punctuation-only inputs remain ``unknown`` because one conversion result
    is not enough evidence for a document-level direction.
    """

    if not isinstance(text, str):
        raise TypeError("diagnostic input must be text")
    simplified = _invoke_official(official_convert, "s2t", text)
    traditional = _invoke_official(official_convert, "t2s", text)
    evidence_length = sum(char.isalpha() and _is_han(char) for char in text)
    simplified_changed = simplified != text
    traditional_changed = traditional != text

    if evidence_length < min_evidence:
        status = "unknown"
        warning = "insufficient Han text for script diagnosis"
    elif simplified_changed and traditional_changed:
        status = "mixed"
        warning = "current text contains mixed simplified and traditional evidence"
    elif simplified_changed:
        status = "simplified"
        warning = ""
    elif traditional_changed:
        status = "traditional"
        warning = ""
    else:
        status = "unknown"
        warning = "official conversions found no directional evidence"

    return ScriptDiagnostic(
        status=status,
        simplified_changed=simplified_changed,
        traditional_changed=traditional_changed,
        source_length=len(text),
        evidence_length=evidence_length,
        warning=warning,
        simplified_output=simplified if include_outputs else "",
        traditional_output=traditional if include_outputs else "",
    )


def diagnose_script(
    text: str,
    official_convert: OfficialConvert | object,
    *,
    min_evidence: int = 2,
    include_outputs: bool = False,
) -> ScriptDiagnostic:
    """Compatibility alias for :func:`diagnose_mixed_script`."""

    return diagnose_mixed_script(
        text,
        official_convert,
        min_evidence=min_evidence,
        include_outputs=include_outputs,
    )


def _invoke_official(backend: OfficialConvert | object, config: str, text: str) -> str:
    if callable(backend):
        result = backend(config, text)
    else:
        method = getattr(backend, "convert_for_config", None)
        if callable(method):
            result = method(config, text)
        else:
            raise TypeError("official_convert must provide a config-aware callback")
    if not isinstance(result, str):
        raise TypeError("official conversion callback must return text")
    return result


def _is_han(char: str) -> bool:
    return any(
        start <= ord(char) <= end
        for start, end in (
            (0x3400, 0x4DBF),
            (0x4E00, 0x9FFF),
            (0xF900, 0xFAFF),
            (0x20000, 0x2FA1F),
        )
    )


def diagnostic_schema_version() -> int:
    return 1


__all__ = ["ScriptDiagnostic", "diagnose_mixed_script", "diagnose_script", "diagnostic_schema_version"]
