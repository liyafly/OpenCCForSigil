# Architecture

This repository implements the Phase 0 skeleton from the engineering
specification. The intended dependency direction is:

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

## Phase 0 behavior

The controller runs `SCANNING → ANALYZING → PLANNED → COMPLETED` as a safe
no-op. This makes installation and package smoke tests possible while keeping
`bk.writefile()` unreachable. The full Preview → Stage → Verify → Commit path
is represented in the state machine and will be enabled only after the
document and official binding payload phases are complete.

## Runtime boundaries

- OpenCC must be the pinned official `opencc` Python Binding loaded from
  `vendor/opencc/manifest.json`.
- V1 formally supports CPython 3.14.x with ABI `cp314`; Sigil bundled Python
  3.14.2 is the production baseline and patch versions are provenance only.
- RuntimeSelector verifies the exact CPython major/minor/OS/architecture/ABI
  payload tree before importing `opencc`; 3.14.2 and 3.14.7 select the same
  payload.
- There is no system module, PATH CLI, user site-packages, pip, or network
  fallback.
- User data is stored outside the plugin installation directory.
- Logs are JSONL and default to metadata/short diagnostic fields, not whole
  book content.
