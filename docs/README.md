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
| Define or review user rule behavior | [`rule-format.md`](rule-format.md) |
| Understand privacy-safe storage and logs | [`privacy.md`](privacy.md) |
| Run local and release validation | [`testing.md`](testing.md) |
| Build and publish the Fat Plugin | [`release.md`](release.md) |
| Record an implementation/specification deviation | [`deviations.md`](deviations.md) |
| Read the project license and third-party license boundary | [`licensing.md`](licensing.md) |
| Review the progress, packaging, and license changes | [`review-2026-09-08.md`](review-2026-09-08.md) |
| Reproduce patch performance measurements and review remaining UI work | [`performance-interaction-followup.md`](performance-interaction-followup.md) |
| Review the v0.0.2-beta UI acceptance record | [`release-review-v0.0.2-beta.md`](release-review-v0.0.2-beta.md) |
| Read the scoped UI design decisions | [`ui-interaction-optimization-plan.md`](ui-interaction-optimization-plan.md) |

## Release artifacts

For future workflow runs, CI uploads one Actions artifact named
`OpenCCForSigil-fat-plugin-${{ github.sha }}` containing
`OpenCCForSigil_${{ github.sha }}.zip`. A tagged release verifies that exact
commit-named ZIP, renames it to `OpenCCForSigil_<version>.zip`, and uploads that
file as the release's one product asset. GitHub may also expose automatically
generated source archives for the tag; those are source snapshots rather than
installable plugin assets. The product ZIP has the single top-level
`OpenCCForSigil/` directory required by Sigil.

Normative specifications, testing guidance, and release notes remain in this
repository under `docs/`. They are not copied into `dist/` or generated as a
documentation ZIP.

## Historical and implementation notes

The versioned specification directories are kept so an implementation or
release can be compared with its recorded baseline. The short operational
guides above are the maintained entry points; historical review material is
linked explicitly instead of being duplicated in several documents.
