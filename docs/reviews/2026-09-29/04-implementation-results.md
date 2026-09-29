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
