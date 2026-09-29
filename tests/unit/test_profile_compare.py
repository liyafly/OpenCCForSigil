from dataclasses import fields, replace

from app.profiles import Profile
from ui.profile_compare import compare_profile_settings, normalized_profile_values


def test_names_and_ids_do_not_count_as_conversion_changes():
    current = Profile(id="draft", name="Unsaved", conversion="s2t")
    candidate = replace(current, id="saved", name="A different name")

    assert compare_profile_settings(current, candidate) == ()


def test_empty_sequences_and_panel_defaults_normalize_consistently():
    current = {
        "conversion": "s2t", "scope": "all", "ruleset_ids": [],
        "pivot_chain": [],
    }
    candidate = {
        "conversion": "s2t", "scope": "all_xhtml", "ruleset_ids": (),
        "pivot_chain": (),
    }

    assert compare_profile_settings(current, candidate) == ()
    assert normalized_profile_values(current)["ruleset_ids"] == ()


def test_missing_profile_fields_and_empty_language_region_use_defaults():
    minimal = {"conversion": "s2t", "language_region": ""}
    complete = Profile(conversion="s2t", language_region="")

    assert compare_profile_settings(minimal, complete) == ()
    assert normalized_profile_values({"conversion": "s2t"})["convert_nav"] is True


def test_legacy_diagnostic_panel_options_do_not_change_profile_comparison():
    before = {
        "conversion": "s2t",
        "diagnose_mixed": True,
        "detailed_classification": True,
    }
    after = {
        "conversion": "s2t",
        "diagnose_mixed": False,
        "detailed_classification": False,
    }

    assert compare_profile_settings(before, after) == ()
    normalized = normalized_profile_values(before)
    assert "diagnose_mixed" not in normalized
    assert "detailed_classification" not in normalized


def test_compare_covers_every_runtime_profile_field():
    current = Profile(id="a", name="Current")
    candidate = replace(
        current,
        conversion="s2tw",
        segmentation="jieba",
        scope="selected",
        convert_nav=False,
        convert_ncx=True,
        convert_metadata=True,
        convert_alt=False,
        convert_title=False,
        convert_aria_label=True,
        convert_svg_text=True,
        convert_ruby_rt=True,
        convert_code_pre=True,
        decode_numeric_cjk_refs=True,
        quotation_mode="curly",
        punctuation_mode="horizontal",
        language_metadata="suggest",
        language_preset="bcp47",
        language_region="zh-TW",
        ruleset_ids=("default", "other"),
        builtin_rules_enabled=False,
        preview_required=False,
        attributes=("aria-label",),
        protected_elements=("pre",),
        mathml=True,
        numeric_cjk_char_refs="decode",
        tofu_policy="exclude",
        regex_rules=True,
        force_pivot=True,
        pivot_chain=("t2s", "s2tw"),
        review_annotations=True,
        checkpoint_notice=False,
    )
    changed = {name for name, _before, _after in
               compare_profile_settings(current, candidate)}
    expected = {item.name for item in fields(Profile)
                if item.name not in {"schema_version", "id", "name", "extras"}}

    assert changed == expected
