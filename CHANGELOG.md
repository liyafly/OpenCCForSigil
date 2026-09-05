# Changelog

## Specification v1.3

- Locked the sole production backend to the vendored BYVoid/OpenCC official Python Binding.
- Added exact CPython ABI/OS/architecture payload selection, import-origin verification, and wheel provenance requirements.
- Unified the V1 runtime policy at CPython 3.14.x/cp314: Sigil 3.14.2 is the production baseline and mise uses 3.14.7 for development/CI only.
- Preserved source-span-safe XHTML mutation, preview/transaction boundaries, rules overlays, provenance, golden/CLI differential tests, and regional explicitness.

## 0.1.0

- Added the Phase 0 plugin skeleton.
- Pinned the local Python and development toolchain with mise.
- Added the state-machine, storage, JSONL logging, official OpenCC payload manifest, and package boundaries.
- Added a no-op Sigil entry point that never mutates the open book.
