from app.controller import Controller
from core.preview import PreviewSession
from ui.preview_window import PreviewOutcome


class ConversionBook:
    def __init__(self):
        self.files = {"chapter": '<p id="stable">汉字与鼠标</p><script>汉字</script>'}
        self.writes = []

    def text_iter(self):
        yield "chapter", "Text/chapter.xhtml"

    def readfile(self, file_id):
        return self.files[file_id]

    def writefile(self, file_id, data):
        self.writes.append((file_id, data))


def test_controller_runs_preview_stage_verify_commit(monkeypatch, tmp_path):
    book = ConversionBook()

    def accept_all(planned):
        previews = tuple(PreviewSession(item.plan) for item in planned)
        for preview in previews:
            preview.accept_all()
        return PreviewOutcome(accepted=True, previews=previews)

    monkeypatch.setattr("ui.preview_window.show_preview", accept_all)
    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert len(book.writes) == 1
    assert "漢字與鼠標" in book.writes[0][1]
    assert "<script>汉字</script>" in book.writes[0][1]
    assert 'id="stable"' in book.writes[0][1]
