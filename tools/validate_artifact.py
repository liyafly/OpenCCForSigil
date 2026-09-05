#!/usr/bin/env python3
"""Validate the final plugin ZIP contents and third-party payload notices."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate(artifact: Path) -> None:
    if not artifact.is_file():
        raise SystemExit(f"plugin artifact is missing: {artifact}")
    with zipfile.ZipFile(artifact) as archive:
        names = archive.namelist()
        top_levels = {name.split("/", 1)[0] for name in names if name}
        if top_levels != {"OpenCCForSigil"}:
            raise SystemExit(f"unexpected plugin ZIP top-level entries: {sorted(top_levels)}")
        forbidden = (
            ".pyc",
            "/__pycache__/",
            "/native_build/",
            "/.git/",
            "/dist/",
        )
        bad = [name for name in names if any(token in name for token in forbidden)]
        if bad:
            raise SystemExit("development-only files in plugin artifact: " + ", ".join(bad[:5]))

        required = {
            "OpenCCForSigil/plugin.xml",
            "OpenCCForSigil/plugin.py",
            "OpenCCForSigil/vendor/opencc/manifest.json",
            "OpenCCForSigil/resources/third_party/THIRD_PARTY_NOTICES.md",
        }
        missing = sorted(required - set(names))
        if missing:
            raise SystemExit("plugin artifact missing required files: " + ", ".join(missing))

        manifest = json.loads(archive.read("OpenCCForSigil/vendor/opencc/manifest.json"))
        payloads = manifest.get("payloads", [])
        if not payloads:
            raise SystemExit("plugin artifact contains no official OpenCC payload")
        for payload in payloads:
            if payload.get("payload_runtime_test") != "passed":
                raise SystemExit(
                    "plugin artifact contains a payload without target-runtime self-test: "
                    + str(payload.get("payload_path"))
                )
            prefix = "OpenCCForSigil/vendor/opencc/" + str(payload["payload_path"]).rstrip("/") + "/"
            payload_names = [name for name in names if name.startswith(prefix)]
            if not payload_names:
                raise SystemExit(f"manifest payload is absent from plugin artifact: {prefix}")
            if prefix + "opencc/__init__.py" not in names:
                raise SystemExit(f"payload has no official opencc package: {prefix}")
            if not any(name.endswith(".dist-info/licenses/LICENSE") for name in payload_names):
                raise SystemExit(f"OpenCC license is absent from payload: {prefix}")
            if not any(name.endswith(".dist-info/licenses/AUTHORS") for name in payload_names):
                raise SystemExit(f"OpenCC authors notice is absent from payload: {prefix}")
            native_plugins = payload.get("native_plugins")
            plugin = native_plugins.get("opencc-jieba") if isinstance(native_plugins, dict) else None
            if not isinstance(plugin, dict):
                raise SystemExit(f"official native opencc-jieba record is absent: {prefix}")
            library_path = prefix + str(plugin.get("library_path", ""))
            if not library_path.startswith(prefix) or library_path not in names:
                raise SystemExit(f"native opencc-jieba library is absent: {library_path}")
            expected_library_hash = str(plugin.get("library_sha256", ""))
            actual_library_hash = _sha256_bytes(archive.read(library_path))
            if actual_library_hash.lower() != expected_library_hash.lower():
                raise SystemExit(f"native opencc-jieba library hash mismatch: {library_path}")
            for config in plugin.get("config_names", []):
                config_name = prefix + "opencc/clib/share/opencc/" + str(config) + ".json"
                if config_name not in names:
                    raise SystemExit(f"native opencc-jieba config is absent: {config_name}")
    print(f"plugin artifact valid: {artifact}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    validate(args.artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
