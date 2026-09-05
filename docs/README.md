# Specification index

`OpenCCForSigil_Spec_v1.4/` is the current stable normative specification.
It supersedes `OpenCCForSigil_Spec_v1.3/`, which is retained as the previous
stable baseline; v1.2 remains the earlier historical backend baseline.

For implementation work, load these three files from v1.4 together:

```text
OpenCCForSigil_Engineering_Spec.md
INVARIANTS.md
REVISION_NOTES.md
```

The v1.4 Production Backend is the vendored BYVoid/OpenCC official Python
Binding (`opencc.OpenCC`). The v1.2 direct `ctypes`/shared-library design is
historical only.

The official native `opencc-jieba` evaluation is recorded in
[`jieba-native-evaluation.md`](jieba-native-evaluation.md). In v1.4 it is a
manifest-detected advanced payload: the UI enables the official Jieba option
only after the selected target payload passes integrity and differential tests.
