"""Pinned official OpenCC Python Binding boundary."""

from opencc_backend.backend import OpenCCBackend, SelfTestResult
from opencc_backend.configs import JIEBA_CONFIGS, SUPPORTED_CONFIGS, V1_CONFIGS

__all__ = [
    "JIEBA_CONFIGS",
    "OpenCCBackend",
    "SelfTestResult",
    "SUPPORTED_CONFIGS",
    "V1_CONFIGS",
]
