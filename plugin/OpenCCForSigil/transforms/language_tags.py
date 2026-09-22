"""Explicit Chinese language-tag planning; never infer a region for s2t (§15)."""

from dataclasses import replace

from core.models import TextTarget
from document.tokenizer import TokenizedDocument
from opencc_backend.configs import base_config


def is_han_language(value: str) -> bool:
    parts = value.strip().lower().split("-")
    return parts[0] == "zh" and all(
        len(part) != 4 or part in {"hans", "hant"} for part in parts[1:]
    )


def target_language(config: str, mode="keep", preset="legacy", region="") -> str | None:
    if mode not in {"keep", "suggest", "force"} or preset not in {"legacy", "bcp47"}:
        raise ValueError("invalid language mode or preset")
    if mode == "keep":
        return None
    config = base_config(config)
    if config in {"s2t", "tw2t", "hk2t"}:
        if preset == "bcp47":
            return "zh-Hant"
        if region in {"zh-TW", "zh-HK"}:
            return region
        if mode == "force":
            raise ValueError("generic Traditional Chinese requires an explicit Legacy region")
        return None
    choices = {
        "s2tw": ("zh-TW", "zh-Hant-TW"), "s2twp": ("zh-TW", "zh-Hant-TW"),
        "t2tw": ("zh-TW", "zh-Hant-TW"), "s2hk": ("zh-HK", "zh-Hant-HK"),
        "s2hkp": ("zh-HK", "zh-Hant-HK"), "t2hk": ("zh-HK", "zh-Hant-HK"),
    }
    for name in ("t2s", "tw2s", "tw2sp", "hk2s", "hk2sp"):
        choices[name] = ("zh-CN", "zh-Hans")
    result = choices.get(config)
    return result[preset == "bcp47"] if result else None


def with_language_targets(document: TokenizedDocument) -> TokenizedDocument:
    targets = list(document.targets)
    for tag in document.tags:
        if tag.closing:
            continue
        for attribute in tag.attributes:
            if attribute.name not in {"lang", "xml:lang"}:
                continue
            value = document.source[attribute.value_start:attribute.value_end]
            if not is_han_language(value):
                continue
            targets.append(TextTarget(
                node_id=f"language:attribute:{attribute.value_start}", source_text=value,
                source_start=attribute.value_start, source_end=attribute.value_end,
                tag_name=tag.name, attribute_name=attribute.name, document_kind="xhtml",
            ))
    return replace(document, targets=tuple(sorted(targets, key=lambda target: target.source_start)))
