"""V1 OpenCC config allowlist and comparison metadata."""

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


_COMPARISON_CONFIGS: Dict[str, Tuple[str, ...]] = {
    "s2twp": ("s2t", "s2tw", "s2twp"),
    "s2hkp": ("s2t", "s2hk", "s2hkp"),
    "tw2sp": ("tw2s", "tw2sp"),
    "hk2sp": ("hk2s", "hk2sp"),
}


def validate_config(config: str) -> str:
    if config not in V1_CONFIGS:
        raise DependencyError(f"config is not in the V1 official OpenCC allowlist: {config}")
    return config


def comparison_configs(config: str) -> Tuple[str, ...]:
    """Return independent comparison configs for attribution only."""

    validate_config(config)
    return _COMPARISON_CONFIGS.get(config, (config,))
