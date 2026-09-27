# UI workflow implementation results

- Specification and before-evidence baseline: `b9ffacfdffdebc16cbb1f8e42447f9cc0a1133aa`.
- Starting implementation HEAD: `b9ffacfdffdebc16cbb1f8e42447f9cc0a1133aa`.
- Final implementation and acceptance-driver HEAD: `31c76fe` (`main`, pushed to `origin/main`). The consolidated Qt matrix ran at this SHA; the benchmark helper was added in `9c9f37a`, focused UX-01 tests in `e7ded5c`, and a byte-for-byte saved-profile preservation assertion in `31c76fe`.
- Environment: macOS 27 arm64, Python 3.14.7, PySide6/Qt 6.11.2, `QT_QPA_PLATFORM=offscreen`; four wrappers use synthetic EPUB/settings data and temporary storage.
- Release metadata remains 0.2.8. No release or publication was performed.

| Item | Implementation commits | Formal and Qt result | Sigil host | Remaining boundary |
| --- | --- | --- | --- | --- |
| UX-01 | `9498e52`; acceptance probes `e7ded5c`, `31c76fe` | Rule summary follows this run's switch; real Qt probe checks false→true and true→false preference values, frozen `tw2sp` rule snapshot IDs, and enabled switch on `s2t` without claiming rules hit. The saved Profile JSON bytes are identical after those panel changes. Focused tests and Qt assertions pass in all three locales. | Not verified | Host conversion output not exercised. |
| UX-02 | `649448e`; acceptance coverage `584d714` | Bounded, independently scrollable ruleset choices; 200 saved profiles and 64 total rule choices measured at each locale. Comparison picker tests filter, empty state, ruleset changes, use/copy/delete stable IDs. | Not verified | Real Qt ran 60 extra rulesets. 0/1/300-choice real widgets, physical 800×600/multi-monitor changes, and repeated real screen moves are not verified. |
| UX-03 | `6eda45f`, `d0d8db0`, completed in `c7a781e` | Merged settings summary, maximum two-line summary, advanced-risk hint, full read-only saved/current/effective table (including unchanged MathML), complete-value tooltips, Jieba pending/unavailable blocking, and read-only spies all pass in three locales. Focused suite: 71 passed. | Not verified | No prior file set was restored by the probe, but a complete close/new-session/return-to-settings host scenario is not verified. Details window measured 800×680 because the synthetic offscreen screen is 800×800. |
| UX-04 | `5ab17cc` | Preview actions, more-menu QAction integration, filter/diagnostic tabs, status synchronization, export opt-in/cancel, and three-language layout probes pass. | Not verified | Real book source offsets and Apply are covered by existing tests, not a Sigil session. |
| UX-05 | `0b1c5f2` | B1/B3/B5/B10 actual Qt dialog and action scenarios pass in all three locales. 300,000-entry planner test visits each decision once without copying text. Additional benchmark records 10k/100k/300k median and memory. | Not verified | Benchmark measures the pure ungrouped planner path; it does not claim end-to-end preview-window latency. |
| UX-06 | `43571bf` | Rules editor and sandbox layout/interaction probe plus formal regression suite pass; draft, conflict count, stale-result invalidation, orientation resize handling, and rule-scope behaviors are retained. | Not verified | Native Sigil editing/testing and applying after a rule change are not verified. |
| UX-07 | `765ceb6` | Search and empty state, profile identity through filtering, ruleset comparison refresh, and panel-option comparison pass with 200 profiles in all three locales. | Not verified | No existing user's real profile directory was used; probes use synthetic profiles. |
| UX-08 | `6b90fcb` | 1,000 metadata records, AND filters, sorting with stable session IDs, empty state, full-history cleanup prompt and byte-identical cancellation pass in all three locales. | Not verified | No real user's history store was read or changed. |

## Evidence

The original plan, executable baseline probe, before screenshots, and baseline logs remain under `evidence/before/`; none were removed or rewritten. The consolidated runner is [`scripts/check_ui_acceptance.py`](scripts/check_ui_acceptance.py). Its `--verify` path invokes real PySide6 interactions and writes an `acceptance.json` with per-scenario PASS/FAIL, commit SHA, Python, PySide6/Qt, OS, QPA, logical screen, DPR, and requested geometry.

All four final consolidated runs were executed at HEAD `31c76fe` and have 13/13 scenarios passing, including the UX-01 real Qt probe, saved-file byte snapshot, and focused formal tests:

- [`evidence/after/ui-acceptance-960x640/`](evidence/after/ui-acceptance-960x640/)
- [`evidence/after/ui-acceptance-1280x800/`](evidence/after/ui-acceptance-1280x800/)
- [`evidence/after/ui-acceptance-scale-125/`](evidence/after/ui-acceptance-scale-125/)
- [`evidence/after/ui-acceptance-scale-200/`](evidence/after/ui-acceptance-scale-200/)

The 960×640 and 1280×800 values are requested Qt logical window sizes, not attached display sizes. The normal offscreen screen reports 800×800 at DPR 1.0; the 125% run reports 640×640 at DPR 1.25; the 200% run reports 400×400 at DPR 2.0. Thus these runs check Qt scaling and requested geometry only. They do not establish physical high-DPI, 1280×800-screen, 800×600-screen, multi-monitor, native theme, or system-font behavior.

UX-03 screenshots and detailed per-locale summaries are in [`evidence/after/ux03/`](evidence/after/ux03/). In the details dialog, the horizontal scrollbar maximum is zero and all four columns are inside the viewport. Long cells visually elide their contents; hovering exposes the full tooltip, which the Qt probe checks for both a long ruleset ID and the complete NAV disabled reason. The offscreen details dialog geometry is 800×680.

The UX-05 benchmark is [`evidence/after/ux05/benchmark-300k.json`](evidence/after/ux05/benchmark-300k.json), generated with the committed script at `9c9f37a`. Across three repetitions, median planner times were 0.0138 s for 10,000 entries, 0.1393 s for 100,000, and 0.4658 s for 300,000. Decision accesses were exactly one per input entry at every size. Peak incremental planner allocations, excluding the prebuilt fixture, were 0.263 MiB, 3.737 MiB, and 11.403 MiB. These timings are specific to this machine and synthetic ungrouped fixture with no source/target text.

## Total checks

At the final implementation SHA `31c76fe`, `make check` exited 0: **682 passed, 1 skipped** in 137.71 seconds. The single skip is `tests/unit/test_rules_window.py:336`, because fake Qt does not calculate widget layout sizes. The target also passed Ruff, vendored OpenCC manifest validation, the 28-case OpenCC CLI/Python differential smoke, the 10-case native Jieba differential smoke, and plugin metadata validation.

`make package` exited 0 and created `dist/OpenCCForSigil_0.2.8.zip`; `make artifact-check` exited 0 and reported the archive valid. This validates the locally available macOS arm64 payload only; it does not claim a complete Fat Plugin or publication. `git diff --check`, targeted Ruff, and Python compilation of the acceptance scripts passed.

The UX-03 focused regression command reported 71 passed. The consolidated real-Qt commands at 960×640, 1280×800, and `QT_SCALE_FACTOR=1.25` / `QT_SCALE_FACTOR=2` each exited 0. Their JSON reports contain no failed scenarios.

## Sigil-host acceptance

H1–H8 are **Not verified** on real Sigil for macOS, Windows, and Linux. These runs do not use a live Sigil process or a real EPUB, and make no claim about saved/reopened EPUB contents. Physical native dark/light themes and display transitions also remain Not verified. The automated zero-read/write assertions are separate evidence from host-level observation.

The implementation and local automated/real-Qt checks are complete; host acceptance remains open. No version number was changed and no release was created.
