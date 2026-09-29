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
