"""Preferences boundary; profiles and rules use separate files."""

from typing import Any, Mapping

from sigil.storage import UserDataStore


def load_preferences(store: UserDataStore) -> dict:
    return store.load_preferences(
        {
            "schema_version": 1,
            "last_profile_id": "conservative",
            "ui": {},
        }
    )


def save_preferences(store: UserDataStore, values: Mapping[str, Any]) -> None:
    store.save_preferences(values)
