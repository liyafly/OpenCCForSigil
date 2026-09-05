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

The official upstream native `opencc-jieba` plugin was evaluated separately.
See [`jieba-native-evaluation.md`](jieba-native-evaluation.md). It remains out
of the V1 payload and UI until every release target has a verified plugin,
resource, loader-path, license, and differential-test artifact.
