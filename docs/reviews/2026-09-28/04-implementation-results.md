# 2026-09-28 implementation results

## Baseline

- Commit: `c14701f9c17e1124523e1d3b74735c366a683ab7` (`main`, version `0.2.8`), clean before importing this review package.
- `make check`: passed; Ruff passed, **682 passed, 1 skipped**, vendor manifest passed, OpenCC CLI differential passed (28 cases), Jieba differential passed (10 cases), package metadata check passed (`0.2.8`).
- Reproduction scripts confirmed the reported regex budget overflow, precedence mismatch, hidden cross-ruleset conflict, two-column TSV rejection, wildcard default direction, accidental ruleset inclusion, wrong filtered-row inspection, and fatal zero-width match.
- Real Qt probes: filter Enter closed the merged dialog with one or two selected files; at 960×640 the rules table showed two rows and the add button was outside the viewport. Preview decision benchmarks recorded 162.9 ms for an undecided-filter decision and 141.9 ms for a file decision; the 480-paragraph diagnostic probe recorded 20.775 s on this run.
- A full four-mode synthetic-book pipeline baseline was stopped after more than three minutes of single-core work; the supplied baseline JSON is retained unchanged under `evidence/perf/`.
- Sigil host acceptance: **Not verified**.

## Implementation batches

| Batch | Items | Implementation commit(s) | `make check` | 960×640 Qt acceptance | Benchmarks and digest | Remaining work / host |
| --- | --- | --- | --- | --- | --- | --- |

