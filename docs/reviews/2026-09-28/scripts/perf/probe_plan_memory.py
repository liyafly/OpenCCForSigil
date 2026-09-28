#!/usr/bin/env python3
"""Compare retained plan memory: current models vs three prototypes
(slotted TokenChange/SourceSpan, shared equal change strings, no TextTarget.context).

Usage (repository root):
    mise exec -- uv run python probe_plan_memory.py [--slots] [--share-strings] [--no-context]
Run once per flag combination; --slots must replace the model classes before
the planner imports them. The digest over every change field must be equal
across runs, proving the prototypes keep plans identical. Synthetic data only.
"""

from __future__ import annotations

import argparse
import dataclasses
import gc
import hashlib
import sys
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synthetic_book  # noqa: E402,F401  (sets sys.path)

parser = argparse.ArgumentParser()
parser.add_argument("--slots", action="store_true")
parser.add_argument("--share-strings", action="store_true",
                    help="prototype: reuse one object per equal change source/target string")
parser.add_argument("--no-context", action="store_true",
                    help="prototype: do not populate the unused TextTarget.context")
parser.add_argument("--files", type=int, default=200)
args = parser.parse_args()

import core.models as models  # noqa: E402

if args.slots:
    for name in ("SourceSpan", "TokenChange"):
        original = getattr(models, name)
        namespace = {key: value for key, value in original.__dict__.items()
                     if key not in {"__dict__", "__weakref__"}}
        plain = type(name, (object,), {
            "__annotations__": original.__annotations__,
            "__module__": original.__module__,
            "__qualname__": original.__qualname__,
            **{field.name: field.default for field in dataclasses.fields(original)
               if field.default is not dataclasses.MISSING},
            **({"__post_init__": original.__post_init__}
               if hasattr(original, "__post_init__") else {}),
            **({"span": namespace["span"]} if "span" in namespace else {}),
        })
        setattr(models, name, dataclasses.dataclass(frozen=True, slots=True)(plain))

from core.models import ConvertRequest  # noqa: E402
import core.planner as planner  # noqa: E402
import document.tokenizer as tokenizer  # noqa: E402

if args.share_strings:
    _original_absolute = planner._absolute_change
    _shared: dict[str, str] = {}

    def _shared_absolute(*a, **k):
        change = _original_absolute(*a, **k)
        return dataclasses.replace(change,
                                   source=_shared.setdefault(change.source, change.source),
                                   target=_shared.setdefault(change.target, change.target))

    planner._absolute_change = _shared_absolute

if args.no_context:
    _original_make_target = tokenizer._make_target

    def _no_context_target(*a, **k):
        return dataclasses.replace(_original_make_target(*a, **k), context="")

    tokenizer._make_target = _no_context_target
from core.workflow import ConversionWorkflow  # noqa: E402
from opencc_backend.backend import OpenCCBackend  # noqa: E402
from sigil.adapter import SigilBookAdapter  # noqa: E402
from synthetic_book import SyntheticBook, build_sources  # noqa: E402

sources = build_sources(args.files, 60, 150)
workflow = ConversionWorkflow(SigilBookAdapter(SyntheticBook(sources)),
                              OpenCCBackend("s2t"), ConvertRequest("s2t"))
workflow.scan()
gc.collect()
tracemalloc.start()
base = tracemalloc.get_traced_memory()[0]
planned = workflow.plan()
gc.collect()
retained = tracemalloc.get_traced_memory()[0] - base
planned_changes = [item.plan.changes for item in planned]
tracemalloc.stop()

digest = hashlib.sha256()
count = 0
for changes in planned_changes:
    for change in changes:
        count += 1
        digest.update(repr(tuple(getattr(change, field.name) if field.name != "span" else
                                 (change.span.start, change.span.end)
                                 for field in dataclasses.fields(change))).encode())
string_bytes = sum(sys.getsizeof(c.source) + sys.getsizeof(c.target)
                   for changes in planned_changes for c in changes)
unique = {}
for changes in planned_changes:
    for c in changes:
        unique[c.source] = sys.getsizeof(c.source)
        unique[c.target] = sys.getsizeof(c.target)
print(f"change source/target string bytes={string_bytes / 2**20:.1f} MiB; "
      f"after sharing equal strings={sum(unique.values()) / 2**20:.1f} MiB")
print(f"slots={args.slots} share_strings={args.share_strings} "
      f"no_context={args.no_context} changes={count} "
      f"retained_mib={retained / 2**20:.1f} digest={digest.hexdigest()[:16]}")
