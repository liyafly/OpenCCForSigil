from app.controller import Controller
from core.preview import PreviewSession
from ui.preview_window import PreviewOutcome


class ConversionBook:
    def __init__(self):
        self.files = {"chapter": '<p id="stable">漢字與鼠標</p><script>漢字</script>'}
        self.writes = []

    def text_iter(self):
        yield "chapter", "Text/chapter.xhtml"

    def readfile(self, file_id):
        return self.files[file_id]

    def writefile(self, file_id, data):
        self.writes.append((file_id, data))


def test_controller_runs_preview_stage_verify_commit(monkeypatch, tmp_path):
    book = ConversionBook()

    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config",
        lambda available_configs, default_config: "t2s",
    )

    def accept_all(planned):
        previews = tuple(PreviewSession(item.plan) for item in planned)
        for preview in previews:
            preview.accept_all()
        return PreviewOutcome(accepted=True, previews=previews)

    monkeypatch.setattr("ui.preview_window.show_preview", accept_all)
    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert len(book.writes) == 1
    assert "汉字与鼠标" in book.writes[0][1]
    assert "<script>漢字</script>" in book.writes[0][1]
    assert 'id="stable"' in book.writes[0][1]
    assert '"last_conversion_config": "t2s"' in (
        tmp_path / "plugin-data" / "preferences.json"
    ).read_text(encoding="utf-8")
