"""Small, explicit rule templates for common regex cases."""

from __future__ import annotations

import re


def signature_protection() -> dict[str, object]:
    return {
        "semantic_version": 2,
        "type": "protect",
        "action": "protect",
        "match_type": "regex",
        "stage": "source",
        "source": r"◎[ \t\u3000]*(?:【著】|著)",
        "target": "",
    }


def protect_between_markers(left: str, right: str) -> dict[str, object]:
    if not left or not right:
        raise ValueError("both markers must contain text")
    return {
        "semantic_version": 2,
        "type": "protect",
        "action": "protect",
        "match_type": "regex",
        "stage": "source",
        "source": f"{re.escape(left)}[\\s\\S]*?{re.escape(right)}",
        "target": "",
    }


def contextual_replacement(
    before: str, term: str, after: str, replacement: str, *, stage: str = "pre"
) -> dict[str, object]:
    if not term:
        raise ValueError("the term to replace must contain text")
    if stage not in {"pre", "post"}:
        raise ValueError("contextual replacements must use the pre or post stage")
    pattern = (
        f"(?P<before>{re.escape(before)})"
        f"(?P<term>{re.escape(term)})"
        f"(?P<after>{re.escape(after)})"
    )
    escaped_replacement = replacement.replace("\\", "\\\\")
    target = f"\\g<before>{escaped_replacement}\\g<after>"
    return {
        "semantic_version": 2,
        "type": "exact",
        "action": "replace",
        "match_type": "regex",
        "stage": stage,
        "source": pattern,
        "target": target,
    }


def collapse_horizontal_spaces(count: int = 1) -> dict[str, object]:
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 16:
        raise ValueError("the kept space count must be between 1 and 16")
    return {
        "semantic_version": 2,
        "type": "exact",
        "action": "replace",
        "match_type": "regex",
        "stage": "post",
        "source": rf"[ \t\u3000]{{{count + 1},}}",
        "target": " " * count,
    }


__all__ = [
    "collapse_horizontal_spaces",
    "contextual_replacement",
    "protect_between_markers",
    "signature_protection",
]
