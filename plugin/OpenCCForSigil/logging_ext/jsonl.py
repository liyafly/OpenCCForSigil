"""Small JSONL writer used by the session logger."""

import json
from pathlib import Path
from typing import Any, Mapping


def append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    """Append one UTF-8 JSON object and keep the file line-oriented."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
