from ui.i18n import Translator, choose_language, load_catalogs, normalize_language


def test_supported_catalogs_have_same_keys_and_render_placeholders():
    catalogs = load_catalogs()
    assert set(catalogs) == {"zh-Hans", "en", "zh-Hant"}
    for language in catalogs:
        text = Translator(language).text("scope.selected_count", selected=2, total=8)
        assert "2" in text and "8" in text


def test_locale_mapping_and_preference_precedence():
    assert normalize_language("zh_TW") == "zh-Hant"
    assert normalize_language("zh-CN") == "zh-Hans"
    assert choose_language("zh-Hant", "en", "en-US") == "zh-Hant"
    assert choose_language(None, "zh-TW", "en-US") == "zh-Hant"
    assert choose_language(None, None, "de-DE") == "en"
