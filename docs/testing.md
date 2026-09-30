# Testing

The local automated checks cover:

```text
pytest unit storage/logging = PASS
plugin package metadata = PASS
official vendored payload manifest/hash = PASS
official CLI/Python Binding differential smoke = 100% equality
source-preserving plan/stage/verify integration = PASS
preview acceptance/rejection integration = PASS
missing BookContainer text API = localized error (error.book_api_unavailable) with zero writes
```

Run locally with the pinned environment:

```sh
mise install
mise exec -- uv sync --locked
make check
```

The test tree separates unit and integration behavior: native payload and OS
metadata, bounded diff reconstruction, thread ownership/cancellation, XML/NCX
metadata whitelists, grouped language decisions, literal and regex rules,
pre/post replacement mapping, rule/profile persistence, locked outputs,
pivot/quotation/punctuation transforms, history privacy, source and settings
drift, return-to-settings replanning, and commit verification.
Preview scale coverage includes 300,000-row model counts and bounded dialog
build, filtering, and bulk acceptance.
The source-only official CLI corpus includes all 16 configs plus ambiguity,
TW/HK vocabulary, mixed scripts, and Unicode preservation examples. Frozen
comparison outputs are explanatory; accepting all must reproduce the selected
pipeline exactly.

The UI workflow has real PySide6/offscreen interaction probes for the merged
settings summary, rules and profile editors, preview controls, bulk-decision
scopes, and searchable conversion history. Run the consolidated matrix with:

```sh
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-27/ui-workflow/scripts/check_ui_acceptance.py \
  --output /tmp/opencc-ui-acceptance --verify --width 960 --height 640
```

The `--verify` run exercises English, Simplified Chinese, and Traditional
Chinese. The committed review evidence also records 1280×800 requested layout,
125%, and 200% Qt scale-factor runs. Those scale-factor runs use Qt's offscreen
platform; their synthetic logical screen sizes do not establish physical
high-DPI or multi-monitor behavior, and they do not replace testing the plugin
inside Sigil. `make check` includes the 300,000-entry bulk-planning operation
count regression. A separate benchmark records median planner time and
incremental memory for 10,000, 100,000, and 300,000 synthetic entries.

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
mise exec -- uv run python tools/merge_regex_payloads.py \
  --artifact-root native_build/artifacts --require-runtimes
mise exec -- uv run python tools/verify_vendor.py --require-runtimes
mise exec -- uv run python tools/verify_regex_vendor.py --require-runtimes
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

Regex archive validation matches its runtime identities to the OpenCC package,
checks file and tree hashes against the locked PyPI wheel records, verifies
native extension architecture, and rejects unmanifested payload files. Package
smoke imports the target-specific module and exercises Unicode captures and
the timeout argument.

The Python Binding and matching official CLI must be 100% equal. The GitHub
matrix runs this on each native Windows/macOS/Linux payload before assembly.
