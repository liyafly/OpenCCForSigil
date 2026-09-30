# 02 剩余工作：FU-01 至 FU-09

基线 `3107f27`。先读 [README](README.md) 的已定决定（D16–D22）、全局约束（包括新增的第 15–18 条）和批次顺序。

**写法说明**
- 行号都是 `3107f27` 上的行号。改动前先用 `grep -n` 确认位置；如果行号已经变了，以函数名或下文引用的原文为准。
- 代码块里的“原文”都是逐字复制的。编辑时用精确替换，不要凭记忆重打。
- 产品修复（FU-01 至 FU-04）先写测试，在修复前确认它失败，再改代码（全局约束 11、16）。
- 本文的每一处改动，都已在 `3107f27` 的临时工作树里完整试做过。

---

## FU-01（P2，FIX-06 规格错误）连续更新一条 `*` 规则两次，它会被静默改成 s2t

**位置**
- `plugin/OpenCCForSigil/ui/rules_window.py:1464` `_update_selected()`。`:1482` 调用了 `self._reset_wildcard_direction()`。
- `ui/rules_window.py:907-909` `_reset_wildcard_direction()`：方向框为 `*` 时，把它改回当前方向。

**现状**
- `evidence/rules/fu01_wildcard_update.out`：
  ```
  loaded: combo = * | editing = w
  after 1st update: rule = * | combo = s2t | editing = w
  after 2nd update: rule = s2t
  ```
- 第一次更新后，编辑区仍绑定同一条规则（`_editing_rule_id = previous.id`），方向框却被改成了 s2t，而且标记为“未修改”。用户再改一下目标文本、点“更新”，这条规则的方向就被静默写成 s2t。
- 根因：2026-09-29 FIX-06 第 3 步要求在 `_update_selected()` 成功之后也调用重置。重置只应该在编辑区清空、准备写下一条新规则时发生。

**期望**
- 更新一条已有规则后，方向框保持这条规则自己的方向。
- FIX-06 的其他行为不变：新增一条之后、删除之后、清空编辑区之后，`*` 仍然会重置为当前方向。

**修改方法**
1. 在 `_update_selected()` 末尾删掉 `self._reset_wildcard_direction()` 这一行。原文：
   ```python
           self._editing_rule_id = previous.id
           self._refresh()
           self._reset_wildcard_direction()
           self._mark_editor_clean()
           self._mark_test_result_stale()
   ```
   改为：
   ```python
           self._editing_rule_id = previous.id
           self._refresh()
           self._mark_editor_clean()
           self._mark_test_result_stale()
   ```
2. 其他调用 `_reset_wildcard_direction()` 的地方都不动：`_clear_editor()`（`:903`）、`_add()`（`:1454`）、`_remove()`（`:1546`）。

**测试**
- 在 `tests/unit/test_rules_window.py` 文件末尾追加：
  ```python
  def test_updating_wildcard_rule_twice_keeps_wildcard_direction():
      rule = Rule(id="w", source="里", target="裡", direction="*")
      manager = RuleManagerDialog(
          make_with_table(), (rule,), translator=Translator("en"), config="s2t",
          rulesets=(RuleSet("default", (rule,)),), ruleset_id="default",
          run_ruleset_ids=("default",))
      manager.table.selectRow(0)
      manager._load_selected()

      manager.target_edit.setText("裏")
      manager._update_selected()
      assert manager.direction_combo.currentData() == "*"

      manager.target_edit.setText("裡")
      manager._update_selected()
      assert manager.rules[0].direction == "*"
  ```
  这个文件已经 import 了 `Rule`、`RuleSet`、`make_with_table`、`Translator`、`RuleManagerDialog`，不用再加 import。
- 修复前的失败信息应为 `AssertionError: assert 's2t' == '*'`。
- 以下现有测试必须继续通过：`test_removing_wildcard_rule_restores_current_direction`、`test_bulk_paste_never_creates_wildcard_rules`、`test_wildcard_direction_shows_reverse_warning`。

**验收标准**
- [ ] `fu01_wildcard_update.py` 输出：
  ```
  loaded: combo = * | editing = w
  after 1st update: rule = * | combo = * | editing = w
  after 2nd update: rule = *
  ```
- [ ] 2026-09-29 的三个 FIX-06 脚本输出不变：`fix06_default_direction_persist`、`fix06_wildcard_inherit`（下一条为 `s2t`）、`fix06_bulk_add_wildcard`（全部为 `s2t`）。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/integration/test_ruleset_persistence.py tests/unit/test_rules_m3.py -q
QT_QPA_PLATFORM=offscreen mise exec -- uv run python docs/reviews/2026-09-30/scripts/rules/fu01_wildcard_update.py
for s in fix06_default_direction_persist fix06_wildcard_inherit fix06_bulk_add_wildcard; do
  mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/$s.py; done
```

**不要做**
- 不删除 `_reset_wildcard_direction()` 本身，也不删除其他 3 处调用。
- 不改 `_apply_rule_defaults()`。
- 不迁移磁盘上已有的 `*` 规则。

---

## FU-02（P2，SIMP-05 前提错误）把 `default` 重命名后再删除，会抛出 `StopIteration`

**位置**
- `ui/rules_window.py:1051` `_delete_ruleset()`。`:1053` 只拦截 ID 等于 `"default"` 的集。`:1076-1080` 先从 `self._rulesets` 删掉当前集，再执行 `self._ruleset_id = next(iter(self._rulesets))`。
- `ui/rules_window.py:1001` `_rename_ruleset()`：允许把 `default` 改成别的名字。
- SIMP-05（`c42f16b`）删掉了“删空后重建 default”的两行，理由是这段代码走不到。实际上通过重命名可以走到。

**现状**
- `evidence/rules/fu02_rename_default_delete.out`：
  ```
  after rename: ['X'] | delete enabled: True
  EXCEPTION escapes _delete_ruleset: StopIteration  | rulesets left = []
  ```
- 在真实 Qt 里，这个异常发生在槽函数中，界面上没有任何提示。窗口内部已经没有规则集，但下拉框和表格还显示着 X。

**期望**（D16）
- 恢复 0.2.10 的行为：删到一个不剩时，重建一个空的 `default` 并切换过去，不抛异常。
- 保存后，磁盘上只剩一个空的 `default.json`，`X.json` 被删除。

**修改方法**
1. 在 `_delete_ruleset()` 里 `self._ruleset_id = next(iter(self._rulesets))` 的前一行，加回两行。原文：
   ```python
           self._run_ruleset_ids = tuple(
               item for item in self._run_ruleset_ids if item != identifier)
           self._ruleset_id = next(iter(self._rulesets))
   ```
   改为：
   ```python
           self._run_ruleset_ids = tuple(
               item for item in self._run_ruleset_ids if item != identifier)
           if not self._rulesets:
               self._rulesets["default"] = RuleSet("default")
           self._ruleset_id = next(iter(self._rulesets))
   ```
   `RuleSet` 已经在文件顶部 import（`:19`）。按 FIX-06，`RuleSet("default")` 的 `default_direction` 默认值就是 `*`，不要传别的参数。

**测试**
- 在 `tests/unit/test_rules_window.py` 文件末尾追加（这是修复前会失败的测试）：
  ```python
  def test_deleting_last_ruleset_after_renaming_default_recreates_empty_default(monkeypatch):
      qt = make_with_table()
      qt.QInputDialog = SimpleNamespace(getText=lambda *_args, **_kwargs: ("X", True))
      rule = Rule(id="d1", source="旧", target="舊", direction="s2t")
      manager = RuleManagerDialog(
          qt, (rule,), translator=Translator("en"), config="s2t",
          rulesets=(RuleSet("default", (rule,)),), ruleset_id="default",
          run_ruleset_ids=("default",))
      manager._rename_ruleset()
      monkeypatch.setattr(rules_window, "ask_confirmation", lambda *_args, **_kwargs: True)

      manager._delete_ruleset()

      assert list(manager._rulesets) == ["default"]
      assert manager._ruleset_id == "default"
      assert manager.rules == []
      manager._apply()
      assert manager.result.deleted == ("X",)
      assert [ruleset.id for ruleset in manager.result.rulesets] == ["default"]
  ```
  `SimpleNamespace` 和 `rules_window` 在这个文件里都已 import。修复前会以 `StopIteration` 失败。
- 在 `tests/integration/test_ruleset_persistence.py` 文件末尾追加一个守卫测试。它锁定保存结果，修复前后都会通过，照抄下面的代码：
  ```python
  def test_deleting_renamed_default_keeps_an_empty_default_on_disk(monkeypatch, tmp_path):
      profile_store = ProfileStore(tmp_path / "profiles")
      profile = Profile(id="saved", name="Saved", ruleset_ids=("default",))
      profile_store.save(profile)
      rules = RuleStore(tmp_path / "rules")
      rules.save(RuleSet("default", (Rule(id="d1", source="旧", target="舊", direction="s2t"),)))
      settings = RunSettings(
          Storage(tmp_path), SimpleNamespace(book_fingerprint=lambda: "book-hash"),
          {"profile_id": "saved"}, language="en", session_id="test-session",
      )
      settings.bind_run(profile, SimpleNamespace(available_configs=lambda: {"s2t"}))
      result = RuleWindowResult(
          "default", (RuleSet("default"),), (("default", "X"),),
          run_ruleset_ids=(), deleted=("X",),
      )
      RuleDialogQt.QMessageBox.response = True
      monkeypatch.setattr("ui.rules_window.show_rules_window",
                          lambda *_args, **_kwargs: result)

      settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

      assert sorted(path.name for path in (tmp_path / "rules").iterdir()) == ["default.json"]
      assert rules.load("default").rules == ()
  ```
  这里的 `Translator`、`RuleDialogQt`、`Storage` 都是这个测试文件自己定义的（`:36`、`:156`、`:161`），不要改成 `ui.i18n.Translator`。

**验收标准**
- [ ] `fu02_rename_default_delete.py` 输出：
  ```
  after rename: ['X'] | delete enabled: True
  after delete: ['default'] | current = default | rules = []
  ```
- [ ] 两个新测试都通过，FIX-02、FIX-03 的现有测试也都通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/integration/test_ruleset_persistence.py tests/unit/test_profiles_m3.py -q
QT_QPA_PLATFORM=offscreen mise exec -- uv run python docs/reviews/2026-09-30/scripts/rules/fu02_rename_default_delete.py
mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix02_fix03_ruleset_rename_delete.py
```

**不要做**
- 不禁止重命名 `default`，不加新文案（D16）。
- 不改 `app/settings.py` 的 `edit_rules`。
- 不改“默认规则集不能删除”的判断（`:1053`）。

---

## FU-03（P3，FIX-09 漏项）数字字符引用里的零宽跳过没有诊断

**位置**
- `plugin/OpenCCForSigil/core/planner.py:131-140`，`elif target.node_id.startswith("numeric_ref:"):` 分支。它新建 `ConvertResult` 时只传了 `converted.diagnostics`，没有传 `converted.zero_width_skips`。
- `:145-146` 汇总 `result.zero_width_skips`，所以这个分支的跳过数永远是 0。
- `core/models.py:140`：`ConvertResult.zero_width_skips` 字段。

**现状**
- `evidence/rules/fu03_numeric_ref_zero_width.out`：
  ```
  literal -> [('REGEX_ZERO_WIDTH_SKIPPED', 'rule z: skipped 1 zero-width match(es)')]
  numeric-ref -> []
  ```
- 在 FIX-09 之前（`664a8c1`），数字引用分支会产生 1 条诊断。现在一条也没有，是静默丢失。

**修改方法**
1. `core/planner.py`，数字引用分支末尾的 `ConvertResult(...)`。原文：
   ```python
                   span=SourceSpan(0, len(target.source_text)), category="numeric_reference", risk="HIGH"),),
                   converted.diagnostics)
   ```
   改为：
   ```python
                   span=SourceSpan(0, len(target.source_text)), category="numeric_reference", risk="HIGH"),),
                   converted.diagnostics, zero_width_skips=converted.zero_width_skips)
   ```

**测试**
- 在 `tests/unit/test_regex_rules.py` 文件末尾追加：
  ```python
  def test_zero_width_skip_inside_numeric_reference_is_reported():
      from document.tokenizer import TokenizerOptions

      rule = _rule(id="z", source=r"(?<=中)[^」]*", target="…")
      source = "<html><body><p>&#x4E2D;</p></body></html>"
      planned = ConversionWorkflow(
          SigilBookAdapter(_Book({"c": source})), _Backend(), _request((rule,)),
          tokenizer_options=TokenizerOptions(decode_numeric_cjk_refs=True),
      ).plan()

      diagnostics = [diagnostic for item in planned for diagnostic in item.plan.diagnostics
                     if diagnostic.code == "REGEX_ZERO_WIDTH_SKIPPED"]
      assert len(diagnostics) == 1
      assert "rule z" in diagnostics[0].message
  ```
  修复前会以 `assert 0 == 1` 失败。

**验收标准**
- [ ] `fu03_numeric_ref_zero_width.py` 的两行都各有 1 条 `REGEX_ZERO_WIDTH_SKIPPED`。
- [ ] 2026-09-29 的 `fix09_zero_width_diagnostics.py` 仍输出 `diagnostics total: 6`。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_regex_rules.py tests/unit/test_preview_diagnostics.py tests/unit/test_i18n.py -q
mise exec -- uv run python docs/reviews/2026-09-30/scripts/rules/fu03_numeric_ref_zero_width.py
mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix09_zero_width_diagnostics.py
```

**不要做**
- 不改其他两个分支（语言标记分支、普通文本分支）。
- 不改诊断文案。

---

## FU-04（P3，SIMP-21 多抄一行）规则测试输出里“最终结果”出现两次

**位置**
- `ui/rules_window.py` `_test()`：
  - `:1699` 已有一行 `f"{self._labels['final_label']}: {inspection.final}"`；
  - SIMP-21 在 `:1731-1732` 又追加了一行，用的是 `common.label_separator`。

**现状**
- `evidence/rules/fu04_rule_test_final_once.out`：
  ```
  zh-Hans final-result lines: ['最终结果: 軟體', '最终结果：軟體']
  en final-result lines: ['Final: 軟體', 'Final: 軟體']
  ```

**修改方法**
1. 删掉 `:1731-1732` 这两行。原文：
   ```python
               lines.append(
                   f"{self._labels['final_label']}{separator}{inspection.final}")
   ```
   紧接在后面的 `attribution_key = (` 一段保持不变。
2. `:1699` 那一行保持原样，不要顺手改它的分隔符。

**测试**
- 在 `tests/unit/test_rules_window.py` 文件末尾追加：
  ```python
  def test_rule_test_output_lists_final_result_once():
      rule = Rule(id="r1", source="软件", target="軟體", direction="s2t")
      manager = RuleManagerDialog(
          make_with_table(), (rule,), translator=Translator("zh-Hans"), config="s2t",
          official_convert=lambda _config, text: text.replace("软件", "軟件"),
          rulesets=(RuleSet("default", (rule,)),), ruleset_id="default",
          run_ruleset_ids=("default",))
      manager.test_input.setPlainText("软件")
      manager._test()
      final_label = Translator("zh-Hans").text("rules.final_label")
      lines = manager.test_output.toPlainText().splitlines()
      assert sum(line.startswith(final_label) for line in lines) == 1
  ```
  修复前会以 `assert 2 == 1` 失败。

**验收标准**
- [ ] `fu04_rule_test_final_once.py` 输出：
  ```
  zh-Hans final-result lines: ['最终结果: 軟體']
  en final-result lines: ['Final: 軟體']
  ```
- [ ] SIMP-21 的现有测试 `test_rule_test_localizes_config_classification_and_rule_labels` 仍然通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py -q
QT_QPA_PLATFORM=offscreen mise exec -- uv run python docs/reviews/2026-09-30/scripts/rules/fu04_rule_test_final_once.py
mise exec -- uv run python docs/reviews/2026-09-28/scripts/rules/rule13_inspect_filtered_row.py
```

**不要做**
- 不删比较行、配置行、归因行、分类行。
- 不改 `rules.final_label` 文案。

---

## FU-05（P2，发布说明）v0.2.11 的发布说明漏写了功能删除和行为变化

**位置**
- `docs/releases/v0.2.11.md`：`## Changes`（`:20-33`）、`## Automated validation`（`:35-40`）。
- `CHANGELOG.md` 的 `## 0.2.11 - 2026-09-30` 一节。
- GitHub Release 页面的正文是打标签时由 `.github/workflows/ci.yml:567-572` 从 `docs/releases/v0.2.11.md` 生成的。之后改这个文件，**不会**自动更新页面（见 D22）。

**现状**
- 发布说明里没有 “Removed” 一节。01 的 SIMP-11、12、13、14、15、18、19、20、21、22、25、30 都是用户能看到的删除，一项都没列。
- “Changes” 最后一条写“while retaining legacy saved-profile behavior”，不对。SIMP-29 之后，旧的 “suggest” 按 Update 执行；通用繁体 + Legacy + 未选地区时，以前什么都不改，现在会阻止分析，并要求选择地区。
- D9 的胜负变化，CHANGELOG 写在 Fixed 下，而且写得很清楚；发布说明只写了一句“apply one scope precedence”。
- “Automated validation” 没有 CI 链接，模板（`docs/releases/TEMPLATE.md`）要求写。

**修改方法**
1. `docs/releases/v0.2.11.md`：把 `## Changes` 最后一条原文
   ```
   - Reduce language-tag choices to keeping existing tags or updating Chinese
     tags, while retaining legacy saved-profile behavior.
   ```
   改为：
   ```
   - Reduce language-tag choices to keeping existing tags or updating Chinese
     tags. Saved "suggest" profiles load as "update".
   ```
2. 在 `## Changes` 一节之后、`## Automated validation` 之前，插入下面两节（英文，逐字照抄）：
   ```markdown
   ## Behavior changes

   - At the same source position, profile rules created by v0.2.5 or later now
     lose to global rules, as spec §11.2 requires. Book rules remain highest.
   - For generic Traditional Chinese with the Legacy preset and no explicit
     region, analysis now stops and asks for a region instead of leaving
     language tags unchanged.
   - NAV is converted when it is in the selected file set; the separate NAV
     switch is gone.
   - Regex rules keep the 50 ms per-search timeout and per-fragment hit and
     candidate limits; the whole-analysis time, hit, and output limits are
     removed, so large books no longer fail on them.
   - OpenCC TXT import splits candidate targets only on ASCII spaces and tabs.
     Ideographic spaces (U+3000) and no-break spaces stay in the target.
   - A Sigil host without the BookContainer text API now stops with a
     localized error instead of finishing without changes.

   ## Removed

   - Regex rule templates in the rule editor.
   - The Checkpoint banner on the file-scope page. Applying changes still asks
     for the Checkpoint confirmation.
   - The "Diagnose mixed scripts" and "Compare official configs to classify
     changes" switches. Saved values are ignored.
   - The "Accept/Skip language tag group" buttons. Deciding one language tag
     change still decides its whole group.
   - The strict rule-import mode. Invalid records are always skipped and
     reported with their record numbers; a structurally broken JSON file still
     fails.
   - "From current settings" in the profile window, the rule set default
     direction and scope settings (new rules always start with the current
     direction and Global scope), the Jieba "Details" button, and the
     "Checking Jieba" notices in the rule and profile windows.
   - Profile summary and comparison rows for settings that have no effect.
   - The status filter in the history window.
   - The separate dictionary inspector. Its OpenCC comparison output is now
     part of the rule **Test** page.
   - The "rules belong to another book or profile" banner. Such rules are still
     labeled in the list.
   - The rule set settings dialog. Rule sets can no longer be disabled from the
     window; a set that is already disabled shows a **Re-enable** button.
   - JSON rule field aliases `pattern` and `replacement`. Files that use them
     now fail with an unknown-field error; use `source` and `target`.
   - The warning for legacy quoted TSV fields. Such fields are imported
     unchanged.
   ```
3. `## Automated validation` 一节的原文
   ```
   The release candidate passed the local repository gate. The tagged workflow
   builds and validates the Fat Plugin and six platform packages, runs all six
   runtime smoke jobs, verifies package checksums, and attests release assets
   before publishing.
   ```
   改为：
   ```
   The release candidate passed `make check` (861 passed, 1 skipped) and the
   real-Qt acceptance script (13/13). The tagged workflow run
   [36649657631](https://github.com/liyafly/OpenCCForSigil/actions/runs/36649657631)
   built and validated the Fat Plugin and six platform packages, ran all six
   runtime smoke jobs, verified package checksums, and attested release assets
   before publishing. These checks do not run the plugin inside Sigil.
   ```
4. `CHANGELOG.md` 的 `## 0.2.11 - 2026-09-30` 一节：
   - 把 `### Changed` 里“while preserving legacy saved-profile behavior.”改为“Saved "suggest" profiles load as "update".”；
   - 在 `### Fixed` 之后追加一节 `### Removed`，内容与第 2 步 `## Removed` 下的列表逐字相同。
   - 其他行都不动，包括 D9 那一条。
5. **不要**运行 `gh release edit`。在 `04-implementation-results.md` 里写一行：“GitHub Release 正文待用户执行：`gh release edit v0.2.11 --notes-file docs/releases/v0.2.11.md`”。

**测试**
- 纯文档，没有单元测试。执行 `mise exec -- make check`，确认 `plugin metadata valid (0.2.11)` 仍然输出。

**验收标准**
- [ ] `grep -n "retaining legacy\|preserving legacy" docs/releases/v0.2.11.md CHANGELOG.md` 无输出。
- [ ] `grep -c "^## Removed\|^## Behavior changes" docs/releases/v0.2.11.md` 输出 `2`。
- [ ] `grep -n "36649657631" docs/releases/v0.2.11.md` 有输出。
- [ ] 版本号文件（`app/version.py`、`plugin.xml`、`pyproject.toml`、`uv.lock`）没有改动：`git diff --stat HEAD -- plugin/OpenCCForSigil/app/version.py plugin/OpenCCForSigil/plugin.xml pyproject.toml uv.lock` 无输出。

**不要做**
- 不改版本号，不打新标签，不移动 `v0.2.11` 标签，不发布（全局约束 6、15）。
- 不改 `## Download`、`## Remaining acceptance`。
- 不改 CHANGELOG 里 0.2.10 及更早的版本。

---

## FU-06（P3，工具）后续提交弄坏的 8 个工具入口

**位置和原因**

| 工具 | 行 | 报错 | 弄坏它的提交 |
| --- | --- | --- | --- |
| `docs/reviews/2026-09-28/scripts/ux/probe_ux_simplicity.py` | `:179` | `TypeError: choose_scope() got an unexpected keyword argument 'nav_available'` | `1bc5505`（SIMP-28） |
| `docs/reviews/2026-09-28/scripts/perf/benchmark_preview_ui.py` | `:162-163`、`:177`、`:188-190` | `AttributeError: ... '_group_ids_by_file'` | `a1cba9b`（SIMP-14） |
| `docs/reviews/2026-09-27/scripts/probe_followup.py` | `:87-88`、`:101` | `AttributeError: ... 'accept_group_button'` | `a1cba9b`（SIMP-14） |
| `docs/reviews/2026-09-24/scripts/round3/a10_export_roundtrip.py` | `:12-13` | `TypeError: import_rules() got an unexpected keyword argument 'strict'` | `d9e0705`（SIMP-15） |
| `docs/reviews/2026-09-26/scripts/test_review_regressions.py` | `:198` | `test_r12_lenient_json_import_keeps_valid_records_and_reports_bad_record` 失败 | `d9e0705` |
| `docs/reviews/2026-09-28/scripts/rules/rule06_import_formats.py` | `:16` | 每个用例都打印 `TypeError ... 'strict'` | `d9e0705` |
| `docs/reviews/2026-09-28/scripts/rules/probe_edge_cases.py` | `:52` | 同上 | `d9e0705` |
| `docs/reviews/2026-09-29/scripts/rules/fix07_fix08_import_edges.py` | `:19`、`:35` | 同上 | `d9e0705` |

修复前的输出：`evidence/tools/check_entrypoints.out`。

**修改方法**（全局约束 9：只改入口，不改断言）
1. `probe_ux_simplicity.py:179`：原文 `services=services, metadata_available=True, nav_available=True,` 改为 `services=services, metadata_available=True,`。
2. `benchmark_preview_ui.py`：`_group_ids_by_file` 已被 SIMP-14 删除，删掉写入它的三处代码。这三处只是给已删除的属性赋值，测量步骤不变。
   - 删掉 `:162-163` 两行：
     ```python
             grouped_ids_by_file = {key: set(value)
                                    for key, value in dialog._group_ids_by_file.items()}
     ```
   - 删掉 `:177` 一行：
     ```python
                 grouped_ids_by_file.setdefault(file_id, set()).add(group_id)
     ```
   - 删掉 `:188-190` 三行：
     ```python
             dialog._group_ids_by_file = {
                 key: frozenset(value) for key, value in grouped_ids_by_file.items()
             }
     ```
   - `:174` 的 `file_id = pair[0][1].file_id` 仍被 `grouped_file_ids[group_id]` 使用，保留。
3. `probe_followup.py` 的 `probe_group_semantics()`：按 D15 改写，两种改法各用一次。
   - `:87-88` 原文：
     ```python
         language_button_visible = dialog.accept_group_button.isVisible()
         dialog.accept_group_button.click()
     ```
     改为“X 不存在”：
     ```python
         language_button_visible = hasattr(dialog, "accept_group_button")
     ```
     后面的 `passed` 仍要求 `not language_button_visible`，以及 `after_hidden_language_button` 全部为 None，这两条断言都不动。
   - `:101` 原文 `    mixed.accept_group_button.click()` 改为“改到新位置”：单击语言项，用“接受此项”决定整个组，断言内容不变。
     ```python
         language_row = next(
             index for index, (_preview, item) in enumerate(mixed._visible_entries_cache)
             if item.change_id == "change-0")
         mixed._set_current_row(language_row)
         mixed.accept_this_button.click()
     ```
4. 删掉 `strict=False` 参数。SIMP-15 之后，唯一剩下的行为就是原来的非 strict 行为，所以这只是改入口。
   - `a10_export_roundtrip.py:12-13`：`direction="s2twp",\n                          strict=False)` 改为 `direction="s2twp")`。
   - `test_review_regressions.py:198`：`format="json", strict=False)` 改为 `format="json")`。
   - `rule06_import_formats.py:16`：`import_rules(text, strict=False, **kw)` 改为 `import_rules(text, **kw)`。
   - `probe_edge_cases.py:52`：`direction="s2t", strict=False)` 改为 `direction="s2t")`。
   - `fix07_fix08_import_edges.py:19`：`import_rules(text, strict=False, **kw)` 改为 `import_rules(text, **kw)`；`:35`：`format="tsv", strict=False)` 改为 `format="tsv")`。
5. 提交说明逐条列出上面每处改动，格式为“只改入口：<文件:行> <原文> → <新文>”。第 3 步的两处写“按 D15 改写：<文件:行> 原断言 → 新断言”。

**验收标准**
- [ ] `sh docs/reviews/2026-09-30/scripts/tools/check_entrypoints.sh` 的 8 行都是 `exit=0`，行尾没有错误信息。
- [ ] `probe_ux_simplicity.py` 的输出里，所有 `enter_in_filter_*_accepted` 都是 `false`（UXS-02）。
- [ ] `probe_followup.py` 输出的 `group_semantics.assertions_passed` 为 `true`，`mixed_language_button_decisions` 为 `{"change-0": "accept_this", "change-1": null}`。
- [ ] `test_review_regressions.py`：16 passed。

**验证命令**
```sh
sh docs/reviews/2026-09-30/scripts/tools/check_entrypoints.sh
```

**不要做**
- 不改这些脚本里的任何断言或期望值（第 3 步的 D15 改写除外）。
- 不改 `evidence/` 下的任何文件。
- 不动 2026-09-23 round2 的脚本（D20）。

---

## FU-07（P3，工具与测试）恢复被删掉或削弱的检查

全局约束 13 只允许两种改法：把“X 存在”改为“X 不存在”，或者把检查改到新位置、内容不变。下面 7 处都违反了这条约束，逐条恢复。

**修改方法**
1. **`docs/reviews/2026-09-27/scripts/check_preview_layout.py:130-131`**（`c20bc9d`，SIMP-02）：原来检查“旧批量标签不在菜单里”，这条被换成了上一行的重复。改为 D15 的“X 不存在”。
   原文：
   ```python
       assert menu_labels.count(translator.text("preview.batch_decide")) == 1
       assert menu_labels.count(translator.text("preview.batch_decide")) == 1
   ```
   改为：
   ```python
       assert menu_labels.count(translator.text("preview.batch_decide")) == 1
       assert not any(hasattr(dialog, name) for name in (
           "accept_file_button", "reject_file_button", "accept_filter_button",
           "reject_filter_button", "accept_all_button", "reject_all_button",
       ))
   ```
2. **同一文件 `:358-360`**（`865c29f`）：恢复被删掉的“混合对话框里，按文件批量接受会接受本文件的规则组”。放在 Undo/Redo 检查之后、`dialog.dialog.hide()` 之前。
   原文：
   ```python
       assert previews[1].decision(language_changes[1].change_id).value == "accept_this"
       assert all(previews[0].decision(change.change_id) is None for change in rule_changes)
       dialog.dialog.hide()
   ```
   改为：
   ```python
       assert previews[1].decision(language_changes[1].change_id).value == "accept_this"
       assert all(previews[0].decision(change.change_id) is None for change in rule_changes)
       complete_batch_dialog(qt, app, translator, dialog, scope="file")
       app.processEvents()
       assert all(previews[0].decision(change.change_id).value == "accept_this"
                  for change in rule_changes)
       dialog.dialog.hide()
   ```
   再在该函数的返回字典里，`"file_batch_action_still_accepts_rule_changes_and_undoes": True,`（`:396`）的下一行加 `"file_batch_completes_local_rule_group": True,`。
3. **`docs/reviews/2026-09-27/ui-workflow/scripts/check_run_summary.py`**（`1bc5505`，SIMP-28）：“未生效原因一列的 tooltip 等于全文”原来只在 NAV 行上检查，NAV 行删除后这条检查也跟着没了。改到 force-pivot 行，内容不变。
   - `:144` 原文 `                        assert "a-long-rule-set-id" in rules_tooltip` 的下一行插入：
     ```python
                             pivot_label = translator.text("options.force_pivot")
                             pivot_row = next((row for row in range(table.rowCount())
                                               if table.item(row, 0).text() == pivot_label), None)
                             if pivot_row is not None:
                                 detail.setdefault("pivot_reason_tooltips", []).append((
                                     table.item(pivot_row, 3).toolTip(),
                                     table.item(pivot_row, 3).text()))
     ```
   - `:240-241` 原文：
     ```python
                         assert translator.text("options.not_effective_reason").split("{")[0] in \
                             detail["inactive_pivot_effective"]
     ```
     的下一行插入：
     ```python
                         pivot_tooltip, pivot_text = detail["pivot_reason_tooltips"][-1]
                         assert pivot_tooltip == pivot_text
                         assert translator.text("options.not_effective_reason").split("{")[0] \
                             in pivot_tooltip
     ```
4. **`docs/reviews/2026-09-29/scripts/rules/fix14_menu_tooltip_qt.py`**（`b87d679`，SIMP-25）：脚本被改成检查已停用的集 A，不再检查 default 集。加回对 default 集的检查，原有的输出行保留。
   在 `:29` 原文 `print("menu actions:", [a.text() for a in w.ruleset_menu.actions()])` 的**前面**插入：
   ```python
   d = RuleManagerDialog(qt, (), translator=Translator("zh-Hans"), config="s2t", profile_id="P", book_fingerprint="B",
       rulesets=(RuleSet("default"), RuleSet("A", (Rule(id="a1", source="软件", target="軟體", direction="s2t"),))),
       ruleset_id="default", run_ruleset_ids=("default",))
   d.dialog.show(); app.processEvents()
   dact = d._ruleset_menu_actions["delete"]
   print("default set: delete action enabled:", dact.isEnabled(), "| tooltip:", dact.toolTip(),
         "| menu.toolTipsVisible():", d.ruleset_menu.toolTipsVisible())
   ```
5. **`tests/unit/test_rules_compiled.py:129-150`**（`9ce645a`，SIMP-03）：300 组随机测试的参照被换成了生产代码的 `source_matches`，这里改回独立参照 `_reference_lock_spans`（同文件 `:44`）。
   - 删掉函数开头的局部 import：`    from rules.matching import RegexBudget, source_matches` 及其后的空行。
   - 原文：
     ```python
             expected = tuple(
                 LockedSpan(match.start, match.end, text[match.start:match.end],
                            match.target, match.rule)
                 for match in source_matches(
                     text, overlay.source_rules, overlay.regex_patterns, RegexBudget())
             )
             assert lock_spans_compiled(text, overlay) == expected
     ```
     改为：
     ```python
             assert lock_spans_compiled(text, overlay) == _reference_lock_spans(
                 text, snapshot, config=config, profile_id="profile", book_fingerprint="book")
     ```
   - **只改 `:129` 这个函数。** `:262` 也有一行 `assert lock_spans_compiled(text, overlay) == expected`，那是另一个测试（前缀索引对全量扫描），不要动。
6. **`tests/unit/test_preview_group_scaling.py:127`**（`c20bc9d`）：`dialog._entries` 仍然被包成了 `VisitCountingEntries`（`:111`），但断言被删了。在 `:127` 那行的下一行加回原断言：
   ```python
       assert dialog._entries.visits <= 3 * changes_per_file + 50
   ```
7. **`tests/unit/test_regex_rules.py:228`** `test_overlapping_regex_candidates_do_not_count_as_hits`（`7d97739`，SIMP-23）：规格要求把计数断言改成“每片段计 1”，实际却直接删掉了。
   - 原文：
     ```python
         rule = _rule(id="overlap", source=r"\p{Han}+", target="X")
         regex = load_regex_module()
         budget = RegexBudget()
     ```
     改为：
     ```python
         class CountingBudget(RegexBudget):
             def __init__(self):
                 super().__init__()
                 self.fragment_counts = []

             def note_regex_hit(self, rule, position, fragment_hits):
                 super().note_regex_hit(rule, position, fragment_hits)
                 self.fragment_counts.append(dict(fragment_hits))

         rule = _rule(id="overlap", source=r"\p{Han}+", target="X")
         regex = load_regex_module()
         budget = CountingBudget()
     ```
   - 在函数末尾 `assert len(hits) == 1` 的下一行加：
     ```python
         assert budget.fragment_counts == [{"overlap": 1}]
     ```
8. 提交说明逐条写“按 D15 恢复：<文件:行> 被删的检查 → 恢复后的检查”。

**验收标准**
- [ ] `mise exec -- uv run pytest tests/unit/test_rules_compiled.py tests/unit/test_preview_group_scaling.py tests/unit/test_regex_rules.py -q` 全部通过，已在试做中确认。如果不通过，按全局约束 18 停下来。
- [ ] 真实 Qt：`check_preview_layout.py --verify`、`check_run_summary.py --verify --language en` 和 `--language zh-Hans` 都退出 0。
- [ ] `fix14_menu_tooltip_qt.py` 输出中有这一行：`default set: delete action enabled: False | tooltip: 默认规则集不能删除。 | menu.toolTipsVisible(): True`。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_compiled.py tests/unit/test_preview_group_scaling.py tests/unit/test_regex_rules.py -q
QT="mise exec -- uv run --with PySide6==6.11.2 python"
QT_QPA_PLATFORM=offscreen $QT docs/reviews/2026-09-27/scripts/check_preview_layout.py --verify --output /tmp/opencc-fu07-preview
for l in en zh-Hans; do
  QT_QPA_PLATFORM=offscreen $QT docs/reviews/2026-09-27/ui-workflow/scripts/check_run_summary.py --verify --language $l --output /tmp/opencc-fu07-summary-$l
done
QT_QPA_PLATFORM=offscreen $QT docs/reviews/2026-09-29/scripts/rules/fix14_menu_tooltip_qt.py
```

**不要做**
- 不放宽本节以外的任何断言。
- 不改 `check_profile_layout.py`（01 里记录的那条空断言只记录，不改）。
- 不改产品代码。

---

## FU-08（P3，文案与校验器）指南仍写“沙箱”和已删除的“词典检查器”；校验器少一个键

**位置与原文 → 新文**（行号为 `3107f27` 上的行号；每一行只替换引号里的片段，行的其余部分不动）

`plugin/OpenCCForSigil/resources/rule-guide.md`（随插件发布，用户能看到）：

| 行 | 原文片段 | 新文片段 |
| --- | --- | --- |
| 5 | `“规则 / 沙箱”` | `“规则与测试”` |
| 50 | `再用沙箱检查周围正文` | `再在“测试”页检查周围正文` |
| 67 | `在沙箱输入有代表性的文本` | `在“测试”页输入有代表性的文本` |
| 70 | `只读词典检查器用于查看 OpenCC 转换结果，不会修改词典。` | `“测试”页还会列出各 OpenCC 配置的比较结果，只用于查看，不会修改词典。` |
| 74 | `「規則 / 沙箱」` | `「規則與測試」` |
| 90 | `若檔案首列有標題，` | `若檔案第 1 列是表頭，` |
| 119 | `再用沙箱檢查周圍正文` | `再在「測試」頁檢查周圍正文` |
| 136 | `在沙箱輸入有代表性的文字` | `在「測試」頁輸入有代表性的文字` |
| 139 | `唯讀詞典檢查器用來查看 OpenCC 轉換結果，不會修改詞典。` | `「測試」頁還會列出各 OpenCC 設定的比較結果，只用於查看，不會修改詞典。` |
| 143 | `Open **Rules / sandbox** from` | `Open **Rules & test** from` |
| 188 | `then test nearby prose in the sandbox.` | `then check nearby prose on the **Test** page.` |
| 205 | `Enter representative text in the sandbox and select **Test**.` | `On the **Test** page, enter representative text and select **Test**.` |
| 208 | `The read-only dictionary inspector shows OpenCC output and does not edit its dictionaries.` | `The **Test** page also lists OpenCC comparison output for reference; it does not edit dictionaries.` |

维护文档：

| 文件:行 | 原文片段 | 新文片段 |
| --- | --- | --- |
| `docs/rule-format.md:5` | `the manager/sandbox/inspector.` | `the rule manager and its **Test** page.` |
| `docs/rule-format.md:46` | `and test nearby prose in the sandbox.` | `and check nearby prose on the **Test** page.` |
| `docs/rule-format.md:48` | `open **Rules / sandbox** and add a` | `open **Rules & test** and add a` |
| `docs/rule-format.md:60` | `Then enter representative text in the sandbox,` | `Then enter representative text on the **Test** page,` |
| `docs/README.md:32` | `Manage profiles, rules, sandbox, and inspector` | `Manage profiles, rules, and rule tests` |
| `README.md:20` | `  a text sandbox, and independent official-config inspection;` | `  and a rule test page with official-config comparison;` |
| `docs/testing.md:12` | `preflight-only run = success with zero BookContainer writes when no text API exists` | `missing BookContainer text API = localized error (error.book_api_unavailable) with zero writes` |

`docs/rules-and-profiles.md:65-68`，原文（4 行）：
```
saving. The text-only sandbox displays rule and conversion stages. The
read-only inspector independently compares official configs on the original
input and labels the result as comparative classification, never as an
internal dictionary-hit trace.
```
改为：
```
saving. The **Test** page displays rule and conversion stages, then compares
official configs on the original input and labels the result as comparative
classification, never as an internal dictionary-hit trace.
```

校验器：`tools/validate_artifact.py:196`，在 `        "result.status.noop",` 的下一行加 `        "result.status.cancelled_unchanged",`。这是 SIMP-04 C 组要求而没做的一项；三份 i18n 里都已有这个键。

**测试**
- 在 `tests/unit/test_i18n.py` 文件末尾追加（修复前会失败）：
  ```python
  def test_rule_guide_uses_the_test_page_wording():
      guide = (Path(__file__).resolve().parents[2] / "plugin" / "OpenCCForSigil"
               / "resources" / "rule-guide.md").read_text(encoding="utf-8").casefold()
      for term in ("沙箱", "sandbox", "词典检查器", "詞典檢查器", "dictionary inspector"):
          assert term not in guide, term
  ```
  `Path` 已在该文件第 2 行 import。
- 在 `tests/unit/test_artifact_validator.py` 文件末尾追加（修复前会失败）：
  ```python
  def test_required_i18n_keys_include_cancelled_unchanged_status():
      assert "result.status.cancelled_unchanged" in _I18N_REQUIRED_KEYS
  ```
  `_I18N_REQUIRED_KEYS` 已在该文件 `:12-13` import。

**验收标准**
- [ ] `grep -n "沙箱\|sandbox\|词典检查器\|詞典檢查器\|dictionary inspector" plugin/OpenCCForSigil/resources/rule-guide.md` 无输出。
- [ ] `grep -n "sandbox\|inspector" docs/rule-format.md docs/rules-and-profiles.md docs/README.md README.md` 无输出。
- [ ] 两个新测试都通过；`mise exec -- make check` 通过，其中包括 `tools/build_plugin.py --check` 对打包内容的校验。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_i18n.py tests/unit/test_artifact_validator.py -q
grep -n "沙箱\|sandbox\|词典检查器\|詞典檢查器\|dictionary inspector" plugin/OpenCCForSigil/resources/rule-guide.md
```

**不要做**
- 不改 i18n 文案，也不新增键（本条只改指南和维护文档）。
- 不改 `docs/OpenCCForSigil_Spec_v1.4/` 和 `docs/deviations.md`。
- 不改 `docs/reviews/` 下的旧文档。

---

## FU-09（P3，记录）追加 2026-09-29 更正，新建本轮结果

**修改方法**
1. 在 `docs/reviews/2026-09-29/04-implementation-results.md` **末尾**追加一节 `## 2026-09-30 corrections (append-only)`（全局约束 10：只追加）。内容逐条引用 [01](01-acceptance-audit.md) 的“自报与实际不符”第 1–11 条和“过程问题”，每条一行，写明 `3107f27` 上的事实，并在末尾注明“详见 docs/reviews/2026-09-30/01-acceptance-audit.md”。另外写上以下各行：
   - `746771f`：计划外的性能提交，按 D19 保留；它的失败测试是 `test_all_scope_undecided_batch_reuses_entries_without_decision_scan`。
   - SIMP-23 第 4 步：按 D17 本轮不做。
   - SIMP-07 新增的 `LiteralPrefixIndex.single_char_buckets`：按 D18 保留，记为偏离原意。
   - SIMP-03 删掉了非字符串检查：按 D21 记录。
   - 2026-09-23 round2 的 `s1_jieba_loop.py`、`s2_direction_reset.py`、`s3_commit_progress.py`、`s4_future_schema.py`、`s6_stale_prefs.py`、`l07_eq.py`：按 D20 标为已退役，原因分别是 SIMP-01、SIMP-16、SIMP-03。
2. 新建 `docs/reviews/2026-09-30/04-implementation-results.md`，按 README“全局约束 17”的格式记录每批结果。第一节写基线 `3107f27` 的数字（861 passed、1 skipped；真实 Qt 13/13）。
3. 不要修改 `docs/reviews/2026-09-29/04-implementation-results.md` 已有的任何一行：`git diff` 里只能有 `+` 行。

**验收标准**
- [ ] `git diff HEAD~1 -- docs/reviews/2026-09-29/04-implementation-results.md | grep '^-[^-]'` 无输出。
- [ ] 新的 `04-implementation-results.md` 里，每批都贴有 `make check` 的 passed/skipped 数和 `acceptance.json` 的 FAIL 数。
- [ ] 有一行写明“GitHub Release 正文待用户执行”（FU-05 第 5 步）。
- [ ] 有一行写明“Sigil 宿主验收：Not verified”。
- [ ] 末尾列出 README 的 U1–U4，每项标为“待用户”。

**不要做**
- 不改前几轮的 `evidence/`，也不改本目录的 `evidence/`。
- 不删除或重写 2026-09-29 04 里的任何原有行。
