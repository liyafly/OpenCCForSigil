from __future__ import annotations

from pathlib import Path

import pytest

from app.profiles import Profile, ProfileStore, ProfileValidationError, migrate_profile_payload
from rules.models import Rule
from rules.store import RuleSet, RuleStore
from rules.validators import RuleValidationError


def test_legacy_profile_fields_normalize_and_round_trip(tmp_path: Path):
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
    assert profile.convert_nav is False
    assert profile.convert_ncx is True
    assert profile.convert_metadata is True
    assert profile.quotation_mode == "corner"
    assert profile.ruleset_ids == ("global",)
    assert profile.attributes == ("alt",)
    assert "include_nav" not in profile.to_dict()
    path = ProfileStore(tmp_path).save(profile)
    assert path.exists()
    assert ProfileStore(tmp_path).load("legacy").to_dict()["convert_nav"] is False


def test_profile_migration_and_actionable_failure(tmp_path: Path):
    migrated = migrate_profile_payload(
        {"name": "old", "conversion": "s2t", "segmentation": "mmseg"}
    )
    assert migrated["schema_version"] == 1
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
