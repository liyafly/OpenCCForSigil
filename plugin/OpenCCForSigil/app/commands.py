"""Application command names shared by future UI adapters."""

from enum import Enum


class Command(str, Enum):
    RUN = "run"
    SELF_TEST = "self_test"
    OPEN_LOG_DIRECTORY = "open_log_directory"
