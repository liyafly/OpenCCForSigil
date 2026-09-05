# Specification index

`OpenCCForSigil_Spec_v1.3/` is the current stable normative specification.
It supersedes `OpenCCForSigil_Spec_v1.2/`, which is retained as a historical
baseline for the backend architecture revision.

For implementation work, load these three files from v1.3 together:

```text
OpenCCForSigil_Engineering_Spec.md
INVARIANTS.md
REVISION_NOTES.md
```

The v1.3 Production Backend is the vendored BYVoid/OpenCC official Python
Binding (`opencc.OpenCC`). The v1.2 direct `ctypes`/shared-library design is
historical only.

The official native `opencc-jieba` evaluation is recorded in
[`jieba-native-evaluation.md`](jieba-native-evaluation.md). It is not a V1
runtime dependency or UI option.
