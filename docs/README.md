# OpenCCForSigil documentation

This is the single documentation entry point. Product users need the root
[`README.md`](../README.md) and an installable plugin ZIP. Maintainers and
contributors can use the guides below without downloading a separate
documentation archive.

## Current source of truth

[`OpenCCForSigil_Spec_v1.4/`](OpenCCForSigil_Spec_v1.4/) is the current stable
normative specification. For implementation work, read these three files
together:

```text
OpenCCForSigil_Engineering_Spec.md
INVARIANTS.md
REVISION_NOTES.md
```

It supersedes [`OpenCCForSigil_Spec_v1.3/`](OpenCCForSigil_Spec_v1.3/), which
is retained as the previous stable baseline. v1.2 remains the historical
backend architecture baseline. The v1.4 production backend is the vendored
BYVoid/OpenCC official Python Binding (`opencc.OpenCC`); the v1.2 direct
`ctypes`/shared-library design is historical only.

## Choose a guide

| Need | Document |
| --- | --- |
| Understand the dependency direction and conversion state machine | [`architecture.md`](architecture.md) |
| Inspect the official OpenCC Binding and payload boundary | [`native-backend.md`](native-backend.md) |
| Review the optional official native Jieba capability | [`jieba-native-evaluation.md`](jieba-native-evaluation.md) |
| Configure NCX, metadata, and language proposals | [`extended-document-conversion.md`](extended-document-conversion.md) |
| Manage profiles, rules, sandbox, and inspector | [`rules-and-profiles.md`](rules-and-profiles.md) |
| Define or review user rule behavior | [`rule-format.md`](rule-format.md); the installable ZIP also includes `OpenCCForSigil/resources/rule-guide.md` |
| Understand privacy-safe storage and logs | [`privacy.md`](privacy.md) |
| Run local and release validation | [`testing.md`](testing.md) |
| Build and publish plugin packages | [`release.md`](release.md) |
| Read the v0.2.8 release notes | [`releases/v0.2.8.md`](releases/v0.2.8.md) |
| Record an implementation/specification deviation | [`deviations.md`](deviations.md) |
| Read the project license and third-party license boundary | [`licensing.md`](licensing.md) |
| Review the progress, packaging, and license changes | [`review-2026-09-08.md`](review-2026-09-08.md) |
| Reproduce patch performance measurements and review remaining UI work | [`performance-interaction-followup.md`](performance-interaction-followup.md) |
| Review the v0.0.2-beta UI acceptance record | [`release-review-v0.0.2-beta.md`](release-review-v0.0.2-beta.md) |
| Read the scoped UI design decisions | [`ui-interaction-optimization-plan.md`](ui-interaction-optimization-plan.md) |
| Reproduce the 2026-09-23 UI, logic, and packaging review | [`reviews/2026-09-23/README.md`](reviews/2026-09-23/README.md) |
| Implement and verify the 2026-09-26 UI, rules, and regex review with Luna | [`reviews/2026-09-26/01-ui-rules-luna-plan.md`](reviews/2026-09-26/01-ui-rules-luna-plan.md) |
| Plan the next preview optimizations, safety fixes, and features for Luna | [`reviews/2026-09-27/01-optimization-feature-luna-plan.md`](reviews/2026-09-27/01-optimization-feature-luna-plan.md) |
| Review the implementation, test evidence, and acceptance limits for that plan | [`reviews/2026-09-27/02-implementation-results.md`](reviews/2026-09-27/02-implementation-results.md) |

## Release artifacts

The release source of truth is [`../tools/runtime_matrix.py`](../tools/runtime_matrix.py)
and [`release.md`](release.md). CI uploads one Actions artifact named
`OpenCCForSigil-packages-${{ github.sha }}` containing the Fat Plugin, six
platform ZIPs, and `SHA256SUMS.txt` (eight assets total). The Fat Plugin has
five CPython 3.14/cp314 runtimes; the separate Linux x86_64/cp312 target is
available only in its platform ZIP. A tagged release validates seven plugin
ZIPs and the checksum manifest, then publishes all eight assets after the six
platform-package smoke jobs and attestation complete. Older releases may have
fewer assets.
GitHub may also expose automatically generated source archives for the tag;
those are source snapshots rather than installable plugin assets. Each product
ZIP has the single top-level `OpenCCForSigil/` directory required by Sigil.

Normative specifications, testing guidance, and release notes remain in this
repository under `docs/`. They are not copied into `dist/` or generated as a
documentation ZIP.

## Historical and implementation notes

The versioned specification directories are kept so an implementation or
release can be compared with its recorded baseline. The short operational
guides above are the maintained entry points; historical review material is
linked explicitly instead of being duplicated in several documents.
