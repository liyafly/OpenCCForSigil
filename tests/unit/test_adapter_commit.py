import pytest

from sigil.adapter import CommitError, SigilBookAdapter


class Book:
    def __init__(self):
        self.writes = []

    def writefile(self, file_id, data):
        self.writes.append((file_id, data))


def test_adapter_captures_failures_from_staged_iterator_with_prior_commits():
    book = Book()
    adapter = SigilBookAdapter(book)

    def staged_files():
        yield "a", "converted a"
        raise RuntimeError("staged iterator failed")

    with pytest.raises(CommitError) as raised:
        adapter.commit(staged_files())

    assert raised.value.file_id == "<staged-iterator>"
    assert raised.value.committed_file_ids == ("a",)
    assert adapter.committed_file_ids == ("a",)
    assert book.writes == [("a", "converted a")]
