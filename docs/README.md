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

v1.4 is the only retained versioned specification. The current backend and
package boundaries are described in [`native-backend.md`](native-backend.md)
and [`release.md`](release.md).

## Maintained guides

These guides describe current behavior and are kept up to date.

| Need | Document |
| --- | --- |
| Understand the dependency direction and conversion state machine | [`architecture.md`](architecture.md) |
| Inspect the official OpenCC Binding and payload boundary | [`native-backend.md`](native-backend.md) |
| Review the optional official native Jieba capability | [`jieba-native-evaluation.md`](jieba-native-evaluation.md) |
| Configure NCX, metadata, and language proposals | [`extended-document-conversion.md`](extended-document-conversion.md) |
| Manage profiles, rules, and rule tests | [`rules-and-profiles.md`](rules-and-profiles.md) |
| Define or review user rule behavior | [`rule-format.md`](rule-format.md); the installable ZIP also includes `OpenCCForSigil/resources/rule-guide.md` |
| Understand privacy-safe storage and logs | [`privacy.md`](privacy.md) |
| Run local and release validation | [`testing.md`](testing.md) |
| Build and publish plugin packages | [`release.md`](release.md) |
| Read the v0.2.12 release notes | [`releases/v0.2.12.md`](releases/v0.2.12.md) |
| Record an implementation/specification deviation | [`deviations.md`](deviations.md) |
| Read the project license and third-party license boundary | [`licensing.md`](licensing.md) |

## Historical records

These are dated reviews, plans, and acceptance records. They are kept as
evidence of what was decided and verified at the time and are not updated to
match current behavior; use the maintained guides above for that.

### Archived one-off records

| Record | Document |
| --- | --- |
| 2026-09-07 scoped UI design plan (partially implemented in v0.0.2-beta) | [`archive/ui-interaction-optimization-plan.md`](archive/ui-interaction-optimization-plan.md) |
| v0.0.2-beta UI acceptance record | [`archive/release-review-v0.0.2-beta.md`](archive/release-review-v0.0.2-beta.md) |
| 2026-09-08 review of the v0.0.1-beta → HEAD findings and Luna plan | [`archive/review-v001-to-head-luna-plan.md`](archive/review-v001-to-head-luna-plan.md) |
| 2026-09-08 progress, packaging, and license change review | [`archive/review-2026-09-08.md`](archive/review-2026-09-08.md) |
| 2026-09-08 patch performance measurements and follow-up status | [`archive/performance-interaction-followup.md`](archive/performance-interaction-followup.md) |

### Review rounds

Screenshot evidence (`*.png`) referenced by these records is no longer kept on
`main`. It is preserved at commit `c9b288e` and on the
`archive/review-evidence` branch; the JSON/log evidence and reproduction
scripts remain in place.

| Record | Document |
| --- | --- |
| 2026-09-23 UI, logic, and packaging review | [`reviews/2026-09-23/README.md`](reviews/2026-09-23/README.md) |
| 2026-09-24 fix and release plan | [`reviews/2026-09-24/README.md`](reviews/2026-09-24/README.md) |
| 2026-09-26 UI, rules, and regex review plan for Luna | [`reviews/2026-09-26/01-ui-rules-luna-plan.md`](reviews/2026-09-26/01-ui-rules-luna-plan.md) |
| 2026-09-27 preview optimizations, safety fixes, and features plan for Luna | [`reviews/2026-09-27/01-optimization-feature-luna-plan.md`](reviews/2026-09-27/01-optimization-feature-luna-plan.md) |
| 2026-09-27 implementation, test evidence, and acceptance limits for that plan | [`reviews/2026-09-27/02-implementation-results.md`](reviews/2026-09-27/02-implementation-results.md) |
| Post-v0.2.8 settings, preview, rules, profiles, and history UI workflow plan for Luna | [`reviews/2026-09-27/ui-workflow/01-luna-plan.md`](reviews/2026-09-27/ui-workflow/01-luna-plan.md) |
| 2026-09-28 interaction, performance, and rules findings with reproduction evidence | [`reviews/2026-09-28/README.md`](reviews/2026-09-28/README.md) |
| 2026-09-29 acceptance audit, remaining fixes, and simplification | [`reviews/2026-09-29/README.md`](reviews/2026-09-29/README.md) |
| 2026-09-30 acceptance audit and post-v0.2.11 fixes | [`reviews/2026-09-30/README.md`](reviews/2026-09-30/README.md) |

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

## Versioned specification

The versioned specification directory is kept so an implementation or release
can be compared with its recorded baseline. Historical review material is
linked from the tables above instead of being duplicated in several documents.
