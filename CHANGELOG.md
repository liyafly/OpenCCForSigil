# Changelog

## Unreleased

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

## 0.1.0

- Added the Phase 0 plugin skeleton.
- Pinned the local Python and development toolchain with mise.
- Added the state-machine, storage, JSONL logging, official OpenCC payload manifest, and package boundaries.
- Added a no-op Sigil entry point that never mutates the open book.
