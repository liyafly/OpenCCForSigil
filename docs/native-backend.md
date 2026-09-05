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

Phase 0 provides the allowlist, provenance model, wheel/payload manifest
schema, tree-hash helper, exact runtime selector, and import-origin boundary.
It intentionally does not ship a wheel payload. A missing payload entry is an
error, not a reason to use a system OpenCC or to run pip.

Phase 1 must populate the manifest only after official wheel hash validation,
clean-process import/origin checks, config-load smoke tests, and canonical CLI
differential tests have passed. The package's native extension remains an
official wheel payload; OpenCCForSigil does not load it with ctypes or manage
its C/C++ lifetime directly.
