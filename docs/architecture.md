# Architecture

This repository implements the source-preserving conversion slice and the
official OpenCC Binding runtime boundary from the engineering specification.
The intended dependency direction is:

```text
Sigil plugin.py
    ↓
app/controller.py + app/session.py
    ↓
    core contracts ← document processors ← opencc_backend
    ↓
sigil adapter (the only commit boundary)
```

The UI will consume application view models later. It must not import
`opencc_backend`, document processors, or the Sigil `BookContainer` directly.
The backend will return strings and provenance only; it will not know about
EPUB structure, rules, or UI.

## Conversion workflow

The first interactive profile runs:

```text
SCAN → ANALYZE → PLAN → PREVIEW → APPLY TO STAGE → VERIFY → COMMIT
```

`TextTarget` carries absolute source spans from the lexical XHTML tokenizer.
`ConversionPlan` freezes OpenCC output, provenance, and the source SHA-256.
Preview decisions produce an accepted-only plan; staging applies those patches
to an in-memory copy; structural and planned-span verification must pass before
the adapter is allowed to call `bk.writefile()`.

The Preview UI supports `Accept this`, `Skip this`, `Accept all`, and `Skip
all`. The core API also supports bulk filters by file, category, risk, or rule
source, so future review modes can narrow a bulk decision without changing the
write boundary.

## Runtime boundaries

- OpenCC must be the pinned official `opencc` Python Binding loaded from
  `vendor/opencc/manifest.json`.
- V1 formally supports CPython 3.14.x with ABI `cp314`; Sigil bundled Python
  3.14.2 is the production baseline and patch versions are provenance only.
- RuntimeSelector verifies the exact CPython major/minor/OS/architecture/ABI
  payload tree before importing `opencc`; the checked-in build host payload is
  macOS arm64/cp314, and 3.14.2 and 3.14.7 select the same payload.
- Build/Release uses `tools/vendor_opencc.py` to fetch exact official wheels,
  verify SHA-256, extract unchanged payloads, and register config/data hashes.
- There is no system module, PATH CLI, user site-packages, pip, or network
  fallback.
- User data is stored outside the plugin installation directory.
- Logs are JSONL and default to metadata/short diagnostic fields, not whole
  book content.
