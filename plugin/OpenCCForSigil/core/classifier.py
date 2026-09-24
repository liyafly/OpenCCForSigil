"""Comparative config attribution boundary.

`comparative_config_diff` is explanatory metadata only and never changes the
selected official OpenCC conversion output.
"""

from dataclasses import dataclass
from typing import Callable

from core.diff import bounded_opcodes
from opencc_backend.configs import comparison_configs


OfficialConvert = Callable[..., str]


@dataclass(frozen=True)
class ClassifiedChange:
    source: str
    target: str
    source_start: int
    source_end: int
    target_start: int
    target_end: int
    category: str
    rule_source: str
    attribution_method: str = "comparative_config_diff"
    comparison_stage: str | None = None
    attribution_confidence: str = "low"


@dataclass(frozen=True)
class ComparativeClassification:
    source: str
    final: str
    config: str
    comparisons: tuple[tuple[str, str], ...]
    changes: tuple[ClassifiedChange, ...]
    attribution_method: str = "comparative_config_diff"


_REGIONAL_BASES = {
    "s2twp": "s2tw",
    "s2hkp": "s2hk",
    "tw2sp": "tw2s",
    "hk2sp": "hk2s",
}


def classify_conversion(
    source: str,
    config: str,
    official_convert: OfficialConvert | object,
    *,
    final: str | None = None,
) -> ComparativeClassification:
    """Classify selected-output changes using independent original-input calls.

    ``final`` may be supplied when the planner already holds the frozen target;
    comparison calls remain diagnostic-only and never replace it.
    """

    configs = comparison_configs(config)
    outputs = tuple((name, final if name == config and final is not None else
                     _invoke_official(official_convert, name, source)) for name in configs)
    output_map = dict(outputs)
    selected = final if final is not None else output_map.get(config)
    if selected is None:
        selected = _invoke_official(official_convert, config, source)
    alignment_cache = {}

    def alignment(output: str):
        if output not in alignment_cache:
            alignment_cache[output] = bounded_opcodes(source, output)
        return alignment_cache[output]

    final_alignment = alignment(selected)

    changes: list[ClassifiedChange] = []
    for tag, i1, i2, j1, j2 in final_alignment:
        if tag == "equal":
            continue
        source_part = source[i1:i2]
        target_part = selected[j1:j2]
        category, stage, confidence = _classify_change(
            config,
            source,
            selected,
            output_map,
            alignment,
            target_part,
            i1,
            i2,
            j1,
            j2,
        )
        changes.append(
            ClassifiedChange(
                source=source_part,
                target=target_part,
                source_start=i1,
                source_end=i2,
                target_start=j1,
                target_end=j2,
                category=category,
                rule_source=f"OpenCC:{config}",
                comparison_stage=stage,
                attribution_confidence=confidence,
            )
        )
    return ComparativeClassification(
        source=source,
        final=selected,
        config=config,
        comparisons=outputs,
        changes=tuple(changes),
    )


def comparative_classification(
    source: str,
    config: str,
    official_convert: OfficialConvert | object,
    *,
    final: str | None = None,
) -> ComparativeClassification:
    """Compatibility alias for :func:`classify_conversion`."""

    return classify_conversion(source, config, official_convert, final=final)


def _classify_change(
    config: str,
    source: str,
    final: str,
    outputs: dict[str, str],
    alignment: Callable[[str], tuple[tuple[str, int, int, int, int], ...]],
    target_part: str,
    source_start: int,
    source_end: int,
    target_start: int,
    target_end: int,
) -> tuple[str, str | None, str]:
    if config in {"s2tw", "s2hk"} and "s2t" in outputs:
        start, end, stable = _project_target(source, outputs["s2t"], source_start,
                                            source_end, _alignment_if_needed(
                                                source, outputs["s2t"], alignment))
        if not stable or target_end - target_start != source_end - source_start:
            return "phrase", None, "low"
        if final[target_start:target_end] != outputs["s2t"][start:end]:
            return "variant", f"{config}-vs-s2t", "high"
    base = _REGIONAL_BASES.get(config)
    generic = "s2t" if config in {"s2twp", "s2hkp"} else None
    if base is not None and base in outputs:
        base_output = outputs[base]
        final_piece = final[target_start:target_end]
        base_start, base_end, base_stable = _project_target(
            source, base_output, source_start, source_end,
            _alignment_if_needed(source, base_output, alignment),
        )
        if base_stable:
            base_piece = base_output[base_start:base_end]
            if final_piece != base_piece:
                confidence = _confidence(
                    source[source_start:source_end],
                    target_part,
                    final_piece,
                    base_piece,
                )
                return "regional", f"{config}-vs-{base}", confidence
            if generic in outputs:
                generic_output = outputs[generic]
                generic_start, generic_end, generic_stable = _project_target(
                    source,
                    generic_output,
                    source_start,
                    source_end,
                    _alignment_if_needed(source, generic_output, alignment),
                )
                if generic_stable:
                    generic_piece = generic_output[generic_start:generic_end]
                    if base_piece != generic_piece:
                        confidence = _confidence(
                            source[source_start:source_end],
                            target_part,
                            final_piece,
                            generic_piece,
                        )
                        return "variant", f"{base}-vs-{generic}", confidence
        else:
            return "phrase", None, "low"

    category = "character" if max(source_end - source_start, len(target_part)) == 1 else "phrase"
    return category, None, "low" if not outputs else "high"


def _alignment_if_needed(source: str, output: str, alignment):
    return alignment(output) if len(source) != len(output) else None


def _confidence(source: str, target: str, final: str, comparison: str) -> str:
    if len(source) == len(target) == len(final) == len(comparison):
        return "high"
    return "low"


def _project_target(
    source: str,
    target: str,
    source_start: int,
    source_end: int,
    opcodes: tuple[tuple[str, int, int, int, int], ...] | None = None,
) -> tuple[int, int, bool]:
    """Project one source span through a source-to-output alignment.

    A length-changing opcode cannot provide a unique character-level
    projection.  The returned ``False`` confidence forces the caller to use a
    conservative phrase classification.
    """

    if len(source) == len(target):
        return source_start, source_end, True
    if opcodes is None:
        opcodes = bounded_opcodes(source, target)

    projected_start: int | None = None
    projected_end: int | None = None
    stable = True
    for tag, i1, i2, j1, j2 in opcodes:
        if i1 == i2:
            if source_start <= i1 <= source_end:
                projected_start = j1 if projected_start is None else min(projected_start, j1)
                projected_end = j2 if projected_end is None else max(projected_end, j2)
            continue
        overlap_start = max(i1, source_start)
        overlap_end = min(i2, source_end)
        if overlap_start >= overlap_end:
            continue
        source_width = i2 - i1
        target_width = j2 - j1
        if source_width != target_width:
            stable = False
            mapped_start, mapped_end = j1, j2
        else:
            mapped_start = j1 + overlap_start - i1
            mapped_end = j1 + overlap_end - i1
        projected_start = (
            mapped_start if projected_start is None else min(projected_start, mapped_start)
        )
        projected_end = mapped_end if projected_end is None else max(projected_end, mapped_end)
    if projected_start is None or projected_end is None:
        return 0, 0, stable
    return projected_start, projected_end, stable


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


def attribution_method() -> str:
    return "comparative_config_diff"


__all__ = [
    "ClassifiedChange",
    "ComparativeClassification",
    "attribution_method",
    "classify_conversion",
    "comparative_classification",
]
