# Official OpenCC wheel payload build

Phase 1 will add the reproducible Build/Release recipe described in the
engineering specification. It must inspect the pinned BYVoid/OpenCC
`ver.1.4.2` release, select official PyPI wheels for exact CPython/OS/
architecture combinations, verify wheel hashes, extract unchanged payloads,
run import/config/differential smoke tests, and write entries into
`plugin/OpenCCForSigil/vendor/opencc/manifest.json`.

V1's Python matrix is CPython 3.14.x / `cp314`; Sigil bundled Python 3.14.2
is the production baseline and 3.14.7 is the development/CI baseline. Patch
versions are provenance-only.

The Phase 0 package intentionally does not download, install, build, or copy
OpenCC at runtime; all wheel retrieval belongs to Build/Release.
