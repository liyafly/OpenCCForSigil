# 2026-09-29 implementation results

## Baseline

- Review package and baseline evidence added in `cb4027628fd62fe23a2e1a5ddc2da6567813433a`; files under `evidence/` are unchanged.
- Implementation baseline: `main` at `6d74b25` (version `0.2.10`), clean and synchronized with `origin/main` before the review package was added.
- Sigil host acceptance: **Not verified**.

## Batch 1 — FIX-02, FIX-03, FIX-01

| Item | Commit | Pre-fix failing test(s) | Post-fix result | Acceptance and reproduction |
| --- | --- | --- | --- | --- |
| FIX-02 | `df876bfb6f6553a297f30a0d255bff08c2d278bb` | `test_deleted_ruleset_id_cannot_be_reused_before_save`; `test_edit_rules_never_deletes_a_ruleset_saved_in_same_result` | Focused regression and existing delete tests: 4 passed. | The UI now rejects a deleted ID when creating or renaming a set. The direct `edit_rules` regression confirms a rule set present in both `result.rulesets` and `result.deleted` remains saved. `fix02_fix03_ruleset_rename_delete.py` no longer reuses X or renames Y to X; the direct-result regression covers the persistence boundary. Existing baseline output remains under `evidence/rules/fix02_fix03_ruleset_rename_delete.out`. |
| FIX-03 | `c1193735c2299acc405645e818032c24d49d710e` | `test_rename_keeps_use_in_run_state_and_conflicts`; `test_run_ids_from_window_are_not_remapped_after_rename` | Related `test_rules_window.py`, `test_ruleset_persistence.py`, and `test_profiles_m3.py`: 102 passed, 1 skipped. | After A→B, run IDs now contain B and the checkbox remains checked. Renaming B→B2 preserves the cross-set conflict and keeps Save disabled. The reproduction output matches these expectations; baseline output remains unchanged under `evidence/rules/fix02_fix03_ruleset_rename_delete.out`. |
| FIX-01 | `e7dec013219a413100fd2cffb11879e33095f7d7` | `test_settings_error_message_localizes_rule_conflict`; `test_profile_pick_with_conflicting_rulesets_shows_localized_error`; `test_analyze_with_cross_ruleset_conflict_shows_localized_error` | Focused i18n, run-options, and persistence suite: 71 passed. | Both the analyze and profile-pick paths show the localized `error.rule_conflict` summary with `a1 (A), b1 (B)` and leave the dialog unaccepted. Fake Qt and real Qt reproductions have no escaping traceback; the real Qt message box reports `error_details`. Existing baseline outputs remain unchanged under `evidence/rules/fix01_analyze_conflict_{fakeqt,qt}.out`. |

### Batch verification at `e7dec013219a413100fd2cffb11879e33095f7d7`

- `make check`: Ruff passed; **782 passed, 1 skipped** (the existing fake-Qt layout limitation); vendor manifest passed; OpenCC differential passed (28 cases); Jieba differential passed (10 cases); plugin metadata valid (`0.2.10`).
- Real Qt `check_ui_acceptance.py --verify --width 960 --height 640`: **PASS**, 13 scenarios, no failures; `acceptance.json` is at `/tmp/opencc-ui-acceptance/acceptance.json`.
- FIX-02, FIX-03, and FIX-01 acceptance checks: complete. Sigil host acceptance: **Not verified**.

## Batch 2 — FIX-04, FIX-05, FIX-06

| Item | Commit | Pre-fix failing test(s) | Post-fix result | Acceptance and reproduction |
| --- | --- | --- | --- | --- |
| FIX-04 | `54a0743863d91a89f34bb08c97a05480edec8e2f` | `test_uninvolved_run_ruleset_view_keeps_save_blocked` | Focused rule-conflict and catalog tests: 23 passed. | Switching from A to unrelated C still shows the A/B conflict and leaves Save disabled. A conflict from an unselected ruleset still does not block Save. The reproduction prints `viewing C: conflicts 1 save enabled False`; baseline output remains unchanged in `evidence/rules/fix04_switch_ruleset_reenables_save.out`. |
| FIX-05 | `76ad3c34ea64c27d6e68c2a341c675b039c3117d` | `test_confirming_addition_does_not_persist_unconfirmed_removal` | New regression plus confirmation/rejection tests: 3 passed. | Confirming N appends it to the saved profile while A remains saved; the active session uses only default and N. The reproduction prints `saved profile now: ('default', 'A', 'N')`; the save prompt count remains one. Baseline output remains unchanged in `evidence/rules/fix03_fix05_rename_new_confirm.out`. |
| FIX-06 | `33f6305f851ae343cdffd3fc60d3885bb0b1240c` | `test_default_set_new_rule_direction_follows_each_session`; `test_removing_wildcard_rule_restores_current_direction`; `test_bulk_paste_never_creates_wildcard_rules` | Related rules window, persistence, and rules M3 suites: 122 passed, 1 skipped. The three new regressions also pass. | New default sets persist `default_direction='*'` and select the current session direction. Removing a `*` rule restores s2t for the next rule; bulk paste in `*` mode creates s2t rules. Existing wildcard rules remain explicit and retain their warning. Reproduction outputs match these expectations; baseline outputs remain unchanged under `evidence/rules/fix06_*.out`. |

### Batch verification at `33f6305f851ae343cdffd3fc60d3885bb0b1240c`

- `make check`: Ruff passed; **787 passed, 1 skipped** (the existing fake-Qt layout limitation); vendor manifest passed; OpenCC differential passed (28 cases); Jieba differential passed (10 cases); plugin metadata valid (`0.2.10`).
- Real Qt `check_ui_acceptance.py --verify --width 960 --height 640`: **PASS**, 13 scenarios, no failures; `acceptance.json` is at `/tmp/opencc-ui-acceptance-batch2/acceptance.json`.
- FIX-04, FIX-05, and FIX-06 acceptance checks: complete. Sigil host acceptance: **Not verified**.

## Batch 3 — FIX-07, FIX-08, FIX-15

| Item | Commit | Pre-fix failing test(s) | Post-fix result | Acceptance and reproduction |
| --- | --- | --- | --- | --- |
| FIX-07 | `3a268c1faa123e4397a014271034bba5980011ee` | `test_chinese_tsv_header_is_skipped`; `test_data_row_starting_with_header_word_is_not_skipped` (4 cases); `test_header_row_skip_is_reported_as_info`; `test_three_column_row_with_blank_direction_uses_selected_direction` | Import roundtrip and i18n tests: 53 passed. | Header detection now requires both source and target column labels in the first row; skipped headers produce a localized info diagnostic. Header-like data stays in the import, blank-direction three-column rows use the chosen direction, and the discarded count only includes warnings (excluding the existing quoted-TSV warning). Both FIX-07 repro scripts pass. TSV and CSV formats are documented in all three guide locales and `docs/rule-format.md`. |
| FIX-08 | `94658936c42ad56baee9509b2ff5f2eb06c2724a` | `test_tsv_roundtrip_keeps_unicode_line_separators` (3 valid XML separators); `test_tsv_roundtrip_keeps_form_feed_in_comment`; `test_opencc_txt_import_keeps_unicode_line_separators`; `test_one_column_row_error_has_no_rule_prefix` | Importer and M3 tests: 63 passed. | TSV and OpenCC TXT split only CRLF, CR, and LF; OpenCC candidate separation no longer treats Unicode line separators as whitespace. The repro preserves U+2028/U+2029/NEL and form-feed comments; one-column errors show the physical line only. CSV parsing is unchanged. Two constraints from the plan are adjusted: form-feed is not legal XML text in a rule target, so it is covered in a TSV comment instead; exported TSV now has the FIX-07 informational header diagnostic, so the roundtrip test expects that info item rather than an empty diagnostics tuple. |
| FIX-15 | `43284ef0d82ad4980f4a48b0837a7f30b707b6cf` | `test_delimited_import_fills_only_matching_owner` (9 format/scope cases); `test_window_rebind_clears_the_other_owner` | Importer, rules-window, and M3 tests: 149 passed, 1 skipped (fake Qt layout limitation). | TSV/CSV/TXT imports set only the owner field matching the selected scope. Window rebinding also clears the other owner. Both FIX-15 reproduction scripts pass; `rule_dedup_key` was not changed. |

### Batch verification at `43284ef0d82ad4980f4a48b0837a7f30b707b6cf`

- `make check`: Ruff passed; **809 passed, 1 skipped** (fake-Qt layout limitation); vendor manifest passed; OpenCC differential passed (28 cases); Jieba differential passed (10 cases); plugin metadata valid (`0.2.10`).
- Real Qt `check_ui_acceptance.py --verify --width 960 --height 640`: **PASS**, 13 scenarios, no failures. Output: `/tmp/opencc-ui-acceptance-batch3/acceptance.json/acceptance.json`.
- FIX-07, FIX-08, and FIX-15 acceptance checks: complete. Sigil host acceptance: **Not verified**.

## Batch 4 — FIX-09, FIX-10

| Item | Commit | Pre-fix failing test(s) | Post-fix result | Acceptance and reproduction |
| --- | --- | --- | --- | --- |
| FIX-09 | `1acfbdc9a35d77b21bfc907389050ae464dfff96` | `test_zero_width_runtime_match_is_skipped_not_fatal`; `test_zero_width_skips_aggregate_to_one_diagnostic_per_rule_per_file`; `test_zero_width_diagnostic_record_is_localized`; `test_zero_width_diagnostics_keep_one_record_per_rule` | Regex, preview diagnostics, and i18n tests: 54 passed. | Converter results retain `zero_width_skips` without emitting per-fragment diagnostics; the planner aggregates counts by rule for each file. The probe now reports 6 diagnostics across 6 files, each saying 10 matches were skipped. Preview names and descriptions are localized in all three languages, include the rule ID/count, and contain no source text. |
| FIX-10 | `95836e6a5674bc6277e5862002e1f87e1b741eee` | `test_undecided_filter_group_accept_does_not_rescan_visible_rows` (pre-fix traversal visited 20,000 rows in one action against a 1,000-row limit) | Preview filters, group scaling, decision history, and preview window tests: 65 passed. | A stable entry-position map plus a sorted visible-position list locates only affected rows; removal updates both cached lists incrementally. The model-range fallback refreshes if row removal is rejected. The updated repro reports 0 full refreshes across five grouped accepts; incremental-count fuzzing reports 400 seeds, 0 failures. |

### Batch verification at `95836e6a5674bc6277e5862002e1f87e1b741eee`

- `make check`: Ruff passed; **814 passed, 1 skipped** (fake-Qt layout limitation); vendor manifest passed; OpenCC differential passed (28 cases); Jieba differential passed (10 cases); plugin metadata valid (`0.2.10`).
- Real Qt `check_ui_acceptance.py --verify --width 960 --height 640`: **PASS**, 13 scenarios, no failures; output: `/tmp/opencc-ui-acceptance-batch4/acceptance.json`.
- Real Qt 396,091-row benchmark: `accept_group_status_undecided` median **19.9 ms** (target ≤25 ms); existing `accept_this_no_filter`, `accept_this_status_undecided`, and `accept_file` medians were **6.4 ms**, **19.0 ms**, and **9.9 ms**, all within their existing limits. Full output: `/tmp/opencc-preview-ui-batch4-final.json`.
- FIX-09 and FIX-10 acceptance checks: complete. Sigil host acceptance: **Not verified**.

## Batch 5 — FIX-11, FIX-13, FIX-14

| Item | Commit | Pre-fix failing test(s) | Post-fix result | Acceptance and reproduction |
| --- | --- | --- | --- | --- |
| FIX-11 | `9a0e677` | `test_batch_feedback_omits_zero_groups`; `test_non_cancel_results_have_no_zero_count_fragments` (9 language/scenario cases) | Preview batch, result-count, i18n, artifact-validator, and conversion integration tests: 127 passed. | Batch feedback omits linked-group counts when there are no groups; result rows omit zero-valued details. `fix11_zero_count_fragments.py` reports `zero lines: none` for all 3 locales and all 3 result scenarios. Cancel remains one line and the save reminder remains covered. |
| FIX-13 | `0c09a2f` | `test_one_term_per_concept`; `test_traditional_chinese_separates_accepting_changes_from_applying_them` | `tests/unit/test_i18n.py`: 20 passed. | All locale catalogs use the agreed test-output wording; Traditional Chinese result rows use 寫回; English checkpoint capitalization is corrected. No `沙箱` or `sandbox` terms remain in locale catalogs. The deferred `rules.version_v1`, `rules.version_v2`, and `rules.detail_version` keys remain for SIMP-24. |
| FIX-14 | `20bdfb1` | `test_ruleset_menu_shows_tooltips`; `test_delete_ruleset_prunes_saved_run_options` | Rules-window and ruleset-persistence suites: 101 passed, 1 skipped (fake-Qt layout limitation); the strengthened persistence regression also passed after confirming unrelated preferences remain. | Real Qt reports `menu.toolTipsVisible(): True`. The persisted-preferences reproduction removes the deleted ID and reports `next launch: missing-ruleset notice = ()`; unrelated run options and UI preferences remain intact. |

### Batch verification at `20bdfb1d58255e7a32b535d5a28304a9e55f1aff`

- `make check`: Ruff passed; **826 passed, 1 skipped** (fake-Qt layout limitation); vendor manifest passed; OpenCC differential passed (28 cases); Jieba differential passed (10 cases); plugin metadata valid (`0.2.10`).
- Real Qt `check_ui_acceptance.py --verify --width 960 --height 640`: **PASS**, all 13 scenarios; output: `/tmp/opencc-ui-acceptance-batch5-final/acceptance.json`.
- FIX-11, FIX-13, and FIX-14 acceptance checks: complete. FIX-16 remains skipped per the review decision and is replaced by SIMP-22. Sigil host acceptance: **Not verified**.

## Batch 6 checkpoint — FIX-12 complete; FIX-17 stopped

| Item | Commit | Validation and result |
| --- | --- | --- |
| FIX-12 | `457e75e` | All four repaired 2026-09-28 probes ran. UXS-02 Enter values were `[False, False, False, False]`; rules viewport showed 10 rows and the add button in view at default size and 960×640; both RULE-05 rulesets showed the conflict and disabled Save; RULE-11 run ruleset IDs remained unchanged. The 2026-09-28 results corrections were appended only. |
| FIX-17 | `ff64375` | Required suite: **73 passed, 1 failed**. The failure is `test_compiled_lock_spans_matches_legacy_ordering_for_300_random_snapshots`, exposed after changing random literal sources to the text alphabet. Per the FIX-17 instruction, this is recorded without changing product code or weakening assertions; later batch work is stopped here. |

### FIX-12 PERF-06 low-load runs

`probe_default_diagnostics.py` ran three times with the first `vm.loadavg` values at start of 1.90, 2.48, and 1.88 (all below 4). Each run preserved identical plan digests. Median plan times across the three runs:

| Config | Current | Evidence | Evidence + memo | Digest |
| --- | ---: | ---: | ---: | --- |
| s2t | 4.168 s | 4.034 s | 4.058 s | `06781c1d491c31f7` |
| s2twp | 4.976 s | 4.983 s | 5.048 s | `6284eef800e5b462` |


## Batch 6 closeout — FIX-12, FIX-17, FIX-18

The checkpoint above records the state before the user authorized continuation. Investigation showed the FIX-17 failure was in the old test oracle, not the prefix index: on the deterministic sample, indexed matching equals a full scan. The `r7` exact candidate overlaps the `r21` protection at `[15,16)`, and `r67` overlaps the `r0` protection at `[37,38)`. Both candidates are intentionally skipped by the A-08 protection-first rule, which is also stated in the rule guide and A-08 specification. The randomized regression now compares against a test-local two-pass reference that includes this rule; no product matching code changed. The required FIX-17 suite passes: **74 passed**.

| Item | Commit | Result |
| --- | --- | --- |
| FIX-12 | `457e75e` | Four repaired 2026-09-28 probes and the three-run low-load PERF-06 evidence are recorded above. |
| FIX-17 | `ff64375`, `fdd2554` | Added the specified coverage, then corrected the stale legacy oracle to model A-08 protection precedence. Required suite: 74 passed. |
| FIX-18.1 | `dfcc653` | Added the book-entity matching note to the rule-writing section in Simplified Chinese, Traditional Chinese, and English. |
| FIX-18.2 | `c6d9f9d` | TSV and CSV rows preserve input/list order. JSON export and canonical rule hashing use separate unchanged paths. The new regression checks both delimited formats. |
| FIX-18.3 | `8ddfddc` | The diagnostics tab starts with the unique record count while its panel and display records stay lazy. Three source diagnostics with one duplicate show a count of two. |

### Phase gates at `8ddfddc`

- `make check`: Ruff passed; **832 passed, 1 skipped** (the existing fake-Qt geometry limitation); OpenCC payload manifest passed; OpenCC differential passed (28 cases); Jieba differential passed (10 cases); package metadata valid (`0.2.10`).
- Real Qt `check_ui_acceptance.py --verify --width 960 --height 640`: **PASS**, all 13 scenarios; output: `/tmp/opencc-ui-acceptance-batch6/acceptance.json`. Requested geometry was 960×640; the offscreen logical screen reported by Qt was 800×800. Sigil-host acceptance remains **Not verified**.
- FIX-18 focused suite: **82 passed**. The real-Qt preview benchmark on the committed code passed at **0.7355 s** dialog construction (limit ≤0.75 s), with 396,091 changes and 5,711 unique diagnostics; output: `/tmp/opencc-preview-ui-batch6-verified-3.json`. Repeated cold-process runs ranged from 0.7153 s to 0.8998 s; Qt font alias initialization and machine load varied. The recorded pass is within the requested limit.
- Phase 6 validation is complete. FIX-16 remains skipped as decided earlier and is replaced by SIMP-22.

## Phase 7 — SIMP-01 through SIMP-10

Each item has its own commit on `main`; each commit records a regression that failed before its change. The pre-fix baseline outputs under `evidence/` were left unchanged. Post-fix outputs and UI screenshots are under `/tmp/opencc-phase7-ui-acceptance/` and the SIMP-07 benchmark files listed below.

| Item | Commit | Pre-fix failing test | Result |
| --- | --- | --- | --- |
| SIMP-01 | `b405fc98bc0df218e0027503a11e7c8f549eb6c1` | `test_scope_flow_has_no_standalone_conversion_config_entrypoint` | Removed the unreachable standalone conversion-config flow; regression and full phase gate pass. |
| SIMP-02 | `c20bc9d86a9da57ebe34e8d1fcc28ab9883126b8` | `test_preview_keeps_primary_review_actions_visible_and_collapses_secondary_filters` | Removed hidden bulk controls and their dead call paths. Preview and updated probe checks pass; old probe assertions were redirected to the batch dialog without weakening decision, confirmation, or grouping checks. |
| SIMP-03 | `9ce645a9648a7b7218ffecd61f430763a15b6f82` | `test_legacy_rules_engine_pipeline_and_exports_are_removed` | Removed `rules.engine` and migrated tests/probes to the production converter or compiled overlay. Required suites: 99 passed; 13,440 prefix fuzz inputs had 0 mismatches. Book digest stayed `8bab6319592d5abb`; median improved from 7.232 s to 7.133 s at this item. |
| SIMP-04 | `7fedeac9cd341d7a5173fb3dfef9b85c9109c9d2` | `test_simp04_removes_unreferenced_modules_symbols_and_i18n_keys` | Removed unreferenced modules, aliases, and locale keys. Ruff passed; focused i18n/artifact/rules/package checks: 102 passed. |
| SIMP-05 | `c42f16b01540268bc090eec09ec38a63797d8dc9` | `test_rule_window_result_run_ruleset_ids_defaults_to_empty_tuple` | Removed obsolete result shapes and fallback branches. Focused persistence/rules-window tests: 102 passed, 1 expected fake-Qt layout skip. |
| SIMP-06 | `d15c5d4fed1e53af0d48ee466972b3d9b0b778e5` | `test_controller_default_comes_from_profile_without_duplicate_resource` | Profile defaults are the single source; focused validator/controller tests: 51 passed. |
| SIMP-07 | `a1499b315600019ed933f2e911f01ece1aacd553` | `test_simp07_removes_unmeasured_matcher_fast_paths` | 40 focused tests passed; 13,440 fuzz inputs, 0 mismatches. `/tmp/opencc-simp07-benchmark-rules-final.out`: medians 0.798 s and 0.772 s (the configured limit is 0.8 s). Book digest `8bab6319592d5abb`, median 6.864 s versus 7.232 s baseline. |
| SIMP-08 | `49003997bf89f13e63864b5ec0531ce17a0cfbf0` | `test_plugin_missing_book_apis_fails_with_localized_error` | Missing BookContainer APIs now fail with a localized error. Required session/integration suite: 83 passed. |
| SIMP-09 | `41da3523b9489035dc3eca6c836c9b4ee0c774de` | `test_exec_dialog_requires_the_supported_exec_method` | Removed unreachable UI compatibility branches and the incorrect UserRole fallback; progress labels use the fixed 55-character limit. Focused preview/Qt/rules/progress checks passed; full `make check` passed. The older summary probe was updated to locate the actual merged-window controls; its previous attribute references raised before assertions ran. |
| SIMP-10 | `640895d854195231d6e8fba6f71d316aa676513f` | `test_opencc_txt_export_keeps_v2_literal_rules` | V2 literal rules export to OpenCC TXT and round-trip without source/target changes. Required exporter/M3 suite: 74 passed. |

### Phase 7 gate at `640895d854195231d6e8fba6f71d316aa676513f`

- `make check`: Ruff passed; **838 passed, 1 skipped** (`tests/unit/test_rules_window.py:470`, fake Qt does not calculate widget layout sizes); OpenCC payload manifest passed; OpenCC differential passed (28 cases); Jieba differential passed (10 cases); package metadata valid (`0.2.10`).
- Real Qt `check_ui_acceptance.py --verify --width 960 --height 640`: **PASS**, all 13 scenarios. Output: `/tmp/opencc-phase7-ui-acceptance/acceptance.json`. Qt reported an 800×800 offscreen screen; requested dialog geometry was 960×640. This is offscreen evidence, not physical-display evidence.
- `SIMP-17`, `SIMP-31`, and `SIMP-32`: **按 2026-09-29 决定不做**. Sigil-host acceptance: **Not verified**.

## Phase 8 — SIMP-11 through SIMP-22 (SIMP-17 skipped)

Each SIMP item below is an independent `main` commit. Every listed regression was run before its product change and failed there; the complete post-change regression set passes the Phase 8 gate. The signed baseline files under `evidence/` remain unchanged.

| Item | Commit | Pre-fix failing test(s) | Post-fix result |
| --- | --- | --- | --- |
| SIMP-11 | `b235b05` | `test_rule_manager_has_no_rule_template_action` | Removed regex rule templates and their dead paths; regression passes in the phase gate. |
| SIMP-12 | `493cbad` | `test_scope_dialog_has_no_checkpoint_banner_but_keeps_recovery_notice` | Removed the scope checkpoint banner; recovery notice remains covered and the regression passes. |
| SIMP-13 | `501192a` | `test_legacy_diagnostic_panel_options_do_not_change_profile_comparison`; `test_diagnostic_options_are_not_exposed_in_run_options_panel`; `test_current_profile_drops_legacy_diagnostic_options_from_extras`; `test_diagnostic_option_strings_are_removed_from_catalogs` | Removed diagnostic option switches and stale catalog keys; all four regressions pass. |
| SIMP-14 | `a1cba9b` | `test_more_menu_has_only_single_batch_path_for_decisions`; `test_language_group_action_strings_are_removed_from_catalogs` | Removed language-group decision buttons; updated real-Qt probe verifies item-level grouped decision and one-step Undo/Redo while preserving batch, reset, and undo checks. |
| SIMP-15 | `d9e0705` | `test_json_import_skips_bad_records_and_preserves_record_numbers`; `test_json_import_options_scope_is_default_and_rebind_is_opt_in`; `test_skip_invalid_import_option_string_is_removed_from_catalogs` | Removed strict rule-import mode; the replacement importer regressions pass. |
| SIMP-16 | `4a2b390` | `test_legacy_profile_field_names_remain_extras_and_round_trip`; `test_profile_migration_and_actionable_failure`; `test_language_region_aliases_normalize_during_profile_load`; `test_missing_or_corrupt_active_profile_falls_back_and_clears_preference` | Removed obsolete profile compatibility shims; profile loading regressions pass. |
| SIMP-18 | `3eeb0e5` | `test_conversion_profile_rule_and_history_dialogs_construct`; `test_more_menu_exposes_settings_help_import_bulk_export_and_delete`; `test_new_rule_defaults_ignore_saved_ruleset_direction_and_scope`; `test_jieba_failure_reason_is_available_in_status_tooltip`; `test_simp18_redundant_action_strings_are_removed_from_catalogs` | Focused suite: **132 passed, 1 skipped**; updated run-summary probe passes. |
| SIMP-19 | `22357fe` | `test_profile_summary_shows_quotation_mode_and_lists_full_profile_name`; `test_compare_covers_only_effective_profile_fields`; `test_simp19_ineffective_profile_summary_strings_are_removed_from_catalogs` | Focused profile-window, comparison, run-options, and i18n suite: **77 passed**. |
| SIMP-20 | `f380381` | `test_history_filters_have_no_status_parameter`; `test_history_dialog_button_defaults_and_empty_cleanup_state`; `test_simp20_history_status_filter_string_is_removed_from_catalogs` | History suite: **45 passed**; real-Qt history-layout probe passes in en, zh-Hans, and zh-Hant. |
| SIMP-21 | `e79ea24` | `test_inspect_without_input_uses_the_visible_selected_rule`; `test_test_page_places_input_before_test_buttons`; `test_rule_test_localizes_config_classification_and_rule_labels`; `test_error_report_dialog_constructs_after_dictionary_inspector_removal`; `test_simp21_dictionary_inspector_action_strings_are_removed_from_catalogs` | Focused rule suite: **154 passed, 1 skipped**; Rule-13 reproduction selects `乙方`. The §86 deviation is recorded in `docs/deviations.md`. |
| SIMP-22 | `d100941` | `test_foreign_book_rule_is_labelled_other_book`; `test_simp22_foreign_owner_banner_string_is_removed_from_catalogs` | Focused rules-window and i18n suite: **110 passed, 1 skipped**. |

`SIMP-17`: **按 2026-09-29 决定不做**.

### Phase 8 gate at `865c29f3a6da8e8d4ac687044d7648213f2daea7`

- `mise exec -- make check`: **PASS** — Ruff; **853 passed, 1 skipped** (`tests/unit/test_rules_window.py:485`, fake Qt does not calculate widget layout sizes); official payload manifest; OpenCC differential **28/28**; Jieba differential **10/10**; plugin metadata valid (`0.2.10`).
- Real Qt `check_ui_acceptance.py --verify --width 960 --height 640`: **PASS**, all **13/13** scenarios. Evidence: `/tmp/opencc-phase8-final-ui-acceptance-r4/acceptance.json`. Qt's offscreen logical screen was 800×800; requested dialog size was 960×640.
- D15 probe updates are in `865c29f`; `/tmp/opencc-phase8-preview-probe-r2/` and `/tmp/opencc-phase8-profile-probe-en-r2/` contain direct probe output. The diagnostic comparison field is explicitly expected to be absent; unrelated batch acceptance, reset, undo, and profile behavior checks remain.
- `SIMP-31` and `SIMP-32`: **按 2026-09-29 决定不做**. Sigil-host acceptance: **Not verified**.
- Phase 7 GitHub Actions rerun `36576356063` on `746771f15380d9df1dfab4a5e6fdc4fbd53e900d` completed with one failure on `macos-x86_64`: `tests/unit/test_preview_model.py::test_three_hundred_thousand_preview_build_filter_and_batch_accept_stay_bounded` measured `accept_all_seconds = 1.18194` against the existing `<1.0 s` bound. The other platform jobs passed. No benchmark limit was changed. This CI run was for the Phase 7 SHA; Phase 8 local gates above are green.
- Phase 8 GitHub Actions run `36586808242` on `0696bac199c97008fe82c58f9a28757b685db461` also completed with one failure on `macos-x86_64`: the same preview benchmark measured `accept_all_seconds = 1.04480` against `<1.0 s`. The other platform jobs passed. No benchmark limit was changed; Phase 8 local `make check` and real-Qt gates above passed.

## Phase 9 — SIMP-23, SIMP-24, SIMP-30, and SIMP-25 through SIMP-29

Each item has its own commit on `main`; each commit records tests that failed before its product change. SIMP-28's final summary fix is included in its item commit. The signed baseline files under `evidence/` remain unchanged.

| Item | Commit | Pre-fix failing test(s) | Result |
| --- | --- | --- | --- |
| SIMP-23 | `7d97739` | `test_regex_search_timeout_is_per_call_not_cumulative`; `test_regex_hits_are_limited_per_fragment_not_per_analysis`; `test_candidate_output_limit_resets_for_each_fragment`; `test_converter_does_not_share_applied_output_limits_between_fragments` | Regex, compiled-rule, and transformation workflow suites: **48 passed**; Ruff passed. Limits now reset per fragment while the timeout remains enforced per call. |
| SIMP-24 | `5aaa7e0` | `test_v1_and_v2_scope_precedence_both_follow_the_spec`; `test_unrelated_v2_rule_does_not_flip_v1_scope_winner`; `test_delimited_export_does_not_warn_for_v2_version_alone`; `test_simp24_version_precedence_strings_are_removed_from_catalogs`; `test_rule_details_do_not_show_semantic_precedence_version` | Focused suite: **229 passed, 1 skipped**. Scope precedence is unified; unrelated V2 rules no longer change the winner. |
| SIMP-30 | `68b2ab1` | `test_legacy_quoted_tsv_field_stays_unchanged_without_warning`; `test_rule_model_does_not_accept_pattern_replacement_aliases`; `test_import_path_is_explicit_and_string_values_are_text` | Import, rule-window, and M3 suites: **160 passed, 1 skipped**. Removed redundant import aliases and path-shape detection. |
| SIMP-25 | `b87d679` | `test_disabled_ruleset_shows_reenable_button_and_click_enables`; `test_enabled_ruleset_hides_reenable_button`; `test_reenable_ruleset_label_exists_and_global_switch_labels_are_removed` | Focused suite: **171 passed, 1 skipped**. Real Qt rules layout and the four affected D15 probes pass; re-enabling a ruleset remains available from its disabled-set row. |
| SIMP-26 | `5b3b52b` | `test_scope_enum_contains_only_supported_modes` | Scope, dialog, profile, and integration tests: **123 passed**. The real-Qt UX probe passes in Chinese and English; profile compatibility for the saved `single` string remains. |
| SIMP-27 | `ea21a75` | `test_text_target_does_not_carry_unused_context` | Model, converter diff, and preview diagnostics tests: **31 passed**. Preview context is derived from frozen source text. |
| SIMP-28 | `1bc5505` | `test_run_options_do_not_expose_nav_conversion_toggle`; `test_run_summary_includes_nav_when_it_is_in_the_selected_file_set`; `test_nav_in_selected_files_is_always_converted`; `test_profile_summary_uses_localized_direction_and_option_labels`; `test_profile_summary_shows_quotation_mode_and_lists_full_profile_name` | NAV follows the resolved file set; the profile summary omits the retained compatibility field. Final combined focus: **113 passed**; the real-Qt run-summary probe passes. D15 updates and scope behavior are recorded in the item commit. |
| SIMP-29 | `9bfff12` | `test_language_modes_do_not_assign_generic_traditional_to_taiwan`; `tests/unit/test_profiles_m3.py::test_saved_suggest_language_mode_loads_as_update`; `tests/unit/test_run_options.py::test_saved_suggest_language_mode_loads_as_update` | Legacy `suggest` profiles load as Update; generic Traditional Legacy mode still requires an explicit region. The required suite passed (**71 passed**) and XML target tests passed (**23 passed**); final combined focus: **113 passed**. |

### Phase 9 gate at `9bfff12570eb2e26d85bbfda860c35df95493054`

- `mise exec -- make check`: **PASS** — Ruff; **860 passed, 1 skipped** (`tests/unit/test_rules_window.py:477`, fake Qt does not calculate widget layout sizes); official payload manifest valid; OpenCC differential **28/28**; Jieba differential **10/10**; plugin metadata valid (`0.2.10`).
- Real Qt `check_ui_acceptance.py --verify --width 960 --height 640`: **PASS**, all **13/13** scenarios. Evidence: `/tmp/opencc-phase9-final-ui-acceptance/acceptance.json`. PySide6/Qt 6.11.2 used an 800×800 offscreen logical screen; requested geometry was 960×640.
- Real Qt run-summary D15 probe: **PASS**. Evidence: `/tmp/opencc-phase9-final-summary/summary-en.json`.
- `git diff origin/main -- docs/reviews/2026-09-29/evidence`: empty. The signed review evidence directory is unchanged.
- `SIMP-17`, `SIMP-31`, and `SIMP-32`: **按 2026-09-29 决定不做**. Sigil-host acceptance: **Not verified**. The first remote run and its performance follow-up are recorded below.

## Phase 9 post-push performance follow-up

- Initial GitHub Actions run [`36595943990`](https://github.com/liyafly/OpenCCForSigil/actions/runs/36595943990) on `f66113a0a084f191392bd959dd797329d30ed4b7` failed only on macOS x86_64 at `test_three_hundred_thousand_preview_build_filter_and_batch_accept_stay_bounded`: `accept_all_seconds = 1.82905` against the unchanged `<1.0 s` bound. The other five payload jobs passed; **859 passed, 1 skipped** in the failing job. Package assembly and smoke jobs were skipped after the matrix failure.
- Follow-up commit `6ff11aaeb69d93f37cfd4d20926b750d9ef3cb08` adds batched decision restoration per preview session and per-file count updates. The new `test_preview_session_restores_many_decisions_with_one_revision` was run red before implementation. The 300k performance test passes locally; no performance threshold was changed.
- `mise exec -- make check` at `6ff11aaeb69d93f37cfd4d20926b750d9ef3cb08`: **PASS** — Ruff; **861 passed, 1 skipped** (`tests/unit/test_rules_window.py:477`, fake Qt does not calculate widget layout sizes); official payload manifest valid; OpenCC differential **28/28**; Jieba differential **10/10**; plugin metadata valid (`0.2.10`).
- Real Qt acceptance after the follow-up: **PASS**, all **13/13** scenarios. Evidence: `/tmp/opencc-postci-bulk-preview-ui/acceptance.json`; PySide6/Qt 6.11.2, 800×800 offscreen logical screen, requested geometry 960×640.
- Follow-up GitHub Actions run [`36598487777`](https://github.com/liyafly/OpenCCForSigil/actions/runs/36598487777) on `6ff11aaeb69d93f37cfd4d20926b750d9ef3cb08`: **SUCCESS**. All six payload jobs, cross-platform Jieba comparison, plugin package assembly, and all six package smoke jobs passed. Tag-only attestation and GitHub Release jobs were skipped for this branch push.

## 2026-09-30 corrections (append-only)

The following corrections describe the state and evidence at baseline `3107f27`; see `docs/reviews/2026-09-30/01-acceptance-audit.md` for the item-by-item audit.

1. **SIMP-18:** The reported test name `test_jieba_failure_reason_is_available_in_status_tooltip` does not exist. The two relevant tests did fail on the parent commit.
2. **SIMP-23:** `test_converter_does_not_share_applied_output_limits_between_fragments` does not exist; the actual test is `test_selected_output_has_no_analysis_wide_limit`. Step 4, compiling each regex once, was not implemented or reported.
3. **SIMP-28:** `test_profile_summary_uses_localized_direction_and_option_labels` passed before the product change; it was incorrectly described as a red test.
4. **FIX-09:** Numeric character references did not pass `zero_width_skips` into `ConvertResult`, so their zero-width diagnostic was missing. FU-03 restores that propagation.
5. **FIX-08:** The `OpenCC TXT` candidate separator change also means U+3000 and NBSP are retained in the target; the old record omitted this behavior change. FU-05 adds it to both release records.
6. **FIX-07:** The two existing assertions changed during implementation; the old record did not say so.
7. **FIX-14:** The reproduction script was changed to use a real `UserDataStore`; the old record omitted that change.
8. **FIX-18.2, FIX-18.3, and `fdd2554`:** Their commit messages omitted the required pre-fix failing-test evidence.
9. **Phase 7 and Phase 8:** Phase 7's statement that no assertions were weakened was false. Phase 8's “unrelated batch checks remain” was also false: `865c29f` had removed the mixed-dialog file-batch assertion. FU-07 restores checks for hidden controls and local rule-group completion.
10. **Phase 9 gate:** `probe_ux_simplicity.py` was not rerun, so its broken entry point went unnoticed; `benchmark_preview_ui.py` was broken as well. FU-06 repairs both entry points.
11. **`746771f`:** The all-scope preview optimization was outside the approved list and appeared only as a CI SHA in the old results. Per D19 it is retained and recorded separately below.

### Process corrections

- Ruff failed with F401 from `3eeb0e5` through `d100941` (five commits), and was fixed at `2d233a5`.
- The real-Qt `check_run_summary.py` probe did not run successfully from SIMP-02 through SIMP-08; it remained hung for more than ten minutes at `d15c5d4`.
- `ux04` had failed since `a1cba9b`, and `ux02` since `501192a`/`3eeb0e5`; both were fixed by `865c29f`.
- These red gates were followed by additional changes, contrary to the rule that a failed batch gate stops progression.

### Decisions retained or deferred

- `746771f` is retained under D19; its pre-fix failing test is `test_all_scope_undecided_batch_reuses_entries_without_decision_scan`.
- SIMP-23 step 4 is not done under D17; each regex is compiled three times, with at most 128 rules.
- `LiteralPrefixIndex.single_char_buckets` is retained under D18 as a deviation from the original simplification intent; the recorded 13,440 fuzz cases and 300 independent comparisons found no mismatch, and measured speedup was 5–8%.
- The explicit non-string backend-output check removed by SIMP-03 is not restored under D21; the official backend returns `str`, and `test_non_string_backend_output_is_rejected` currently passes through a `len(None)` failure in `core/diff.py:49`.
- The 2026-09-23 round2 probes `s1_jieba_loop.py`, `s2_direction_reset.py`, `s3_commit_progress.py`, `s4_future_schema.py`, `s6_stale_prefs.py`, and `l07_eq.py` are retired under D20 because SIMP-01, SIMP-16, and SIMP-03 removed the behavior they exercise.
