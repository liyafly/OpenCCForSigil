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

The current implementation provides the allowlist, provenance model,
wheel/payload manifest, deterministic tree hash, exact runtime selector,
import-origin boundary, and a verified macOS arm64 / cp314 payload. A missing
payload entry is an error, not a reason to use a system OpenCC or to run pip.

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
