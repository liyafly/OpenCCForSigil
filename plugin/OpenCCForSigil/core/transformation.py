"""Pure post-conversion transforms and explicit force-pivot planning.

The functions in this module never import OpenCC.  Callers provide the
official backend callback, making the conversion authority and call order
visible to tests and to the planner.
"""

from dataclasses import dataclass
from typing import Callable, Final, Sequence


OfficialConvert = Callable[..., str]

# Force pivot is intentionally a small allowlist.  A chain is only accepted
# when it first converts to Simplified Chinese and then explicitly converts to
# one of the supported Traditional targets, or the reverse direction.  The
# tuple contains the actual official configs invoked, in order.
FORCE_PIVOT_CHAINS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("t2s", "s2t"),
        ("t2s", "s2tw"),
        ("t2s", "s2twp"),
        ("t2s", "s2hk"),
        ("t2s", "s2hkp"),
        ("s2t", "t2s"),
        ("s2tw", "t2s"),
        ("s2twp", "t2s"),
        ("s2hk", "t2s"),
        ("s2hkp", "t2s"),
    }
)


@dataclass(frozen=True)
class TransformationResult:
    source: str
    target: str
    chain: tuple[str, ...] = ()
    applied: bool = False
    category: str = "opencc_change"
    risk: str = "LOW"
    rule_source: str = ""


def apply_force_pivot(
    text: str,
    chain: Sequence[str],
    official_convert: OfficialConvert | object,
    *,
    enabled: bool = False,
) -> TransformationResult:
    """Apply an explicitly selected, validated high-risk pivot chain.

    With ``enabled=False`` the source is returned unchanged and no backend
    callback is invoked.  Enabled chains must be one of
    :data:`FORCE_PIVOT_CHAINS`; incompatible directions fail instead of being
    silently chained.
    """

    normalized = tuple(str(config) for config in chain)
    if len(normalized) != 2 or normalized not in FORCE_PIVOT_CHAINS:
        raise ValueError(f"unsupported force-pivot chain: {normalized!r}")
    if not enabled:
        return TransformationResult(source=text, target=text)

    current = text
    for config in normalized:
        current = _invoke_official(official_convert, config, current)
    return TransformationResult(
        source=text,
        target=current,
        chain=normalized,
        applied=True,
        category="opencc_change",
        risk="HIGH",
        rule_source="PivotChain:" + "→".join(normalized),
    )


def force_pivot(
    text: str,
    chain: Sequence[str],
    official_convert: OfficialConvert | object,
    *,
    enabled: bool = False,
) -> TransformationResult:
    """Compatibility alias for :func:`apply_force_pivot`."""

    return apply_force_pivot(text, chain, official_convert, enabled=enabled)


def _invoke_official(backend: OfficialConvert | object, config: str, text: str) -> str:
    if callable(backend):
        result = backend(config, text)
    else:
        method = getattr(backend, "convert_for_config", None)
        if not callable(method):
            raise TypeError("official_convert must provide a config-aware callback")
        result = method(config, text)
    if not isinstance(result, str):
        raise TypeError("official conversion callback must return text")
    return result


__all__ = [
    "FORCE_PIVOT_CHAINS",
    "TransformationResult",
    "apply_force_pivot",
    "force_pivot",
]
