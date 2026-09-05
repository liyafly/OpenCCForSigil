# Release and artifact validation

Release packaging is split into two steps:

1. build and verify exact official OpenCC wheel payloads;
2. validate and package the shared Python plugin and manifest.

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
macos-14       → macos-arm64-cp314
macos-13       → macos-x86_64-cp314
windows-latest → windows-x86_64-cp314
```

Each matrix job runs `tools/vendor_opencc.py`, manifest/payload verification,
`tools/build_opencc_jieba.py`, native plugin verification, Python Binding smoke
tests, and the independent official CLI plus native Jieba differential corpora
on its own native runner. It then exports only the target-tested payload
with `tools/export_verified_payload.py` and uploads that directory as a
workflow artifact.

The dependent `build-fat-plugin` job downloads all artifacts, merges them with
`tools/merge_verified_payloads.py`, verifies every payload and provenance hash,
runs the Linux differential test, builds the Fat Plugin ZIP, validates its
licenses/notices, and uploads the final plugin plus specification bundle. A
payload marked `skipped-cross-platform` cannot enter the final artifact.

To use it, push the branch or select **Actions → CI and Fat Plugin build → Run
workflow**. Download the artifact named
`OpenCCForSigil-fat-plugin-<commit>` from the successful run. No local
Windows/Linux installation is required; GitHub-hosted runner availability and
repository Actions-minute limits still apply.
