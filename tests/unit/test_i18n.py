from ui.i18n import Translator, choose_language, load_catalogs, normalize_language
from ui import preview_window


def test_supported_catalogs_have_same_keys_and_render_placeholders():
    catalogs = load_catalogs()
    assert set(catalogs) == {"zh-Hans", "en", "zh-Hant"}
    expected = set(catalogs["en"])
    assert all(set(catalog) == expected for catalog in catalogs.values())
    for language in catalogs:
        text = Translator(language).text("scope.selected_count", selected=2, total=8)
        assert "2" in text and "8" in text
        detail = Translator(language).text("preview.change")
        assert detail and detail != "preview.change"
        progress = Translator(language).text("progress.status", phase=Translator(language).text("progress.phase.analyzing"), index=1, total=2, file="a.xhtml")
        assert "a.xhtml" in progress


def test_locale_mapping_and_preference_precedence():
    assert normalize_language("zh_TW") == "zh-Hant"
    assert normalize_language("zh-CN") == "zh-Hans"
    assert choose_language("zh-Hant", "en", "en-US") == "zh-Hant"
    assert choose_language(None, "zh-TW", "en-US") == "zh-Hant"
    assert choose_language(None, None, "de-DE") == "en"


def test_dialogs_share_one_qapplication_instance():
    class FakeApplication:
        current = None
        created = 0

        @classmethod
        def instance(cls):
            return cls.current

        def __init__(self, _args):
            type(self).created += 1
            type(self).current = self

    class FakeQt:
        QApplication = FakeApplication

    first = preview_window._ensure_application(FakeQt)
    second = preview_window._ensure_application(FakeQt)
    assert first is second
    assert FakeApplication.created == 1
