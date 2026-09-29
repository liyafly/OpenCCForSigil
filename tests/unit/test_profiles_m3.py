from __future__ import annotations

from pathlib import Path

import pytest

from app.profiles import Profile, ProfileStore, ProfileValidationError, migrate_profile_payload
from rules.models import Rule
from rules.store import RuleSet, RuleStore
from rules.validators import RuleValidationError


def test_legacy_profile_field_names_remain_extras_and_round_trip(tmp_path: Path):
    profile = Profile.from_dict(
        {
            "schema_version": 1,
            "id": "legacy",
            "name": "Legacy",
            "conversion": "s2t",
            "segmentation": "mmseg",
            "include_nav": False,
            "include_ncx": True,
            "include_metadata": True,
            "quotation": "corner",
            "punctuation": "keep",
            "attributes": ["alt"],
            "ruleset_ids": ["global"],
        }
    )
    assert profile.convert_nav is True
    assert profile.convert_ncx is False
    assert profile.convert_metadata is False
    assert profile.quotation_mode == "keep"
    assert profile.ruleset_ids == ("global",)
    assert profile.attributes == ("alt",)
    assert dict(profile.extras) == {
        "include_metadata": True,
        "include_nav": False,
        "include_ncx": True,
        "punctuation": "keep",
        "quotation": "corner",
    }
    assert not hasattr(profile, "include_nav")
    path = ProfileStore(tmp_path).save(profile)
    assert path.exists()
    assert ProfileStore(tmp_path).load("legacy").convert_nav is True


def test_profile_still_loads_legacy_single_scope_string():
    profile = Profile.from_dict({
        "schema_version": 1,
        "id": "single-scope",
        "name": "Single scope",
        "conversion": "s2t",
        "segmentation": "mmseg",
        "scope": "single",
    })

    assert profile.scope == "single"


def test_profile_migration_and_actionable_failure(tmp_path: Path):
    with pytest.raises(ProfileValidationError, match="schema_version 0"):
        migrate_profile_payload(
            {"name": "old", "conversion": "s2t", "segmentation": "mmseg"}
        )
    with pytest.raises(ProfileValidationError, match="segmentation"):
        Profile.from_dict(
            {
                "schema_version": 1,
                "id": "x",
                "name": "x",
                "conversion": "s2t",
                "segmentation": "unknown",
            }
        )
    with pytest.raises(ProfileValidationError, match="unsupported"):
        Profile.from_dict(
            {
                "schema_version": 99,
                "id": "x",
                "name": "x",
                "conversion": "s2t",
                "segmentation": "mmseg",
            }
        )
    with pytest.raises(ProfileValidationError, match="V1.1"):
        Profile.from_dict(
            {
                "schema_version": 1,
                "id": "x",
                "name": "x",
                "conversion": "s2t",
                "segmentation": "mmseg",
                "regex_rules": True,
            }
        )


@pytest.mark.parametrize(("legacy", "canonical"), (
    ("auto", ""), ("zhTW", "zh-TW"), ("zhHK", "zh-HK"),
))
def test_language_region_aliases_normalize_during_profile_load(legacy, canonical):
    profile = Profile.from_dict({
        "schema_version": 1,
        "id": "x",
        "name": "x",
        "conversion": "s2t",
        "segmentation": "mmseg",
        "language_region": legacy,
    })

    assert profile.language_region == canonical
    assert Profile().language_region == ""


def test_saved_suggest_language_mode_loads_as_update():
    profile = Profile.from_dict({
        "schema_version": 1,
        "id": "legacy-suggest",
        "name": "Legacy suggest",
        "conversion": "s2t",
        "segmentation": "mmseg",
        "language_metadata": "suggest",
    })

    assert profile.language_metadata == "force"


def test_ruleset_store_round_trip_and_snapshot(tmp_path: Path):
    store = RuleStore(tmp_path)
    rules = (Rule(direction="s2t", source="软件", target="軟件"),)
    path = store.save(RuleSet("global", rules, "Global terms"))
    assert path == tmp_path / "rules" / "global.json"
    loaded = store.load("global")
    assert loaded.name == "Global terms"
    assert store.load_many(("global",))[0].target == "軟件"
    assert store.load_snapshot(("global",)).rules_hash


def test_profile_strict_enums_and_windowsafe_ids(tmp_path: Path):
    with pytest.raises(ProfileValidationError, match="quotation_mode"):
        Profile.from_dict(
            {
                "schema_version": 1,
                "id": "x",
                "name": "x",
                "conversion": "s2t",
                "segmentation": "mmseg",
                "quotation_mode": "free",
            }
        )
    with pytest.raises(ProfileValidationError, match="filename-safe"):
        ProfileStore(tmp_path).load("C:\\profile")
    with pytest.raises(RuleValidationError, match="filename-safe"):
        RuleStore(tmp_path).load("C:\\rules")
def test_protected_elements_survive_settings_policy_and_scripts_stay_protected():
    from app.settings import tokenizer_policy
    from document.tokenizer import tokenize_xhtml

    profile = Profile(protected_elements=("h1",), convert_code_pre=True)
    document = tokenize_xhtml('<h1>标题</h1><script>脚本</script><code>示例</code>',
                              tokenizer_policy(profile))
    assert [target.source_text for target in document.targets] == ["示例"]


def test_ruby_rtc_is_protected_by_the_profile_tokenizer_policy():
    from app.settings import tokenizer_policy
    from document.tokenizer import tokenize_xhtml

    document = tokenize_xhtml("<ruby>汉<rtc>ㄏㄢˋ</rtc></ruby>", tokenizer_policy(Profile()))

    assert [target.source_text for target in document.targets] == ["汉"]


def test_profile_mathml_setting_controls_mathml_text_targets():
    from app.settings import tokenizer_policy
    from document.tokenizer import tokenize_xhtml

    source = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        '<m:math xmlns:m="http://www.w3.org/1998/Math/MathML" id="formula">'
        '<m:mi title="identifier">变量</m:mi><m:mo>+</m:mo><m:mn>2</m:mn>'
        '<m:mtext title="annotation">说明<m:mi>符号</m:mi>文字</m:mtext>'
        '<m:mtext xmlns:m="urn:unknown">不应转换</m:mtext>'
        '<m:annotation encoding="text/plain">注释</m:annotation>'
        '<m:annotation-xml encoding="application/xhtml+xml"><p>片段</p>'
        '</m:annotation-xml>'
        '</m:math></body></html>'
    )
    disabled = tokenize_xhtml(source, tokenizer_policy(Profile(mathml=False)))
    payload = Profile(mathml=True, name="mathml safety").to_dict()
    restored = Profile.from_dict(payload)
    enabled = tokenize_xhtml(source, tokenizer_policy(restored))

    assert disabled.targets == ()
    assert [target.source_text for target in enabled.targets] == ["说明", "文字"]
    assert all(target.attribute_name is None for target in enabled.targets)


def test_profile_mathml_skips_unknown_mathml_namespace():
    from app.settings import tokenizer_policy
    from document.tokenizer import tokenize_xhtml

    source = "<math xmlns='urn:unknown'><mtext>不应转换</mtext></math>"
    document = tokenize_xhtml(source, tokenizer_policy(Profile(mathml=True)))

    assert document.targets == ()


def test_profile_mathml_without_namespace_only_opens_mtext_text():
    from app.settings import tokenizer_policy
    from document.tokenizer import tokenize_xhtml

    source = (
        "<math><mi>变量</mi><mtext>说明<mi>符号</mi>文字</mtext>"
        "<annotation>批注</annotation></math>"
    )
    document = tokenize_xhtml(source, tokenizer_policy(Profile(mathml=True)))

    assert [target.source_text for target in document.targets] == ["说明", "文字"]
