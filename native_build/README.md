# Official OpenCC wheel payload build

`tools/vendor_opencc.py` is the reproducible Build/Release recipe described in
the engineering specification. It inspects the pinned BYVoid/OpenCC
`ver.1.4.2` release, selects official PyPI wheels for exact CPython/OS/
architecture combinations, verifies wheel hashes, extracts unchanged payloads,
runs import/config/smoke tests where the native payload can run, and writes entries into
`plugin/OpenCCForSigil/vendor/opencc/manifest.json`.

V1's Python matrix is CPython 3.14.x / `cp314`; Sigil bundled Python 3.14.2
is the production baseline and 3.14.7 is the development/CI baseline. Patch
versions are provenance-only.

The package intentionally does not download, install, build, or copy OpenCC at
runtime; all wheel retrieval belongs to Build/Release. Use
`--wheel-name ... --skip-import-test` only for a deliberate cross-platform
artifact build, followed by verification on the target runtime before release.
