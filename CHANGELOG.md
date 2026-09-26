# Changelog

## 0.2.5 - 2026-09-26

### Added

- Add rule semantic version 2 with separate protect, final wording, pre-replacement,
  and post-replacement actions, plus literal and regular-expression matching.
- Bundle a pinned regular-expression engine for all six supported runtime targets,
  with offline loading, validated replacement templates, and reusable rule templates.

### Changed

- Run sandbox previews and book conversion through the same frozen rules and
  conversion stages, then map changes back to original XHTML offsets.
- Apply each replacement stage once, group dependent edits, and keep failed rule
  analysis from producing a partial writeback plan.

### Fixed

- Bound regex runtime, hit counts, and replacement output, and reject zero-length
  matches and invalid group references before conversion.
- Keep signature protection scoped to explicit markers such as `◎著`; ordinary
  occurrences of `著` continue through OpenCC.

## 0.2.2 - 2026-09-25

### Fixed

- Preserve unbracketed and commonly spaced `◎著` author-credit markers in
  `tw2sp` and `tw2sp_jieba`, while continuing to convert ordinary `慰藉著` to
  `慰藉着`.
- Explain why a bare `著` cannot be protected globally without changing
  ordinary prose, with examples in the localized rules page and package guide.

## 0.2.1 - 2026-09-25

### Fixed

- Preserve the bracketed `◎【著】` author-credit marker in `tw2sp` and
  `tw2sp_jieba`.

### Added

- Add localized rule-writing help to the Rules / sandbox page and a
  multilingual rule guide to the installable package.

## 0.2.0 - 2026-09-24

### Fixed

- Keep each OpenCC phrase replacement together in the preview so a partial
  acceptance cannot create text that is neither the source nor the conversion.
- Preserve source spelling and offsets while scanning raw XHTML. Leave comments,
  CDATA, script/style text, namespaced MathML/SVG elements, ruby annotations,
  and foreign-language spans outside conversion as specified.
- Verify that writes change only planned ranges and leave protected content
  intact; report malformed XHTML, NCX, and metadata with accurate source
  locations without failing unrelated files.
- Make protection rules take precedence when they overlap earlier exact rules,
  assign safe IDs to imported rules, and warn before lossy rule exports.
- Preserve user settings, profile state, and rule sets across dialogs and
  upgrades. Use unique temporary preference files and avoid replacing newer
  schemas or concurrent preference updates.
- Keep successful book writes successful if later progress or history reporting
  fails, and show actionable diagnostics for prewrite and export failures.
- Keep the optional Jieba probe out of standard conversion preflight, cancel
  background probing cleanly, and retain the saved direction when reopening
  conversion settings.

### Changed

- Make preview decisions responsive on large books by formatting rows lazily,
  updating only changed rows, and avoiding repeated conversions, alignments,
  rule overlays, and payload-tree hashing.
- Refine conversion, profile, rule, history, progress, and result dialogs with
  clearer navigation, localized controls, theme-aware colors, accessible
  shortcuts, stable layouts, and explicit discard/error feedback.
- Build native payloads on matching hosted runners and test Jieba output across
  platforms before assembling installable packages.

### Added

- Add a separate Linux x86_64 CPython 3.12/cp312 package for compatible Sigil
  builds, including Ubuntu 24.04; keep the Fat Plugin on its five cp314 runtimes.
- Publish seven installable ZIPs with a SHA-256 manifest, test all six platform
  runtimes, pin GitHub Actions to commit SHAs, and generate GitHub artifact
  attestations for every ZIP and the checksum manifest.
- Add diagnostics and regressions for mixed or unbalanced quote changes,
  skipped XHTML source lines, report counts, and large preview models.

## 0.1.0 - 2026-09-22

- Connect exact/protect rules, profile storage, rule import/export, a text
  sandbox, and official comparative inspection to the conversion settings.
- Add optional quotation and horizontal punctuation transforms, mixed-script
  diagnostics, explicit high-risk pivot, and numeric Han reference decoding.
- Add spine selection, file/category/risk preview filters, grouped decisions,
  return to settings, and the persisted Checkpoint reminder preference.
- Add private conversion history and Markdown/JSON reports. Full diff remains
  in memory unless explicitly exported; verify settings and source snapshots
  again before committing the exact verified staged files.
- Extend TW/HK, ambiguity, and Unicode CLI differential coverage to 28 cases.

- Analyze frozen document sources with a worker-owned OpenCC instance while
  the main thread handles progress, cancellation, and every Sigil API call.
  Cancellation discards the plan and never enters the write boundary.

- Add opt-in NCX labels and whitelisted OPF metadata conversion, plus grouped
  Chinese language-tag proposals. Preserve XML source formatting and require
  preview, structural verification, and source hash checks before any write.

- Build native Jieba for macOS 13 and Ubuntu 22.04/GCC 11; validate binary
  architecture and macOS/GLIBC/GLIBCXX requirements in both the source tree
  and the final ZIP. Pin the Windows build runner to Windows Server 2022.

- Bound long-text preview alignment work without splitting OpenCC conversion
  input. Ambiguous large regions are shown as one exact replacement; accepting
  all changes still reproduces the official result exactly.

- Separate standard conversion preflight from optional native Jieba probing.
  A verified Jieba library that cannot load on the host disables the advanced
  option and reports its reason without blocking standard conversion. A
  selected Jieba configuration never falls back to another algorithm, and
  payload/hash/provenance failures remain blocking (spec §4.4.1, §4.5.5).

- Release validation covers CI tests, the four-platform native binary baseline,
  and a controlled Qt smoke test on the local host. Real Sigil install,
  apply, save, and reopen acceptance across all four platforms remains open;
  previously noted minor UI polish is deferred to a later release.

## 0.0.3-beta

- Assemble source patches with a single join, update only the selected preview
  row for individual decisions, and finalize accepted plans once in the workflow.
- Report analyzed, written, skipped, unchanged, and unwritten files with
  localized singular/plural wording while preserving the existing summary
  fields and their subset semantics.
- Validate bundled runtime resources, all required i18n keys, payload provenance,
  streaming payload hashes, and the four-runtime Fat Plugin release contract;
  reject bytecode and incomplete archives.
- Close the official OpenCC native runfiles fallback, verify import origins, and
  ship the pinned native dependency notices for the packaged payload.
- Show progress by explicit analysis, planning, staging, and verification
  phases with reset boundaries, operation-complete counts, safe cancellation
  checks, and guarded preview re-entry.
- Release CI now publishes only the installable Fat Plugin ZIP; normative
  documentation stays source-controlled and is no longer built or uploaded as
  a second ZIP. Consolidated maintainer documentation and the Apache-2.0
  project/package notice boundary remain in the repository.

## 0.0.2-beta

- Closed the scoped conversion UI review findings: every text-capable host now
  requires an explicit XHTML target selection, with metadata-only inventory,
  empty-selection protection, localized three-language controls, and accurate
  counts.
- Added cancellation checkpoints around progress callbacks, retained the Qt
  application owner, and ran repository and differential tests on every CI
  platform even when native payloads come from cache.
- Completed no-change and all-skipped previews without writes, and report
  partial write failures with the files already handed to Sigil.
- Enforced verified source-only imports for official OpenCC modules so unchecked
  cached bytecode cannot bypass payload integrity checks.

## 0.0.1-beta

- First public beta release of the source-preserving Sigil conversion plugin.
- Includes the official BYVoid/OpenCC Python Binding and target-built native
  Jieba payloads in the GitHub Actions Fat Plugin artifact.
- Supports CPython 3.14.x/cp314 with Sigil bundled Python 3.14.2 as the
  production baseline and 3.14.7 as the development/CI baseline.

## Specification v1.3

- Locked the sole production backend to the vendored BYVoid/OpenCC official Python Binding.
- Added exact CPython ABI/OS/architecture payload selection, import-origin verification, and wheel provenance requirements.
- Unified the V1 runtime policy at CPython 3.14.x/cp314: Sigil 3.14.2 is the production baseline and mise uses 3.14.7 for development/CI only.
- Preserved source-span-safe XHTML mutation, preview/transaction boundaries, rules overlays, provenance, golden/CLI differential tests, and regional explicitness.

## Historical Phase 0 plugin skeleton

- Added the Phase 0 plugin skeleton.
- Pinned the local Python and development toolchain with mise.
- Added the state-machine, storage, JSONL logging, official OpenCC payload manifest, and package boundaries.
- Added a no-op Sigil entry point that never mutates the open book.
