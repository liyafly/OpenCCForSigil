# Testing

The local automated checks cover:

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

The test tree separates unit and integration behavior: native payload and OS
metadata, bounded diff reconstruction, thread ownership/cancellation, XML/NCX
metadata whitelists, grouped language decisions, rules/profile persistence,
locked outputs, pivot/quotation/punctuation transforms, history privacy, source
and settings drift, return-to-settings replanning, and commit verification.
Preview scale coverage includes 300,000-row model counts and bounded dialog
build, filtering, and bulk acceptance.
The source-only official CLI corpus includes all 16 configs plus ambiguity,
TW/HK vocabulary, mixed scripts, and Unicode preservation examples. Frozen
comparison outputs are explanatory; accepting all must reproduce the selected
pipeline exactly.

The native Jieba suite is a separate advanced-payload gate:
[`jieba-native-evaluation.md`](jieba-native-evaluation.md) records the pinned
upstream build. Run it with:

```sh
mise exec -- uv run python tools/differential_jieba_test.py \
  --corpus tests/fixtures/opencc_jieba_smoke.jsonl
```

For a release candidate, require the complete Fat Plugin matrix and validate
the archive after it is assembled:

```sh
mise exec -- uv run python tools/verify_vendor.py --require-runtimes
mise exec -- uv run python tools/build_plugin.py --require-runtimes \
  --output dist/OpenCCForSigil_release.zip
mise exec -- uv run python tools/validate_artifact.py --require-runtimes \
  dist/OpenCCForSigil_release.zip
```

The package builder fixes ZIP member order, timestamps, and executable modes.
`tests/integration/test_package.py` checks that two builds from the same tree
are byte-for-byte identical. The final archive validator recomputes each
payload tree hash from ZIP contents, so a successful pre-package manifest check
cannot hide a packaging omission or mutation.

The Python Binding and matching official CLI must be 100% equal. The GitHub
matrix runs this on each native Windows/macOS/Linux payload before assembly.
