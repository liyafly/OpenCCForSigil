"""Official OpenCC config families and comparison metadata."""

from typing import Dict, Tuple

from app.errors import DependencyError


V1_CONFIGS: Tuple[str, ...] = (
    "s2t",
    "t2s",
    "s2tw",
    "tw2s",
    "s2twp",
    "tw2sp",
    "s2hk",
    "hk2s",
    "s2hkp",
    "hk2sp",
    "t2tw",
    "tw2t",
    "t2hk",
    "hk2t",
    "t2jp",
    "jp2t",
)

# These names are supplied by the official upstream native opencc-jieba
# plugin.  They are intentionally separate from the standard config family:
# their availability depends on the selected payload's native plugin record.
JIEBA_CONFIGS: Tuple[str, ...] = (
    "s2t_jieba",
    "s2tw_jieba",
    "s2twp_jieba",
    "s2hk_jieba",
    "s2hkp_jieba",
    "tw2sp_jieba",
    "hk2sp_jieba",
)

SUPPORTED_CONFIGS: Tuple[str, ...] = V1_CONFIGS + JIEBA_CONFIGS

JIEBA_CONFIG_BY_BASE: Dict[str, str] = {
    "s2t": "s2t_jieba",
    "s2tw": "s2tw_jieba",
    "s2twp": "s2twp_jieba",
    "s2hk": "s2hk_jieba",
    "s2hkp": "s2hkp_jieba",
    "tw2sp": "tw2sp_jieba",
    "hk2sp": "hk2sp_jieba",
}
BASE_CONFIG_BY_JIEBA = {value: key for key, value in JIEBA_CONFIG_BY_BASE.items()}


_COMPARISON_CONFIGS: Dict[str, Tuple[str, ...]] = {
    "s2twp": ("s2t", "s2tw", "s2twp"),
    "s2hkp": ("s2t", "s2hk", "s2hkp"),
    "tw2sp": ("tw2s", "tw2sp"),
    "hk2sp": ("hk2s", "hk2sp"),
}


def validate_config(config: str) -> str:
    if config not in SUPPORTED_CONFIGS:
        raise DependencyError(f"config is not in the official OpenCC allowlist: {config}")
    return config


def is_jieba_config(config: str) -> bool:
    return config in JIEBA_CONFIGS


def base_config(config: str) -> str:
    return BASE_CONFIG_BY_JIEBA.get(config, config)


def comparison_configs(config: str) -> Tuple[str, ...]:
    """Return independent comparison configs for attribution only."""

    validate_config(config)
    if config in JIEBA_CONFIGS:
        return (base_config(config), config)
    return _COMPARISON_CONFIGS.get(config, (config,))
