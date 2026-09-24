# Official Python Binding backend plan

The only production backend is the BYVoid/OpenCC official Python Binding
distribution `opencc` version `1.4.2`. The source reference is checked out at:

```text
../OpenCCForSigil-References/OpenCC
```

V1 formally supports CPython 3.14.x with wheel ABI `cp314`. The current Sigil
bundled Python 3.14.2 is the production baseline; Python 3.14.7 is used only
for mise development/CI. Patch versions are recorded in provenance and do not
participate in payload selection.

Standard startup preflight checks standard conversions and the selected
configuration. Optional Jieba load tests are performed once per backend when
enumerating available configurations. If the verified optional library cannot
load, standard conversion remains available and the UI/log reports the cause;
an explicitly selected Jieba configuration still fails rather than changing
its algorithm. Payload hash and provenance errors remain blocking. The full
`self_test()` continues to include the optional capability for diagnostics;
startup uses `self_test(include_optional=False)` (spec §4.4.1 and §4.5.5).

The current implementation provides the allowlist, provenance model,
wheel/payload manifest, deterministic tree hash, exact runtime selector,
import-origin boundary, and a verified macOS arm64 / cp314 payload. A missing
payload entry is an error, not a reason to use a system OpenCC or to run pip.

Within one process, the runtime selector caches a verified payload-tree digest
by absolute root and the sorted `(relative path, size, mtime_ns)` signature of
its files. The first check hashes the full tree; loader checks reuse that digest
while the signature is unchanged, and a size or modification-time change causes
a fresh hash. This saves repeated reads of the 24 MB payload. It assumes payload
files do not change bytes while preserving both size and modification time.
Manifest-listed native plugin files still receive their individual SHA-256
checks on each backend selection.

Additional Fat Plugin payloads must be added only after official wheel hash
validation, clean-process import/origin checks on the target runtime,
config-load smoke tests, and canonical CLI differential tests have passed. The
package's native extension remains an official wheel payload; OpenCCForSigil
does not load it with ctypes or manage its C/C++ lifetime directly.

The official upstream native `opencc-jieba` plugin is now a detectable advanced
payload. See [`jieba-native-evaluation.md`](jieba-native-evaluation.md). The
macOS arm64 payload includes the verified plugin; Windows, Linux, and macOS
x86_64 are built independently by the GitHub Actions native matrix before
entering the Fat Plugin. The UI never offers a generic segmentation selector.

The plugin is the official BYVoid/OpenCC C++ plugin, not a Python Jieba
rewrite. It is selected by official plugin-backed configs such as
`s2twp_jieba`, and its library/resources are loaded only from the exact
manifest-approved payload.
