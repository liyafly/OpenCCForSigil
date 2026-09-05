"""Book selection scope names."""

from enum import Enum


class Scope(str, Enum):
    ALL_XHTML = "all_xhtml"
    SPINE = "spine"
    SELECTED = "selected"
