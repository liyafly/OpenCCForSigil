# 2026-09-30 implementation results

## Baseline

- Base commit: `3107f270fd79f86bb22925fd5584fdfeb1ef819b`, on `main`; package version `0.2.11`.
- Supplied audit baseline: `make check` **861 passed, 1 skipped**; real-Qt acceptance **13/13 PASS**. Sigil-host acceptance for v0.2.11: **Not verified**.
- The review bundle and frozen reproduction evidence were added in `5c8f368` and pushed. A recursive comparison confirmed the checked-in `evidence/` bytes match the supplied archive. No earlier signed evidence was edited.
- Baseline reproductions match `evidence/rules/` and `evidence/tools/check_entrypoints.out`: FU-01 changed `*` to `s2t` after the first update; FU-02 raised `StopIteration` after deleting renamed `default`; FU-03 produced no numeric-reference diagnostic; FU-04 listed the final result twice; the eight-tool entrypoint check reported the supplied failures.

## Batch 1 — FU-01, FU-02, FU-04

Commits: `e1d04e3`, `64caa51`, `78e3533`; pushed together after both batch gates passed.

- Each new product regression was run red before its code change. FU-02's disk persistence guard passed before and after the fix.
- Focused gates: FU-01 **134 passed, 1 skipped**; FU-02 **123 passed, 1 skipped**; FU-04 **87 passed, 1 skipped**.
- Reproduction outputs:

  ```text
  after 1st update: rule = * | combo = * | editing = w
  after 2nd update: rule = *
  after rename: ['X'] | delete enabled: True
  after delete: ['default'] | current = default | rules = []
  zh-Hans final-result lines: ['最终结果: 軟體']
  en final-result lines: ['Final: 軟體']
  ```

- `mise exec -- make check` raw conclusion: Ruff passed; **865 passed, 1 skipped**; official OpenCC manifest valid; OpenCC differential **28/28**; Jieba differential **10/10**; plugin metadata valid (`0.2.11`).
- `check_ui_acceptance.py --verify --width 960 --height 640`: `status=PASS`, **13 PASS, 0 FAIL** in `/tmp/opencc-2026-09-30-batch1-ui/acceptance.json` (head `78e3533`). Offscreen logical screen was 800×800; requested window was 960×640.
- Pushed `78e3533ac051e24b1176865eabb5e4dc95676ce5`; `origin/main` matched.

## Batch 2 — FU-03

Commit: `0b20091`; pushed after both batch gates passed.

- `test_zero_width_skip_inside_numeric_reference_is_reported` failed before the planner fix (`assert 0 == 1`). Focused suite: **62 passed**.
- Reproduction output:

  ```text
  literal -> [('REGEX_ZERO_WIDTH_SKIPPED', 'rule z: skipped 1 zero-width match(es)')]
  numeric-ref -> [('REGEX_ZERO_WIDTH_SKIPPED', 'rule z: skipped 1 zero-width match(es)')]
  REGEX_ZERO_WIDTH_SKIPPED diagnostics total: 6
  ```

- `mise exec -- make check` raw conclusion: Ruff passed; **866 passed, 1 skipped**; official OpenCC manifest valid; OpenCC differential **28/28**; Jieba differential **10/10**; plugin metadata valid (`0.2.11`).
- Real-Qt acceptance: `status=PASS`, **13 PASS, 0 FAIL** in `/tmp/opencc-2026-09-30-batch2-ui/acceptance.json` (head `0b20091`).
- Pushed `0b20091fc3777e1af3823988c5d6389c20a9f601`; `origin/main` matched.

## Batch 3 — FU-06, FU-07

Commits: `f542e14`, `4250ac3`; pushed together after all gates passed.

- The FU-06 entrypoint check returned eight lines, all `exit=0`: `probe_ux_simplicity`, `benchmark_preview_ui_small`, `probe_followup`, `a10_export_roundtrip`, `test_review_regressions`, `rule06_import_formats`, `probe_edge_cases`, and `fix07_fix08_import_edges`.
- UXS-02 reported all `enter_in_filter_*_accepted` values as `false`. `probe_followup.json` reported `group_semantics.assertions_passed: true` and decisions `{"change-0":"accept_this","change-1":null}`. `test_review_regressions.py`: **16 passed**.
- FU-07 focused tests: **40 passed**. Real-Qt preview-layout verification, run-summary probes in `en` and `zh-Hans`, and `fix14_menu_tooltip_qt.py` exited 0. The tooltip probe printed `default set: delete action enabled: False | tooltip: 默认规则集不能删除。 | menu.toolTipsVisible(): True`; the restored local file-batch flag was true in all three preview languages.
- `mise exec -- make check` raw conclusion: Ruff passed; **866 passed, 1 skipped**; official OpenCC manifest valid; OpenCC differential **28/28**; Jieba differential **10/10**; plugin metadata valid (`0.2.11`).
- Real-Qt acceptance: `status=PASS`, **13 PASS, 0 FAIL** in `/tmp/opencc-2026-09-30-batch3-ui/acceptance.json` (head `4250ac3`).
- Pushed `4250ac3da0fd07e53592d739245f8de2b995ffa9`; `origin/main` matched.

## Batch 4 — FU-08

Commit: `cb349a7`; pushed after both batch gates passed.

- Both new tests failed before their respective guide and validator fixes. Focused suite: **67 passed**. The required obsolete-term searches returned no matches; no i18n catalog key was changed.
- `mise exec -- make check` raw conclusion: Ruff passed; **868 passed, 1 skipped**; official OpenCC manifest valid; OpenCC differential **28/28**; Jieba differential **10/10**; plugin metadata valid (`0.2.11`).
- Real-Qt acceptance: `status=PASS`, **13 PASS, 0 FAIL** in `/tmp/opencc-2026-09-30-batch4-ui/acceptance.json` (head `cb349a7`).
- Pushed `cb349a7c7a969f2ea502fd7c86983c79e8d4ec9b`; `origin/main` matched.

## Batch 5 — FU-05, FU-09

- FU-05 commit `63b3b74` documents the removed features and behavior changes in `docs/releases/v0.2.11.md` and `CHANGELOG.md`. The version metadata files remain untouched. The requested GitHub Release body update and final batch gates are pending this batch's push and verification.
- FU-09 appends corrections to the 2026-09-29 results and records the five batch gates here. `git diff` for the old results file contains additions only.
- `mise exec -- make check` raw conclusion: Ruff passed; **868 passed, 1 skipped**; official OpenCC manifest valid; OpenCC differential **28/28**; Jieba differential **10/10**; plugin metadata valid (`0.2.11`).
- Real-Qt acceptance: `status=PASS`, **13 PASS, 0 FAIL** in `/tmp/opencc-2026-09-30-batch5-ui/acceptance.json` (head `63b3b74`).
- FU-05 acceptance commands: no “retaining/preserving legacy” matches; the release notes contain **2** required sections; CI run `36649657631` is linked; version metadata diff is empty.
- GitHub Release body update for v0.2.11: `gh release edit` completed after `63b3b74` was pushed. `gh release view` confirmed a stable, non-draft release and a body byte-for-text equal to `docs/releases/v0.2.11.md`: [v0.2.11 release](https://github.com/liyafly/OpenCCForSigil/releases/tag/v0.2.11). Sigil-host acceptance for this older release remains **Not verified**.

## Release and host follow-up

- The supplied README's original no-tag restriction is superseded for this execution by the user's direct instruction to stage commits and finish with a tag. The authorized next release target is `v0.2.12`; version preparation, the annotated tag, and its push happen only after the five fix batches pass.
- U1, authorization of the already-published v0.2.11 release at `3107f27`, is historical and cannot be inferred from the current request; `v0.2.11` remains unchanged.
- U2, update the existing v0.2.11 GitHub Release body: **completed**; the remote body matches `docs/releases/v0.2.11.md`.
- U3, real-Sigil installation, conversion, preview acceptance, rule save, history, EPUB save and reopen: **Not verified** until performed against the published v0.2.12 package.
- U4, whether to release 0.2.12: authorized by the current direct request; release/tag work follows the final fix-batch gates.
