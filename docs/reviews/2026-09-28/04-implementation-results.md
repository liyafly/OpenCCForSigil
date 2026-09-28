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
| 1 | RULE-10 | `8699302` | PASS: 684 passed, 1 skipped; vendor, OpenCC/Jieba differential, and package checks passed | PASS: `check_ui_acceptance.py --verify`; RULE-10 real Qt probe defaults to `s2t` and does not apply the rule to `t2s` | Existing wildcard rules remain `*`; no conversion output change outside the direction boundary | Complete; Sigil host **Not verified** |
| 2 | RULE-01, PERF-04 | `691f1e1` | PASS: 689 passed, 1 skipped; vendor, OpenCC (28 cases), Jieba (10 cases), and package checks passed | PASS: `check_ui_acceptance.py --verify` | RULE-01: 600 matches across 60 files planned; PERF-04: 200 files 10.59 s, 400 files 21.15 s, ratio 2.00 (limit 2.2); 19 regex tests passed | Complete; Sigil host **Not verified** |
| 3 | UXS-02, UXS-01 | `c456868`, `a340d3b` | PASS: 691 passed, 1 skipped; vendor manifest, OpenCC (28 cases), Jieba (10 cases), and package metadata checks passed (`0.2.8`) | PASS: `check_ui_acceptance.py --verify --width 960 --height 640`; merged-dialog real Qt probe passed in all three languages | UXS-02: filter Enter keeps the dialog open, leaves scope unaccepted, and focuses the first visible result for 0/1/2 selections; UXS-01: direction control moved above tabs, title and Analyze label retranslate together, direction changes refresh the summary; 25 focused tests passed | Complete; Sigil host **Not verified** |
