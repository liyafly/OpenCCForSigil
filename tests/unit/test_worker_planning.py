from threading import Event, get_ident
import time
from types import SimpleNamespace

import pytest

from core.models import ConvertRequest
from core.preview import PreviewSession
from core.workflow import ConversionWorkflow, SourceDocument, WorkflowCancelled
from sigil.adapter import SigilBookAdapter


def test_worker_owns_backend_and_main_owns_book_and_progress():
    main = get_ident()
    calls = []

    class Book:
        def text_iter(self):
            assert get_ident() == main
            yield "a", "a.xhtml"

        def readfile(self, _id):
            assert get_ident() == main
            return "<p>汉</p>"

        def writefile(self, _id, source):
            assert get_ident() == main
            calls.append(("write", source))

    class Backend:
        def __init__(self, config):
            assert get_ident() != main
            self.config = config
            self.thread = get_ident()

        def convert(self, text):
            assert get_ident() == self.thread
            return text.replace("汉", "漢")

        def provenance(self):
            return SimpleNamespace(as_dict=lambda: {"test": True})

        def close(self):
            assert get_ident() == self.thread
            calls.append(("closed", True))

    def progress(*_args):
        assert get_ident() == main

    flow = ConversionWorkflow(SigilBookAdapter(Book()), None, ConvertRequest("s2t"))
    planned = flow.plan_in_worker(Backend, progress=progress)
    assert calls == [("closed", True)]
    previews = [PreviewSession(item.plan) for item in planned]
    for preview in previews:
        preview.accept_all()
    flow.stage(flow.finalize(previews))
    flow.verify()
    flow.commit()
    assert calls[-1] == ("write", "<p>漢</p>")


def test_cancel_during_worker_discards_plan_without_writes():
    started = Event()
    finish = Event()
    closed = Event()

    class Book:
        def text_iter(self):
            yield "a", "a.xhtml"

        def readfile(self, _id):
            return "<p>汉</p>"

        def writefile(self, *_args):
            pytest.fail("cancelled work wrote a file")

    class Backend:
        def __init__(self, config):
            self.config = config

        def convert(self, text):
            started.set()
            assert finish.wait(5)
            return text.replace("汉", "漢")

        def provenance(self):
            return SimpleNamespace(as_dict=lambda: {})

        def close(self):
            closed.set()

    def cancelled():
        if started.is_set():
            finish.set()
            return True
        return False

    class Progress:
        def __init__(self):
            self.updates = []
            self.cancelling_count = 0

        def update(self, *values):
            self.updates.append(values)

        def set_cancelling(self):
            self.cancelling_count += 1

    flow = ConversionWorkflow(SigilBookAdapter(Book()), None, ConvertRequest("s2t"))
    progress = Progress()
    with pytest.raises(WorkflowCancelled):
        flow.plan_in_worker(Backend, progress=progress.update, cancelled=cancelled)
    assert closed.is_set()
    assert flow._planned == ()
    assert tuple(flow.staging.values()) == ()
    assert progress.cancelling_count == 1


def test_worker_progress_coalesces_large_update_bursts():
    burst_queued = Event()
    flow = ConversionWorkflow(None, None, ConvertRequest("s2t"))
    flow._sources = tuple(
        SourceDocument(str(index), f"Text/{index}.xhtml", "") for index in range(500)
    )
    flow.scan = lambda **_kwargs: flow._sources
    flow._plan_document = lambda source, **_kwargs: source

    class Backend:
        def __init__(self, _config):
            pass

        def close(self):
            # Keep the future alive after its whole update burst is queued so
            # the main-thread consumer has to drain/coalesce the queue.
            burst_queued.set()
            time.sleep(0.3)

    updates = []

    def progress(*values):
        updates.append(values)

    result = flow.plan_in_worker(Backend, progress=progress)

    assert len(result) == 500
    assert updates[-1][1:3] == (500, 500)
    assert burst_queued.is_set()
    assert 1 < len(updates) < 100
