from app.controller import Controller
from app.session import SessionState


class FakeBookContainer:
    def __init__(self):
        self.write_calls = []

    def writefile(self, file_id, data):
        self.write_calls.append((file_id, data))
        raise AssertionError("Phase 0 must not write book content")


def test_phase0_controller_completes_without_book_mutation(tmp_path):
    book = FakeBookContainer()
    controller = Controller(book, data_dir=tmp_path / "plugin-data")

    assert controller.run() == 0
    assert controller.session.state is SessionState.COMPLETED
    assert book.write_calls == []
