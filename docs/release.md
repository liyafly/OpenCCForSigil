# Release and artifact validation

Release packaging is split into two steps:

1. build and verify exact official OpenCC wheel payloads;
2. validate and package the shared Python plugin and manifest.

The exact official wheel inputs are recorded in
[`native_build/payload-lock.json`](../native_build/payload-lock.json). The lock
contains one CPython 3.14/cp314 wheel for each supported runtime and is checked
against the live PyPI metadata before extraction. A changed wheel URL, size, or
SHA-256 is a blocking error; the build never silently selects another release.

`tools/vendor_opencc.py` performs step 1. `tools/build_plugin.py` performs step
2 and invokes manifest/payload verification before packaging. It validates
`plugin.xml`, the code version, and the one-top-level-directory ZIP shape. No
unverified wheel payload is synthesized or copied.

The release job must also run `tools/differential_test.py` against an
independent official CLI from the same pinned OpenCC release. Any Python
Binding/CLI difference is blocking; golden candidates are review-only and are
never used to auto-accept changed conversion output.

When the advanced native Jieba payload is enabled, the release job must also
run `tools/differential_jieba_test.py`. Its plugin library, seven plugin config
files, Jieba resources, and manifest hashes are target-specific. No macOS
`.dylib` is copied into a Windows/Linux payload; each native runner builds its
own official plugin.

## GitHub Actions without local Windows/Linux environments

`.github/workflows/ci.yml` uses GitHub-hosted runners as the native build
matrix:

```text
ubuntu-latest  → linux-x86_64-cp314
macos-15       → macos-arm64-cp314
macos-15-intel → macos-x86_64-cp314
windows-latest → windows-x86_64-cp314
```

Each matrix job runs `tools/vendor_opencc.py`, manifest/payload verification,
`tools/build_opencc_jieba.py`, native plugin verification, Python Binding smoke
tests, and the independent official CLI plus native Jieba differential corpora
on its own native runner. It then exports only the target-tested payload
with `tools/export_verified_payload.py` and uploads that directory as a
workflow artifact.

Successful push and manual runs also cache the exported, target-tested payload
under a key derived from the wheel lock, manifest, and native build recipes.
The cache is an acceleration layer: a hit is merged and hash-verified before it
is used, while a miss performs the complete native build. Pull requests do not
restore this cache, so untrusted workflow input cannot supply a native binary.

The dependent `build-fat-plugin` job downloads all artifacts, merges them with
`tools/merge_verified_payloads.py --require-runtimes`, verifies every payload and provenance hash,
runs the Linux differential test, builds the Fat Plugin ZIP, validates its
licenses/notices, and uploads the final plugin plus specification bundle. A
payload marked `skipped-cross-platform` cannot enter the final artifact.

Release mode requires exactly these four runtime identities, with no missing or
extra payload: Linux x86_64, macOS arm64, macOS x86_64, and Windows x86_64,
all on CPython 3.14/cp314. `tools/build_plugin.py --require-runtimes` writes a
deterministic ZIP with fixed member order, timestamps, and permissions. The
same ZIP is then passed through `tools/validate_artifact.py --require-runtimes`,
which recomputes every payload tree and data hash from the archive itself.

To use it, push the branch or select **Actions → CI and Fat Plugin build → Run
workflow**. Download the artifact named
`OpenCCForSigil-fat-plugin-<commit>` from the successful run. No local
Windows/Linux installation is required; GitHub-hosted runner availability and
repository Actions-minute limits still apply.
