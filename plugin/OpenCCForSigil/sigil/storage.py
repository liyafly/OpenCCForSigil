"""User-data location and schema-aware storage helpers."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Optional

from app.errors import StorageError


APP_DIRECTORY_NAME = "OpenCCForSigil"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StoragePaths:
    root: Path
    preferences: Path
    profiles: Path
    rules: Path
    logs: Path
    history: Path
    exports: Path
    cache: Path

    @classmethod
    def from_root(cls, root: Path) -> "StoragePaths":
        return cls(
            root=root,
            preferences=root / "preferences.json",
            profiles=root / "profiles",
            rules=root / "rules",
            logs=root / "logs",
            history=root / "history",
            exports=root / "exports",
            cache=root / "cache",
        )


def resolve_user_data_dir(bk: Any) -> Path:
    """Resolve storage using the documented Sigil preference fallback order."""

    window = getattr(bk, "_w", None)
    support_dir = getattr(window, "usrsupdir", None)
    if support_dir:
        return Path(support_dir) / "plugins_prefs" / APP_DIRECTORY_NAME

    try:
        return Path.home() / ".opencc-for-sigil"
    except RuntimeError:
        return Path(tempfile.gettempdir()) / ".opencc-for-sigil"


class UserDataStore:
    """Persist plugin-owned data outside the plugin installation directory."""

    def __init__(self, root: Path) -> None:
        self.paths = StoragePaths.from_root(root)
        self.read_only_preferences = False
        self._recovery_notice: tuple[str, str] | None = None

    def ensure_layout(self) -> StoragePaths:
        for directory in (
            self.paths.root,
            self.paths.profiles,
            self.paths.rules,
            self.paths.logs,
            self.paths.history,
            self.paths.exports,
            self.paths.cache,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return self.paths

    def load_preferences(self, default: Optional[Mapping[str, Any]] = None) -> dict:
        """Load schema version 1 preferences without silently resetting data."""

        if not self.paths.preferences.exists():
            return dict(default or {"schema_version": SCHEMA_VERSION})
        try:
            payload = self._read_json(self.paths.preferences)
        except StorageError:
            backup = self.quarantine(self.paths.preferences)
            self._recovery_notice = ("preferences_corrupt", backup.name)
            return dict(default or {"schema_version": SCHEMA_VERSION})
        version = payload.get("schema_version")
        if isinstance(version, int) and not isinstance(version, bool) and version > SCHEMA_VERSION:
            self.read_only_preferences = True
            self._recovery_notice = ("preferences_future_schema", str(version))
            return payload
        if version != SCHEMA_VERSION:
            backup = self.quarantine(self.paths.preferences)
            self._recovery_notice = ("preferences_corrupt", backup.name)
            return dict(default or {"schema_version": SCHEMA_VERSION})
        return payload

    def save_preferences(self, values: Mapping[str, Any]) -> None:
        if self.read_only_preferences:
            return
        payload = dict(values)
        payload.setdefault("schema_version", SCHEMA_VERSION)
        self._validate_schema(payload, self.paths.preferences)
        self._write_json(self.paths.preferences, payload)

    def quarantine(self, path: str | Path) -> Path:
        """Rename one plugin-owned data file to a timestamped recovery copy."""

        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.paths.root / candidate
        root = self.paths.root.resolve()
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise StorageError("recovery files must be inside the plugin data directory") from exc
        if not resolved.is_file():
            raise StorageError("only plugin-owned files can be quarantined")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = resolved.with_name(f"{resolved.name}.corrupt-{timestamp}")
        suffix = 1
        while destination.exists():
            destination = resolved.with_name(f"{resolved.name}.corrupt-{timestamp}-{suffix}")
            suffix += 1
        resolved.replace(destination)
        return destination

    def take_recovery_notice(self) -> tuple[str, str] | None:
        notice = self._recovery_notice
        self._recovery_notice = None
        return notice

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as exc:
            raise StorageError(f"could not read JSON storage: {path}") from exc
        if not isinstance(payload, dict):
            raise StorageError(f"JSON storage must contain an object: {path}")
        return payload

    @staticmethod
    def _validate_schema(payload: Mapping[str, Any], path: Path) -> None:
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise StorageError(
                f"unsupported schema_version in {path}; migration is required before writing"
            )

    @staticmethod
    def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            temporary.replace(path)
        except OSError as exc:
            raise StorageError(f"could not write JSON storage: {path}") from exc
