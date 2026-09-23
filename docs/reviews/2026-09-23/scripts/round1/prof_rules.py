"""Round 1 (L-07): cProfile of the rule overlay with ~2000 rules, 100 nodes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)

import cProfile
import pstats
import random

from bench_rules import make_nodes, make_request
from core.converter import OfficialBackendConverter
from opencc_backend.backend import OpenCCBackend

rng = random.Random(1)
converter = OfficialBackendConverter(OpenCCBackend("s2t"))
nodes = make_nodes(rng, count=100)
request, unique = make_request(rng, 2000)
print("rules:", unique)
profile = cProfile.Profile()
profile.enable()
for node in nodes:
    converter.convert(node, request)
profile.disable()
pstats.Stats(profile).sort_stats("cumulative").print_stats(18)
