import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import time
import queue

import core.workflow as wfmod
from core.workflow import ConversionWorkflow, SourceDocument
from core.models import ConvertRequest


class B:
    def __init__(self, _c):
        pass

    def close(self):
        pass


def scenario(tail_sleep):
    flow = ConversionWorkflow(None, None, ConvertRequest("s2t"))
    flow._sources = tuple(SourceDocument(str(i), f"Text/{i}.xhtml", "") for i in range(500))
    flow.scan = lambda **_k: flow._sources
    n = [0]

    def plan_doc(src, **_k):
        n[0] += 1
        if n[0] == 500:
            time.sleep(tail_sleep)
        return src

    flow._plan_document = plan_doc
    updates = []
    flow.plan_in_worker(B, progress=lambda *v: updates.append(v))
    # drop the final unconditional progress call
    before_final = updates[:-1]
    return len(updates), updates[-1][1:3], (before_final[-1][1] if before_final else None)


print("current code  (repo test scenario):", scenario(0))
print("current code  (burst then 300ms tail):", scenario(0.3))


class NoDrain(queue.Queue):
    def get_nowait(self):
        raise queue.Empty


wfmod.Queue = NoDrain
print("no-drain code (repo test scenario):", scenario(0))
print("no-drain code (burst then 300ms tail):", scenario(0.3))
