"""Absolute source-offset tokenizer boundary.

HTMLParser may assist with events later, but this module owns the source
cursor and never treats serializer output as a source-preserving patch.
"""


def tokenizer_strategy() -> str:
    return "absolute_source_spans"
