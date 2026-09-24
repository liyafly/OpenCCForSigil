# Architecture

This repository implements the source-preserving V1 conversion workflow and the
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

UI dialogs receive immutable plans and settings services. Backend config
identifiers may be displayed by the UI; native conversion remains behind the
backend service. Dialogs never write BookContainer resources. The backend
returns strings and provenance and knows nothing about EPUB structure or UI.

## Conversion workflow

The controller runs an explicit standard-config chooser (for
example `s2t`, `t2s`, `tw2s`, or `tw2sp`) before the workflow:

```text
SCAN → ANALYZE → PLAN → PREVIEW → APPLY TO STAGE → VERIFY → COMMIT
```

`TextTarget` carries absolute source spans from the lexical XHTML tokenizer.
`ConversionPlan` freezes OpenCC output, provenance, and the source SHA-256.
Preview decisions produce an accepted-only plan; staging applies those patches
to an in-memory copy; structural and planned-span verification must pass before
the adapter is allowed to call `bk.writefile()`.

The Preview UI supports `Accept this`, `Skip this`, `Accept all`, and `Skip
all`. The selected config is saved as the next default, but every run still
shows the explicit choice. When the selected payload advertises a verified
official native plugin, the config dialog enables an advanced Jieba checkbox
that maps a standard config to its concrete `*_jieba` config. It is not a
generic segmentation selector, and an unavailable/invalid payload fails
closed. The core API also supports bulk filters by file, category, risk, or
rule source. The UI exposes file/category/risk filters. Language-tag groups
remain indivisible even when some members are hidden by a filter.

## Runtime boundaries

- OpenCC must be the pinned official `opencc` Python Binding loaded from
  `vendor/opencc/manifest.json`.
- The Fat Plugin supports five CPython 3.14.x / `cp314` runtimes. A separate
  Linux x86_64 package supports CPython 3.12 / `cp312`; Sigil bundled Python
  3.14.2 remains the primary production baseline.
- RuntimeSelector verifies the exact CPython major/minor/OS/architecture/ABI
  payload tree before importing `opencc`; the checked-in build host payload is
  macOS arm64/cp314, and 3.14.2 and 3.14.7 select the same payload.
- RuntimeSelector verifies optional `opencc-jieba` library/config/resource
  hashes and sets plugin/data paths only inside the selected payload; it never
  inherits a system plugin path.
- Build/Release uses `tools/vendor_opencc.py` to fetch exact official wheels,
  verify SHA-256, extract unchanged payloads, and register config/data hashes.
- There is no system module, PATH CLI, user site-packages, pip, or network
  fallback.
- User data is stored outside the plugin installation directory.
- Logs are JSONL and default to metadata/short diagnostic fields, not whole
  book content.

## Frozen settings and worker ownership

The controller reads Sigil sources on the main thread. One worker constructs,
uses, and closes its own backend while immutable source/request data and queued
progress cross the thread boundary. Returning to settings discards old plans
and decisions. Cancellation discards all analysis before any commit.

Rules lock their spans before the unlocked pipeline runs. Exact/protect output
bypasses every subsequent transform. OpenCC comparisons independently receive
the original segment and only explain the frozen result; they never replace
it during Apply. Full-diff exports use in-memory data and require opt-in.

A final source hash check covers every staged resource before the first write.
The verified staged-file tuple and profile/rule storage revision must still
match. A host write failure can be partial; its committed IDs are reported
honestly, without claiming rollback or an undo transaction.
