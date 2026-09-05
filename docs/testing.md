# Testing

The initial exit condition is:

```text
pytest unit storage/logging = PASS
plugin package metadata = PASS
official vendored payload manifest/hash = PASS
official CLI/Python Binding differential smoke = 100% equality
source-preserving plan/stage/verify integration = PASS
preview acceptance/rejection integration = PASS
preflight-only run = success with zero BookContainer writes when no text API exists
```

Run locally with the pinned environment:

```sh
mise install
mise exec -- uv sync --locked
make check
```

The test tree follows the specification's fixed separation. The current slice
also validates the checked-in official wheel payload, import origin, all V1
configs, the independent CLI smoke corpus, source-preserving target spans,
preview decisions, and the single write boundary. Later phases add broader
document, structural, golden, and performance suites; they should not be
collapsed into one plugin smoke test.

The native Jieba suite is a separate advanced-payload gate:
[`jieba-native-evaluation.md`](jieba-native-evaluation.md) records the pinned
upstream build. Run it with:

```sh
mise exec -- uv run python tools/differential_jieba_test.py \
  --corpus tests/fixtures/opencc_jieba_smoke.jsonl
```

The Python Binding and matching official CLI must be 100% equal. The GitHub
matrix runs this on each native Windows/macOS/Linux payload before assembly.
