# v0.0.2-beta release review

This release closes the safety findings from the first interactive UI review.

The scope dialog is now mandatory for every text-capable BookContainer. Hosts
without `selected_iter()` start with no checked files, and a missing or empty
selection cannot widen into an all-XHTML conversion. Scope inventory and
selection use manifest metadata only; the workflow reads and writes only the
frozen target IDs. The dialog reports ignored non-XHTML Book Browser entries,
uses full relative paths, refreshes counts after each checkbox change, shows an
accurate all-XHTML count, and disables analysis for empty or invalid choices.

The language picker is available before the conversion direction dialog, so a
first launch can read the direction controls in the chosen language. All new
messages, including exact-one errors, cancellation, skipped changes, success,
and partial write failures, are present in the three shipped catalogs. Invalid
`ui` preference values are normalized to an empty mapping while valid sibling
keys are preserved.

Preview Apply stays disabled while any change is undecided. Per-file and global
bulk actions explicitly overwrite earlier decisions when the user chooses them
again; the core API keeps its existing undecided-only default for callers that
do not opt into overwrite behavior. A plan with no changes or with every change
skipped completes without a `writefile` call and reports the outcome. The
adapter records the files handed to Sigil before a later write failure, and the
session summary reports the committed IDs and failed target instead of claiming
that nothing was written.

Progress cancellation is checked before and after each progress callback and
after the final file operation, preventing a last-file cancel from reaching
preview. A single process-level QApplication reference is retained for the
whole invocation. CI keeps its native payload cache while running lint,
pytest, and both differential suites on every platform for the current commit.

The following larger interactions remain outside this small release fix: a
grouped file tree with per-file preview summaries, a return-to-settings flow
that re-plans in the same invocation, cancellation controls during staging and
verification, and a full cross-platform real-reader acceptance matrix. The
current preview still presents a flat change list, and real Sigil save behavior
must be checked during host acceptance.

Validation on 2026-09-07 also exercised the real Sigil bundled
Python 3.14.2/PySide6 Cocoa runtime with a controlled two-file BookContainer.
The scope and direction dialogs, preview decisions, Apply, and result dialog
completed end to end with status 0. Selecting file B produced reads for B only
(the analysis read and the source-hash check), one B write, no A access, and
the protected script text remained unchanged. This smoke used a controlled
fixture and did not modify a user EPUB; it is host UI evidence rather than a
cross-platform reader acceptance result.
