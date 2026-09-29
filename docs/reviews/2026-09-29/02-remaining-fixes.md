# 02 剩余工作：FIX-01 至 FIX-18

基线 `6d74b25`。先读 [README](README.md) 的全局约束（包括新增的第 9–12 条）、术语表和批次顺序。

**写法说明**
- 行号都是 HEAD 上的行号。改动前先用 `grep -n` 确认位置；如果行号已经变了，以函数名为准。
- 每条都要先写测试，在修复前确认它失败，再改代码（全局约束 11）。
- 复现脚本在 `scripts/` 下，修复前的输出在 `evidence/` 下。修复后的输出写到 `/tmp/`，与 `evidence/` 对照。

---

## FIX-01（P1，RULE-05 漏项）跨规则集冲突时点“分析并预览”没有任何反应

**位置**
- `plugin/OpenCCForSigil/ui/preview_window.py:3925` `_ConversionConfigDialog._accept()`：`:3937-3946` 只捕获 `ValueError`。
- `ui/run_options.py:346-349` `RunOptionsPanel.validate()`：调用 `self._services.freeze_rules(profile)`。
- `ui/run_options.py:598` `RunOptionsPanel._tool()`：`:644` 只捕获 `(ValueError, OSError)`。“选择方案…”会走 `app/settings.py:255-267`，其中也调用 `freeze_rules`。
- `app/settings.py:455-482` `freeze_rules()`：抛出 `app.errors.RuleConflictError`。
- `app/errors.py:26`：`RuleConflictError(PluginError)`，`PluginError` 继承 `Exception`，**不是** `ValueError`。
- `app/controller.py:883` `_rule_conflict_summary()`：本地化文案只有 controller 的通用错误路径用得到，UI 路径到不了。
- `ui/i18n.py:105` `settings_error_message()`。

**现状**
- `scripts/rules/fix01_analyze_conflict_fakeqt.py` → `EXCEPTION escapes _accept: RuleConflictError blocking rule conflicts: a1 (A), b1 (B) | is ValueError: False`
- `scripts/rules/fix01_analyze_conflict_qt.py`（真实 Qt）→ 控制台打出 traceback，随后 `after click: accepted = False | dialog visible = True | message boxes = []`。用户看到的是按钮点了没反应。
- 这个问题配合 RULE-02 更容易出现：旧 V1 规则集和新 V2 规则集里的同源异目标规则，现在会成为阻断冲突。

**期望**
- 点击后弹出本地化说明（键 `error.rule_conflict`，已存在），内容包含 `a1 (A), b1 (B)`，对话框保持打开，`accepted` 为 False。
- “选择方案…”遇到冲突时同样处理。

**修改方法**
1. `ui/i18n.py`，在 `settings_error_message` 之前新增函数：
   ```python
   def rule_conflict_message(translator: Translator, error: BaseException) -> str:
       groups = "; ".join(
           ", ".join(f"{rule_id} ({ruleset_id})" for rule_id, ruleset_id in group)
           for group in getattr(error, "conflict_groups", ())
       )
       return translator.text("error.rule_conflict", rules=groups)
   ```
2. `settings_error_message()` 的第一行（`detail = str(error)` 之前）加：
   ```python
   if getattr(error, "code", None) == "RULE_CONFLICT_ERROR":
       return rule_conflict_message(translator, error)
   ```
   这里用 `code` 判断，这样 `ui/i18n.py` 不用 import `app.errors`。
3. `app/controller.py:883`：`_rule_conflict_summary` 的函数体改为 `return rule_conflict_message(translator, error)`，并在文件顶部的 `from ui.i18n import …` 中加入 `rule_conflict_message`。文案只保留 i18n 这一份。
4. `ui/preview_window.py` `_accept()`：在函数开头已有的局部 import 旁加 `from app.errors import RuleConflictError`，把 `except ValueError as exc:` 改为 `except (ValueError, RuleConflictError) as exc:`。`except` 块里已有的 `show_error_details(..., settings_error_message(self._translator, exc), str(exc))` 不用改。
5. `ui/run_options.py:644`：把 `except (ValueError, OSError) as exc:` 改为 `except (ValueError, OSError, RuleConflictError) as exc:`，并在 `_tool()` 开头加局部 import `from app.errors import RuleConflictError`（与 `:599` 的写法一致）。

**测试**
- `tests/unit/test_i18n.py::test_settings_error_message_localizes_rule_conflict`
  ```python
  error = RuleConflictError(((("a1", "A"), ("b1", "B")),))
  for language in ("en", "zh-Hans", "zh-Hant"):
      tr = Translator(language)
      assert settings_error_message(tr, error) == tr.text("error.rule_conflict", rules="a1 (A), b1 (B)")
  ```
- `tests/unit/test_run_options.py::test_analyze_with_cross_ruleset_conflict_shows_localized_error`
  - 照抄 `scripts/rules/fix01_analyze_conflict_fakeqt.py` 的构造，把临时目录换成 `tmp_path`。
  - 用 `monkeypatch.setattr(preview_window, "show_error_details", lambda *a: shown.append(a[3]))` 记录调用。
  - 断言：`dialog._accept()` 不抛异常；`dialog.accepted is False`；`shown == [Translator("en").text("error.rule_conflict", rules="a1 (A), b1 (B)")]`。
- `tests/unit/test_run_options.py::test_profile_pick_with_conflicting_rulesets_shows_localized_error`
  - 构造 `RunOptionsPanel`，写法参照同文件中已有的、传入 services 的测试。
  - services 的 `pick_profile` 返回任意 `Profile()`，`validate_profile` 抛出 `RuleConflictError(((("a1","A"),("b1","B")),))`。
  - monkeypatch `ui.run_options.show_error_details` 记录调用，然后调用 `panel._tool("profiles")`。
  - 断言不抛异常，且记录下的 summary 等于上一条测试的期望文案。

**验收标准**
- [ ] `fix01_analyze_conflict_fakeqt.py` 输出 `accept returned; accepted= False shown= [...]`，且 shown 里含 `a1 (A), b1 (B)`。
- [ ] `fix01_analyze_conflict_qt.py` 输出中没有 Traceback，`message boxes` 里有一条 `error_details`。
- [ ] 三种语言的文案都来自 `error.rule_conflict`，没有英文原始异常。
- [ ] controller 的通用错误路径仍然显示同一段文案（`tests/integration/test_ruleset_persistence.py::test_freeze_rules_reports_cross_ruleset_conflict_with_ruleset_ids` 通过）。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_i18n.py tests/unit/test_run_options.py tests/integration/test_ruleset_persistence.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix01_analyze_conflict_fakeqt.py \
  && QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-29/scripts/rules/fix01_analyze_conflict_qt.py
```

**不要做**
- 不放宽冲突校验，不跳过 `freeze_rules`。
- 不在 `_accept()` 里捕获 `Exception`。
- 不把冲突说明改成英文原始异常。

---

## FIX-02（P1，RULE-12 缺陷，丢数据）删除规则集后，保存前复用同一个 ID，保存时文件被删

**位置**
- `ui/rules_window.py:1160`（`_new_ruleset`）和 `:1194`（`_rename_ruleset`）：只检查 `identifier in self._rulesets`，不检查 `self._deleted`。
- `ui/rules_window.py:1225-1262` `_delete_ruleset()`：把 ID 加入 `self._deleted`。
- `app/settings.py:343-359` `edit_rules()`：先保存 `result_sets` 中的每个规则集（`:343-346`），再对 `deleted` 调用 `_remove_ruleset_references`（`:358-359`）。后者最终执行 `self.rules.delete(identifier)`（`:427-428`），把刚保存的文件删掉。

**现状**（`scripts/rules/fix02_fix03_ruleset_rename_delete.py`，`evidence/rules/fix02_fix03_ruleset_rename_delete.out`）
- B 段：删除 X → 新建 X → 加规则 → 保存。结果 `window result: sets = ['default', 'X'] deleted = ('X',)`，`X.json exists after save: False`，新规则全部丢失。
- C 段：删除 X → 把 Y 改名为 X → 保存。结果 `files: []`，Y 的规则 `y1` 丢失。

**期望**
- 窗口里不允许在保存前复用已删除的 ID，弹出“规则集已存在”的警告。
- `edit_rules()` 也要防御：同一个结果里既保存又删除的 ID，一律不删除。

**修改方法**
1. `ui/rules_window.py` `_new_ruleset()`：把 `if identifier in self._rulesets:` 改为 `if identifier in self._rulesets or identifier in self._deleted:`，命中后仍走 `self._warn(self._labels["duplicate_ruleset"])`。
2. `_rename_ruleset()`：同样修改。
3. `app/settings.py` `edit_rules()`：在 `deleted = tuple(dict.fromkeys(result.deleted))`（`:346`）之后加一行：
   ```python
   deleted = tuple(item for item in deleted if item not in {s.id for s in result_sets})
   ```
4. 不新增 i18n 键，复用 `rules.duplicate_ruleset`。

**测试**
- `tests/unit/test_rules_window.py::test_deleted_ruleset_id_cannot_be_reused_before_save`
  - 窗口里有 default 和 mine 两个规则集，删除 mine（用 monkeypatch 让 `ask_confirmation` 返回 True）。
  - 让 `QInputDialog.getText` 返回 `("mine", True)` 后调用 `_new_ruleset()`，断言 `"mine" not in manager._rulesets`，且发出过一次警告。
  - 再选中 default，同样调用 `_rename_ruleset()`，断言 `"mine" not in manager._rulesets`。
- `tests/integration/test_ruleset_persistence.py::test_edit_rules_never_deletes_a_ruleset_saved_in_same_result`
  - 构造 `RuleWindowResult("X", (RuleSet("default"), RuleSet("X", (rule,))), run_ruleset_ids=("default", "X"), deleted=("X",))`。
  - 执行 `edit_rules` 后，断言 `RuleStore(...).load("X").rules == (rule,)`。

**验收标准**
- [ ] 重跑 `fix02_fix03_ruleset_rename_delete.py`：B 段在新建 X 时被拒绝；如果改脚本绕过窗口直接给结果，`X.json` 仍然存在。C 段 Y 的规则不丢。
- [ ] `test_delete_ruleset_removes_profile_references_and_file` 和 `test_cancel_after_delete_keeps_ruleset_file` 仍然通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/integration/test_ruleset_persistence.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix02_fix03_ruleset_rename_delete.py
```

**不要做**
- 不做回收站，不做“撤销删除”。
- 不改变“删除只在保存时生效”的规则。
- 不改规则集或方案文件的格式。

---

## FIX-03（P1，RULE-11 缺陷）重命名规则集后，“用于本次转换”与它脱节

**位置**
- `ui/rules_window.py:1177-1214` `_rename_ruleset()`：改了 `_rulesets`、`_renamed`、`_ruleset_profiles`，但**没有改 `self._run_ruleset_ids`**。
- `ui/rules_window.py:1425-1436` `_rule_is_active()`，以及 `:1520-1544` `_run_candidates()`：都按 `self._run_ruleset_ids` 判断。
- `app/settings.py:368-372` `edit_rules()`：用 `renamed` 把 `run_ruleset_ids` 再映射一次。

**现状**
- `evidence/rules/fix02_fix03_ruleset_rename_delete.out` A 段：
  - 把 A 改名为 B 后，`_run_ruleset_ids = ('default', 'A')`，勾选框显示未勾选，规则 a1 显示“规则集未被本次引用”。
  - 用户勾上再取消，结果仍是 `('default', 'B')`，没法把它移出本次。
- A2 段：改名前能看到冲突、“保存”被禁用；改名后冲突消失、“保存”可用。保存后 freeze 抛出 `RuleConflictError`。
- `evidence/rules/fix03_fix05_rename_new_confirm.out` A3 段：把 A 改名为 B，再新建一个 A，新 A 的勾选框显示已勾选，实际结果是 `('default', 'B')`。

**期望**
- 窗口内的 `_run_ruleset_ids` 始终使用当前 ID。
- `edit_rules()` 不再对窗口返回的 `run_ruleset_ids` 做第二次映射。

**修改方法**
1. `_rename_ruleset()`：在 `self._ruleset_id = identifier`（`:1207`）之前加：
   ```python
   self._run_ruleset_ids = tuple(dict.fromkeys(
       identifier if item == old else item for item in self._run_ruleset_ids))
   ```
2. `app/settings.py` `edit_rules()`：在 `run_ruleset_ids is not None` 分支（`:368-372`）中，去掉 `replacements.get(item, item)` 映射，改为：
   ```python
   updated_rule_ids = tuple(dict.fromkeys(
       identifier for identifier in run_ruleset_ids if identifier not in deleted))
   ```
   `previous_rule_ids` 的映射（`:362-363`）保留，因为它用来判断哪些是“新加入”的。
3. `run_ruleset_ids is None` 的旧分支先不动，SIMP-05 会删掉它。

**测试**
- `tests/unit/test_rules_window.py::test_rename_keeps_use_in_run_state_and_conflicts`
  - 规则集 A 含规则 `软件→軟體`，B 含规则 `软件→軟件`，`run_ruleset_ids=("A", "B")`，当前是 A。
  - 切到 B，改名为 B2。断言 `manager._run_ruleset_ids == ("A", "B2")`、`manager.use_in_run_check.isChecked()`。
  - 切回 A，断言 `manager.conflict_list.count() == 1` 且 `not manager.apply_button.isEnabled()`。
- `tests/integration/test_ruleset_persistence.py::test_run_ids_from_window_are_not_remapped_after_rename`
  - 构造 `RuleWindowResult("B", (RuleSet("default"), RuleSet("B"), RuleSet("A")), renamed=(("A", "B"),), run_ruleset_ids=("default", "B", "A"))`。
  - 已有 `A.json`，方案引用 `("default", "A")`。执行后断言 `settings.active.ruleset_ids == ("default", "B", "A")`。

**验收标准**
- [ ] 重跑 `fix02_fix03_ruleset_rename_delete.py`：
  - A 段改名后 `use_in_run checked = True`，勾上再取消后，结果不再包含 B；
  - A2 段改名后 `conflicts listed = 1 save enabled = False`。
- [ ] 重跑 `fix03_fix05_rename_new_confirm.py`：A3 段新建的 A `use_in_run checked = False`。
- [ ] R-01 和重命名的现有用例全部通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/integration/test_ruleset_persistence.py tests/unit/test_profiles_m3.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix02_fix03_ruleset_rename_delete.py \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix03_fix05_rename_new_confirm.py
```

**不要做**
- 不把本次引用持久化到偏好设置。
- 不改 `RuleWindowResult` 的字段。

---

## FIX-04（P2，RULE-05 缺陷）切到一个与冲突无关的本次规则集后，“保存”又可用

**依赖**：FIX-03。

**位置**：`ui/rules_window.py:1343-1374` `_refresh()`。
- 循环里 `if not any(id(rule) in current_rule_objects …): continue` 跳过了不涉及当前规则集的冲突。
- 之后 `self.apply_button.setEnabled(not any(conflict.blocking for conflict in conflicts))` 只看到当前集的冲突。

**现状**（`scripts/rules/fix04_switch_ruleset_reenables_save.py`）
- 本次使用 A、B、C 三个集，在 A 中新增一条与 B 冲突的规则：`viewing A: conflicts 1 save enabled False`。
- 切到 C：`viewing C: conflicts 0 save enabled True`。
- 保存成功，保存后的规则集之间仍有阻断冲突。

**期望**：“保存”作用于整个窗口的全部规则集。只要本次引用的规则集之间还有阻断冲突，无论当前显示哪个集，“保存”都要禁用，并在冲突列表里写明是哪两个集。

**修改方法**
1. `_refresh()`：先计算 `run_blocking = blocking_conflicts(run_candidates)`。
2. 循环改为遍历 `run_blocking`：
   - 涉及当前集的冲突，仍然用 `rules.conflict_other_ruleset` 显示，写法不变；
   - 不涉及当前集的冲突，用新键 `rules.conflict_between_rulesets` 显示：
     - zh-Hans：“规则集 {rulesets} 之间冲突：{detail}”
     - zh-Hant：“規則集 {rulesets} 之間衝突：{detail}”
     - en：“Rule sets {rulesets} conflict: {detail}”
   - `{rulesets}` 为涉及的规则集名称，用“、”（en 用 “, ”）连接。
3. 保存按钮：
   ```python
   self.apply_button.setEnabled(not any(c.blocking for c in conflicts) and not run_blocking)
   ```

**测试**：`tests/unit/test_rules_window.py::test_uninvolved_run_ruleset_view_keeps_save_blocked`
- 照抄 `fix04_switch_ruleset_reenables_save.py` 的构造。
- 切到 C 后断言 `not manager.apply_button.isEnabled()`，且 `manager.conflict_list.count() == 1`，这一项的文字包含 “A” 和 “B”。

**验收标准**
- [ ] 重跑脚本，得到 `viewing C: conflicts 1 save enabled False`。
- [ ] 本次没有引用的规则集之间的冲突，仍然不阻断保存（`test_conflicts_in_an_unselected_direction_do_not_block_this_run` 通过）。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/unit/test_i18n.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix04_switch_ruleset_reenables_save.py
```

**不要做**
- 不对本次未引用的规则集阻断保存。
- 不新增冲突种类。

---

## FIX-05（P2，RULE-11 违反“不要做”）确认“加入方案”时，把没问过的移除也写进了方案

**位置**：`app/settings.py:374-391` `edit_rules()`：用户回答“是”后执行 `self.profiles.save(updated)`，而 `updated` 是本次会话完整的 `ruleset_ids`。

**现状**（`evidence/rules/fix03_fix05_rename_new_confirm.out` D 段）
- 已保存的方案是 `("default", "A")`。用户在窗口里把 A 移出本次（本应只影响会话），又加入新集 N。
- 保存时只问了“把 N 加入方案 Saved？”，回答“是”后，`saved profile now: ('default', 'N')`，A 被移除了。

**期望**：回答“是”只把新加入的规则集追加到已保存的方案；移除只影响本次会话。

**修改方法**：把 `:391` 的 `self.profiles.save(updated)` 改为：
```python
saved = self.profiles.load(self.active.id)
self.profiles.save(replace(saved, ruleset_ids=tuple(dict.fromkeys(
    (*saved.ruleset_ids, *newly_added_ids)))))
```
`self.active = updated`（`:392`）保持不变。

注意：
- 重命名和删除已经在前面（`:347-359`）写进了方案文件，这里 `load` 读到的是最新内容。
- 决定 D10 已定为保留这个问题，所以只做上面的修改，不删除询问块。

**测试**：`tests/integration/test_ruleset_persistence.py::test_confirming_addition_does_not_persist_unconfirmed_removal`
- 已保存的方案 `("default", "A")`；窗口返回 `run_ruleset_ids=("default", "N")`，规则集里有 N；问题框回答“是”。
- 断言 `profiles.load("saved").ruleset_ids == ("default", "A", "N")`，且 `settings.active.ruleset_ids == ("default", "N")`。

**验收标准**
- [ ] 重跑 `fix03_fix05_rename_new_confirm.py`：D 段为 `saved profile now: ('default', 'A', 'N')`。
- [ ] E 段保存时仍只有 1 个模态框。
- [ ] `test_saved_profile_can_confirm_adding_ruleset` 和 `test_saved_profile_rejection_keeps_change_session_only` 通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/integration/test_ruleset_persistence.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix03_fix05_rename_new_confirm.py
```

**不要做**
- 不新增第二个问题框。
- 未经确认，不写入已保存的方案。

---

## FIX-06（P2，RULE-10 与 D7）新规则的方向会被固化为以前会话的方向，或静默继承 `*`

**位置**
- `app/settings.py:298-299`、`:303-305` `edit_rules()`：占位规则集用 `RuleSet(..., default_direction=base_direction(config))`。default 集一旦有了规则就会保存，会话方向随之写进文件。
- `ui/rules_window.py:1163-1168` `_new_ruleset()`，以及 `:1254-1256` `_delete_ruleset()` 的兜底：同样把会话方向写成 `default_direction`。
- `ui/rules_window.py:967-980` `_apply_rule_defaults()`：只在 `default_direction == "*"` 时才替换成当前方向。
- `ui/rules_window.py:1079-1084` `_clear_editor()`：不恢复方向。
- `ui/rules_window.py:2053` `_bulk_add()`：直接使用编辑区的方向，可能是 `*`。

**现状**
- `evidence/rules/fix06_default_direction_persist.out`：s2t 会话保存后，`default.json` 的 `default_direction` 为 `s2t`；下一次 t2s 会话打开时预选 `s2t`，新加的规则 `applies to this t2s run: False`。
- `evidence/rules/fix06_wildcard_inherit.out`：选中一条 `*` 规则再删除，下一条新规则的方向是 `*`。
- `evidence/rules/fix06_bulk_add_wildcard.out`：编辑区方向为 `*` 时，批量添加得到 `[('*','里','裡'), ('*','软件','軟體')]`。

**期望**（D7）：新规则默认使用本次转换的方向；“任意方向”只能逐条显式选择。

**修改方法**
1. `app/settings.py:298-299` 改为 `values.setdefault("default", RuleSet("default"))`，`:303-305` 改为 `values.setdefault(identifier, RuleSet(identifier))`。字段默认值就是 `*`。
2. `ui/rules_window.py` `_new_ruleset()` 中的 `default_direction=base_direction(self._config)` 改为 `default_direction="*"`；`_delete_ruleset()` 兜底中的 `RuleSet("default", default_direction=base_direction(self._config))` 改为 `RuleSet("default")`。
3. 新增辅助方法：
   ```python
   def _reset_wildcard_direction(self) -> None:
       if str(self.direction_combo.currentData()) == "*":
           self._apply_rule_defaults()
   ```
   在以下位置的末尾调用它：`_add()` 成功之后、`_update_selected()` 成功之后、`_remove()` 之后，以及 `_clear_editor()`。
   用户显式选 `*` 并提交一条规则后，下一条会回到当前方向；选的是具体方向时保持不变，符合 RULE-10 第 4 步“不重置为 `*`”。
4. `_bulk_add()`（`:2053`）：
   ```python
   bulk_direction = str(self.direction_combo.currentData() or "")
   if bulk_direction in ("", "*"):
       bulk_direction = base_direction(self._config)
   ```
   把 `bulk_direction` 传给 `import_rules(direction=...)`。
5. 已经写在磁盘上的 `default_direction` 不改写（见“不要做”）。SIMP-18 第 2 项已批准，会在批次 8 把这个设置从界面上去掉，届时编辑区一律预选当前方向，已写在磁盘上的值也就不再起作用。本条不要提前做那一步。

**测试**
- `tests/integration/test_ruleset_persistence.py::test_default_set_new_rule_direction_follows_each_session`
  - 照抄 `fix06_default_direction_persist.py`。
  - 断言第二次会话 `direction_combo.currentData() == "t2s"`，且 `default.json` 中 `default_direction == "*"`。
- `tests/unit/test_rules_window.py::test_removing_wildcard_rule_restores_current_direction`
  - 照抄 `fix06_wildcard_inherit.py`，断言下一条规则的方向为 `s2t`。
- `tests/unit/test_rules_window.py::test_bulk_paste_never_creates_wildcard_rules`
  - 照抄 `fix06_bulk_add_wildcard.py`，断言所有新规则的方向都是 `s2t`。
- 现有的 `test_new_rule_in_fresh_default_set_uses_current_direction`、`test_wildcard_direction_shows_reverse_warning` 继续通过。

**验收标准**
- [ ] 三个脚本分别输出：`[('s2t','s2t'),('t2s','t2s')]`；`next new rule direction: s2t`；批量添加的方向全部为 `s2t`。
- [ ] 显式选 `*` 仍然可以保存一条 `*` 规则，并显示反向警告。
- [ ] 已有的 `*` 规则和已保存的 `default_direction` 不被改写。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/integration/test_ruleset_persistence.py tests/unit/test_rules_m3.py -q
for s in fix06_default_direction_persist fix06_wildcard_inherit fix06_bulk_add_wildcard; do
  mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/$s.py; done
```

**不要做**
- 不迁移已保存的规则或规则集文件。
- 不删除 `*` 选项。
- 不引入“方向族”。

---

## FIX-07（P2，RULE-06 缺陷与回归）表头误判会丢弃数据行；3 列空方向行回归

**位置**
- `rules/importers.py:364-370` `_is_header()`：只看第一个字段是否在 15 个词的集合里。
- `rules/importers.py:206-208`：命中表头就 `rows.pop(0)`，不产生任何诊断。
- `rules/importers.py:213-229`：3 列行的判定。`keep_legacy_blank_direction` 只对 ≥ 4 列生效，所以 `"\t软件\t軟體"` 被当成“源为空”。
- 批量添加走同一个函数（`ui/rules_window.py:2006-2061`）。

**现状**（`evidence/rules/fix07_fix08_import_edges.out` 前 6 行，以及 `fix07_bulk_add_header.out`）
- `"备注\t備註\n软件\t軟體\n"` 只得到 1 条规则，第一行被当作表头静默丢弃，`diags=[]`。“目标”“原文”“source”开头的数据行也一样。
- `"\t软件\t軟體\n"`（旧格式，方向栏为空）：`rules=[] diags=[(1, 'error', 'source: source must not be empty')]`。0.2.8 在这种情况下使用对话框选的方向。
- 批量粘贴 `备注=備註\n软件=軟體`，只新增 `软件`，没有诊断。

**期望**
- 只有一行里**同时**出现“源”类词和“目标”类词时才算表头，并给出一条 info 诊断。
- 3 列行的第一栏为空时，按旧格式处理，方向取对话框里选的值。

**修改方法**
1. 把 `_is_header` 改为：
   ```python
   _HEADER_SOURCE = {"源", "源文本", "原文", "來源文字", "source"}
   _HEADER_TARGET = {"目标", "目标文本", "目標", "目標文字", "target"}

   def _is_header(row: list[str]) -> bool:
       cells = {value.strip().casefold() for value in row}
       return bool(cells & _HEADER_SOURCE) and bool(cells & _HEADER_TARGET)
   ```
2. `_rows_to_rules`：跳过表头时追加诊断：
   ```python
   diagnostics.append(ImportDiagnostic(
       rows[0][0], "header row skipped", "info", "line", message_key="rules.import_header_skipped"))
   ```
   `ImportDiagnostic`（`rules/importers.py:18-23`）已经有 `message_key` 字段；导入预览会按 `rules_window.py:2231` 的写法把它本地化。
   新键 `rules.import_header_skipped`：
   - zh-Hans：“第 1 行是表头，已跳过”
   - zh-Hant：“第 1 行是表頭，已略過”
   - en：“Line 1 is a header row and was skipped”

   `rules_window.py:2198-2202` 的 `discarded` 目前统计所有非 error 的诊断，会把 info 也算进去。改为只统计 `severity == "warning"` 的诊断，已有的 `message_key != "rules.import_tsv_quoted_field"` 条件保留。
3. 3 列判定（`:213-229`）：
   - 删除 `keep_legacy_blank_direction`；
   - 把 `elif len(row) >= 3 and not has_direction and direction and not keep_legacy_blank_direction:` 改为 `elif len(row) >= 3 and first and not has_direction and direction:`；
   - 后面的 `elif len(row) >= 3:` 分支已经处理“第一栏为空”，写法是 `first or (direction or "")`，不用改。
4. 文档：在三种语言的 `resources/rule-guide.md` 和 `docs/rule-format.md` 的 TSV 一节，补充文件导入支持的三种写法：
   - `源<Tab>目标`；
   - `源<Tab>目标<Tab>备注`；
   - `方向<Tab>源<Tab>目标<Tab>备注`。

   两列、三列时方向取导入对话框里选的方向。表头行必须同时含“源”和“目标”两类词。

**测试**（`tests/unit/test_rule_import_export_roundtrip.py`）
- `test_first_data_row_starting_with_header_word_is_not_dropped`：对四组文本参数化：`"备注\t備註\n软件\t軟體\n"`、`"目标\t目標\n软件\t軟體\n"`、`"原文\t原文本\n软件\t軟體\n"`、`"source\tsauce\ncolor\tcolour\n"`。每组都断言得到 2 条规则。
- `test_header_row_skip_is_reported_as_info`：`"源\t目标\n软件\t軟體\n"` 得到 1 条规则，并有 1 条 severity 为 `info` 的诊断。
- `test_three_column_row_with_blank_direction_uses_selected_direction`：`"\t软件\t軟體\n"`，`direction="s2t"`，结果为 `[("s2t","软件","軟體")]`。
- 现有的 `test_chinese_tsv_header_is_skipped`、`test_three_columns_without_direction_are_source_target_comment`、`test_two_column_tsv_uses_selected_direction` 继续通过。

**验收标准**
- [ ] 重跑 `fix07_fix08_import_edges.py`：RULE-06 段前 4 行各得到 2 条规则；第 6 行得到 `[('s2t', '软件', '軟體', '')]`。
- [ ] 重跑 `fix07_bulk_add_header.py`：additions 为 `[('备注', '備註'), ('软件', '軟體')]`。
- [ ] `probe_edge_cases.py`（2026-09-28）仍然输出 `TSV roundtrip identity: True`。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_rules_window.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix07_fix08_import_edges.py \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix07_bulk_add_header.py \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/rules/probe_edge_cases.py
```

**不要做**
- 不猜测方向。
- 不新增 CSV schema。
- 批量添加不能绕过去重和冲突检查。

---

## FIX-08（P2，RULE-07 回归）TSV 和 OpenCC TXT 导入在 U+2028/U+2029/NEL/`\x0c` 处断行

**位置**
- `rules/importers.py:180-185` `_delimited_rows()`：TSV 分支用 `text.lstrip("﻿").splitlines()`。
- `rules/importers.py:285`：OpenCC TXT 用 `text.splitlines()`，这是既有问题，一并修。
- `rules/exporters.py:139-173`：导出端只跳过含 `\t`、`\r`、`\n` 的字段，含 U+2028 的规则会原样写出。

**现状**（`evidence/rules/fix07_fix08_import_edges.out` 的 RULE-07 段）
- target 为 `軟 體`，往返后 `reimported=[('软件', '軟')]`，另外多出一条诊断 `rule 3: direction: …`。`\x85` 和 ` ` 的结果相同。
- 含 `\x0c` 的备注行被拆成两行。

**期望**：只在 `\r\n`、`\r`、`\n` 处断行，与导出端的检查一致。

**修改方法**
1. `rules/importers.py` 顶部新增 `_LINE_BREAK = re.compile(r"\r\n|\r|\n")`（文件如果还没有 `import re`，一并加上），以及：
   ```python
   def _physical_lines(text: str) -> list[str]:
       lines = _LINE_BREAK.split(text)
       if lines and lines[-1] == "":
           lines.pop()
       return lines
   ```
2. `_delimited_rows()` 的 TSV 分支改为 `enumerate(_physical_lines(text.lstrip("﻿")), 1)`。
3. `:285` 的 `enumerate(text.splitlines(), 1)` 改为 `enumerate(_physical_lines(text), 1)`。
4. 顺带修 RULE-08 留下的文案：`:231` 的 `RuleValidationError("expected direction, source, target, comment", index=line)` 会显示成 “rule 2: …”，容易被误读成规则序号。改为不传 `index`，行号已经由诊断的 `line` 字段携带。

**测试**（`tests/unit/test_rule_import_export_roundtrip.py`）
- `test_tsv_roundtrip_keeps_unicode_line_separators`：对 `" "`、`" "`、`"\x85"`、`"\x0c"` 参数化，规则 `Rule(id="r", direction="s2t", source="软件", target=f"軟{ch}體")`。经 TSV 导出再导入后，断言 `back.rules[0].target == rule.target` 且 `back.diagnostics == ()`（按实际返回类型写，可能是 `[]`）。
- `test_opencc_txt_import_keeps_unicode_line_separators`：`"软件\t軟 體\n"` 按 `format="txt", direction="s2t"` 导入，得到 1 条规则，target 为 `軟 體`。
- `test_one_column_row_error_has_no_rule_prefix`：`"direction\tsource\ttarget\nonlyone\n"`，断言诊断的 `line == 2`，且消息不以 `"rule "` 开头。

**验收标准**
- [ ] 重跑 `fix07_fix08_import_edges.py`：RULE-07 段三行的 reimported 都是完整的 `軟?體`，diags 为空；“TSV form-feed inside comment”一行得到 1 条规则和 1 条第 2 行的错误。
- [ ] CSV 的行为不变。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_rules_m3.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix07_fix08_import_edges.py
```

**不要做**
- 不改 CSV 解析。
- 不改 JSON。
- 不在导出端新增跳过规则。

---

## FIX-09（P2，RULE-15 未达标）零宽跳过的诊断按片段发出，且没有本地化

**位置**
- `core/converter.py:285-296`：每个文本片段都追加一条 `REGEX_ZERO_WIDTH_SKIPPED` 诊断。
- `core/models.py:141`：`ConvertResult.zero_width_skips` 字段已经存在。
- `core/planner.py:143`：`diagnostics.extend(result.diagnostics)`。
- `core/planner.py:214`：`diagnostics=tuple(diagnostics)`。
- `ui/preview_window.py:836-838`：诊断名称按 `diagnostic.name.{code}` 查找，找不到就用 `diagnostic.name.unknown`。
- `ui/preview_window.py:853`：描述文字用 `diagnostic_summary(translator, code, 1)`。
- `ui/i18n.py:141-153` `diagnostic_summary()`：没有这个 code 的映射。

**现状**（`evidence/rules/fix09_zero_width_diagnostics.out`）
- 6 个文件、每个 10 段，共产生 60 条诊断。
- 预览中是 6 条记录，名称为“其他诊断：REGEX_ZERO_WIDTH_SKIPPED”，描述为“其他诊断 REGEX_ZERO_WIDTH_SKIPPED：1 处”，看不到规则 ID，也看不到实际次数 10。

**期望**：每个文件、每条规则一条诊断，写明规则 ID 和该文件内的总次数；名称和描述三种语言都本地化；不含正文。

**修改方法**
1. `core/converter.py:290-296`：删除 `diagnostics.extend(Diagnostic("REGEX_ZERO_WIDTH_SKIPPED", ...) ...)` 这一段，保留 `zero_width_skips` 的计算和返回，规则测试（`ui/rules_window.py:177`）仍然要用。
2. `core/planner.py`：
   - 在逐 target 循环之前建 `zero_width: dict[str, int] = {}`；
   - 在 `:143` 之后累加：`for rule_id, count in getattr(result, "zero_width_skips", ()): zero_width[rule_id] = zero_width.get(rule_id, 0) + count`；
   - 在构造 plan 之前（`:214` 之前），按 rule_id 排序追加：
     ```python
     diagnostics.extend(
         Diagnostic("REGEX_ZERO_WIDTH_SKIPPED", f"rule {rule_id}: skipped {count} zero-width match(es)")
         for rule_id, count in sorted(zero_width.items()))
     ```
   - 如果 planner 里调用 converter 的地方不止一处（例如数字字符引用的分支），每一处都要累加。
3. i18n 三份新增：
   - `diagnostic.name.REGEX_ZERO_WIDTH_SKIPPED`：
     - zh-Hans：“正则零宽度命中已跳过”
     - zh-Hant：“正規表示式零寬度命中已略過”
     - en：“Zero-width regex matches skipped”
   - `diagnostic.regex_zero_width_skipped`：
     - zh-Hans：“零宽度命中已跳过：{count} 处”
     - zh-Hant：“零寬度命中已略過：{count} 處”
     - en：“Zero-width matches skipped: {count}”
4. `ui/i18n.py` `diagnostic_summary()` 的映射表加 `"REGEX_ZERO_WIDTH_SKIPPED": "diagnostic.regex_zero_width_skipped"`。
5. `ui/preview_window.py` `_diagnostic_records()`：
   - code 为 `REGEX_ZERO_WIDTH_SKIPPED` 时，用 `re.match(r"rule (\S+): skipped (\d+) ", message)` 取出规则 ID 和次数；
   - 描述改用现有键 `rules.zero_width_skipped`（“规则 {id}：跳过了 {count} 次零宽度命中。”），即 `translator.text("rules.zero_width_skipped", id=rule_id, count=int(count))`；
   - 匹配失败时回落到 `diagnostic_summary(...)`。

**测试**
- `tests/unit/test_regex_rules.py::test_zero_width_skips_aggregate_to_one_diagnostic_per_rule_per_file`
  - 照抄 `fix09_zero_width_diagnostics.py` 的书。
  - 断言：每个文件恰好 1 条 `REGEX_ZERO_WIDTH_SKIPPED`，消息为 `rule z: skipped 10 zero-width match(es)`；6 个文件共 6 条。
- `tests/unit/test_preview_diagnostics.py::test_zero_width_diagnostic_record_is_localized`
  - 对三种语言断言：记录的 `name` 不含 `REGEX_ZERO_WIDTH_SKIPPED`；`description == Translator(lang).text("rules.zero_width_skipped", id="z", count=10)`。
- 现有的 `test_zero_width_runtime_match_is_skipped_not_fatal`：如果它断言的是 converter 层的诊断，改为断言 `ConvertResult.zero_width_skips == (("z", 1),)`。**断言的强度不能降低**。

**验收标准**
- [ ] 重跑 `fix09_zero_width_diagnostics.py`：`diagnostics total: 6`；样例消息为 `skipped 10`；预览记录的名称和描述都是本地化文字。
- [ ] 诊断和日志中不含原文。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_regex_rules.py tests/unit/test_preview_diagnostics.py tests/unit/test_i18n.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix09_zero_width_diagnostics.py
```

**不要做**
- 不放宽保存时的正则校验。
- 不把零宽匹配当作插入点。
- 不在诊断里写入正文。

---

## FIX-10（P2，PERF-05 未达标）状态筛选下，有分组的项每次单击都重建 O(N) 行映射

**位置**（`ui/preview_window.py`）
- `:2513-2522` `_visible_row_map()`：以“可见 tuple 的身份”为缓存键。
- `:2609` `_refresh_after_decision()`：`:2626` 只有“单项且带 `preferred_row`”时才不建映射。
- `:2677-2678`：删行后把缓存置空，所以下一次单击又要重建。

**现状**
- `evidence/perf/fix10_row_map_rebuilds.out`：2 万项、两两成组，在“待决定”筛选下连续接受 5 次，结果 `row-map rebuilds = 5 entries iterated = 99980`。
- 真实 Qt、39.6 万行时，分组接受每次 54–61 ms，目标 ≤ 25 ms。

**期望**：每次决定只做与受影响行数相关的工作，映射在筛选变化时建一次。

**修改方法**
1. `__init__`：在 `self._entries` 定好之后，一次性建立
   ```python
   self._entry_position = {
       (change.file_id, change.change_id): index
       for index, (_preview, change) in enumerate(self._entries)}
   ```
2. `_refresh()`：每次赋值 `self._visible_entries_cache = visible` 时，同步维护
   ```python
   self._visible_positions = [
       self._entry_position[(c.file_id, c.change_id)] for _p, c in visible]
   ```
   可见行一定是 `_entries` 按原顺序的子序列，所以这个列表单调递增。
3. `_refresh_after_decision()`：
   - 删掉 `row_map` 和 `preferred_row` 特例；
   - 每个受影响项用 `pos = self._entry_position[identity]; row = bisect_left(self._visible_positions, pos)` 定位；
   - 只有 `row < len(self._visible_positions) and self._visible_positions[row] == pos` 时才视为可见，否则 `row = None`；
   - 删区间时同步执行 `del self._visible_positions[first:last + 1]`，与 `next_entries` 的切片一一对应。
4. 删除 `_visible_row_map`、`_visible_identity_to_row`、`_visible_identity_to_row_entries`，以及调用方传入的 `preferred_row` 参数。先 grep，确认所有调用方都改掉了。
5. `model.remove_rows(((first, last),))` 如果遇到越界区间（`:1629-1630` 会静默跳过），改为回退到 `self._refresh(refresh_statuses=True)` 并 `return`，避免对话框缓存与模型不同步。

**测试**
- `tests/unit/test_preview_filters.py::test_undecided_filter_group_accept_does_not_rescan_visible_rows`
  - 照抄 `fix10_row_map_rebuilds.py` 的夹具。
  - 用 `tests/unit/test_preview_group_scaling.py` 的 `VisitCountingEntries` 包住 `dialog._visible_entries_cache` 后赋回。
  - 对第 100 行连续 5 次 `_accept_this()`。
  - 断言：总访问次数 ≤ 1,000；每次单击 decision() 调用 ≤ 1,000；每次可见数减 2；焦点落在下一条待决定项。
- `docs/reviews/2026-09-28/scripts/perf/benchmark_preview_ui.py`：新增一行 `accept_group_status_undecided`，在“待决定”筛选下对一个有分组的项接受一次，目标 ≤ 25 ms。这是新增测量，不改原有断言。
- `scripts/perf/fuzz_incremental_counts.py` 仍然输出 `failures=0`。

**验收标准**
- [ ] 新测试通过；`fix10_row_map_rebuilds.py` 在删掉 `_visible_row_map` 后会报 AttributeError。这是预期的，把脚本改为统计 `_refresh` 的调用次数，结果应为 0。
- [ ] 真实 Qt 下 `accept_group_status_undecided` ≤ 25 ms，原有三项不退化。
- [ ] `tests/unit/test_preview_decision_history.py` 全部通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_preview_filters.py tests/unit/test_preview_group_scaling.py tests/unit/test_preview_decision_history.py tests/unit/test_preview_window.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/perf/fuzz_incremental_counts.py \
  && QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-28/scripts/perf/benchmark_preview_ui.py
```

**不要做**
- 不拆开原子组。
- 不引入 QSortFilterProxyModel。
- 不改 Apply 的可用条件和撤销格式。
- “本文件”的批量路径不在本条范围内：SIMP-02 会删掉隐藏的“接受本文件”按钮，批量对话框是一次性操作，允许 O(N)。

---

## FIX-11（P3，UXS-03 和 UXS-08 未达标）批量提示和结果框里仍有 0 数量片段

**位置**
- `ui/preview_window.py:2401-2403`：`preview.batch_applied` 总是带 `{groups}`。
- `ui/preview_window.py:2365-2371`：没有可处理项时，禁用的确认按钮显示“处理 0 项修改”。
- `ui/preview_window.py:2364`：`summary.setText(" ".join(summary_parts))`，中文句子之间多出一个空格。
- `ui/preview_window.py:1141-1152` `show_result()`：`result.row.written` 总是加入，且总带“已跳过 {skipped} 项”；`result.row.unwritten` 总带“其中没有建议变更：{unchanged} 个”。
- `tools/validate_artifact.py:219-221`：必需键列表。

**现状**（`evidence/ux/fix11_zero_count_fragments.out`）
- 三种语言的批量提示都是“…涉及 0 个组。”。
- 结果框在 3 个场景 × 3 种语言下都有 0 数量行或片段，例如 `已写回：0 个文件（已接受 0 项变更，已跳过 0 项）`。

**期望**：UXS-03 和 UXS-08 的原验收：不出现任何 0 数量行或片段。

**修改方法**
1. 批量提示：三份 i18n 新增两个键，然后删除 `preview.batch_applied`（先用 grep 确认没有其他引用）。
   - `preview.batch_applied_main`：“已批量处理 {changes} 项修改。”/“已批次處理 {changes} 項修改。”/“Batch decision applied to {changes} changes.”
   - `preview.batch_applied_groups`：“涉及 {groups} 个组。”/“涉及 {groups} 個組。”/“Linked groups: {groups}.”

   `:2401` 处先取 main；`batch.group_count > 0` 时再拼接 groups 部分。中文直接拼接，en 用一个空格。
2. 确认按钮：`batch.change_count == 0` 时改用新键 `preview.batch_confirm_none`（“处理”/“處理”/“Apply”），按钮仍然禁用。
3. 摘要拼接（`:2364`）：`sep = "" if self._translator.language.startswith("zh") else " "`，然后 `summary.setText(sep.join(summary_parts))`。先确认 `Translator` 上语言属性的名字。
4. 结果框（`:1141-1152`）：
   - `files_changed > 0` 时才加入写回行。`skipped_changes > 0` 时用 `result.row.written`，否则用新键 `result.row.written_accepted`：
     - zh-Hans：“已写回：{files} 个文件（已接受 {accepted} 项变更）”
     - zh-Hant：“已寫回：{files} 個檔案（已接受 {accepted} 項變更）”
     - en：“Written files: {files} (applied changes: {accepted})”
   - 未写回行：`files_without_changes > 0` 时用 `result.row.unwritten`，否则用新键 `result.row.unwritten_plain`：
     - zh-Hans：“未写回：{files} 个文件”
     - zh-Hant：“未寫回：{files} 個檔案”
     - en：“Files not written: {files}”
5. `tools/validate_artifact.py:219-221` 把新键加入必需列表。

**测试**
- `tests/unit/test_preview_batch.py::test_batch_feedback_omits_zero_groups`
  - 沿用 `test_resolve_remaining_preserves_manual_skips` 的夹具，确认后断言：
    - `dialog._last_group_feedback == Translator("en").text("preview.batch_applied_main", changes=5)`；
    - `re.search(r"(?<![\d.])0(?!\d)", dialog._last_group_feedback) is None`。
- `tests/unit/test_result_counts.py::test_non_cancel_results_have_no_zero_count_fragments`
  - 三种语言 × `evidence/ux/fix11_zero_count_fragments.out` 中的 3 个场景。
  - 断言每一行都不匹配 `(?<![\d.])0(?!\d)`。
- 更新 `test_result_done_states_unwritten_files_include_unchanged_subset` 和 `test_result_status_and_count_rows_are_localized_line_by_line`：改为按新键断言。`skipped_changes` 为 0 时，不再要求 `"0"` 出现在写回行中。

**验收标准**
- [ ] 重跑 `scripts/ux/fix11_zero_count_fragments.py`，每一行都是 `zero lines: none`。
- [ ] 取消结果仍然只有一行；部分失败的警告和 `result.save_reminder` 保留。
- [ ] `check_ui_acceptance.py --verify` 仍然全部 PASS。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_preview_batch.py tests/unit/test_result_counts.py tests/unit/test_i18n.py tests/unit/test_artifact_validator.py tests/integration/test_plugin_conversion.py -q \
  && QT_QPA_PLATFORM=offscreen mise exec -- uv run python docs/reviews/2026-09-29/scripts/ux/fix11_zero_count_fragments.py
```

**不要做**
- 不改日志和历史的 summary 字段。
- 不改变结果框的状态行。

---

## FIX-12（P2）修好坏掉的验证工具，更正执行记录

按 2026-09-28 全局约束 7，这一条**只改入口，不降低断言**。

**修改方法**
1. `docs/reviews/2026-09-28/scripts/ux/probe_ux_simplicity.py:236`：`report["help_text"] = rules.help_label.text()` 改为 `report["help_text"] = tr.text("rules.help")`。
2. `docs/reviews/2026-09-28/scripts/ux/probe_rules_viewport.py:28`：两处 `rules.import_button` 改为 `rules.ruleset_more_button`。键名 `import_button_height` 和 `import_button_width` 保留，避免与旧证据对不上。
3. `docs/reviews/2026-09-28/scripts/rules/rule05_cross_ruleset_conflict.py:28-32`：`RuleManagerDialog(...)` 加参数 `run_ruleset_ids=("taiwan-terms", "default")`。
4. `docs/reviews/2026-09-28/scripts/rules/rule11_ruleset_enabled_is_global.py` 的第二段：把直接返回 `RuleWindowResult("other", ..., run_ruleset_ids=())` 的桩，改为真实窗口：
   ```python
   def view_other(rules, **kwargs):
       manager = rules_window.RuleManagerDialog(make_with_table(), rules, **kwargs)
       manager.ruleset_combo.setCurrentIndex(manager.ruleset_combo.findData("other"))
       manager._apply()
       return manager.result
   rules_window.show_rules_window = view_other
   ```
5. 按 [01 的“对执行记录的更正”](01-acceptance-audit.md#对-2026-09-2804-implementation-resultsmd-的更正)，在 `docs/reviews/2026-09-28/04-implementation-results.md` 末尾追加一节“2026-09-29 更正”。
6. PERF-06：在负载低于 4 时（`sysctl -n vm.loadavg` 的第一个数）连续跑 3 次 `probe_default_diagnostics.py`，把中位数写进本目录的 `04-implementation-results.md`。不修改探针的计时方式。

**验收标准**
- [ ] `probe_ux_simplicity.py` 退出 0。`ux_probe.json` 中两种语言的 `merged_one_selected.enter_in_filter_closed_dialog` 和 `merged_two_selected.enter_in_filter_closed_dialog` 都为 `false`。
- [ ] `probe_rules_viewport.py` 退出 0，默认尺寸和 960×640 下 `table_rows_visible >= 5`，`add_button_in_viewport` 为 true。
- [ ] `rule05_cross_ruleset_conflict.py` 两个集都输出非空冲突，且 `save enabled …: False`。
- [ ] `rule11_ruleset_enabled_is_global.py` 输出 `run ruleset_ids after :` 与 before 相同。
- [ ] 2026-09-28 的 04 文件原有行没有改动（`git diff` 只有追加）。

**验证命令**
```sh
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-28/scripts/ux/probe_ux_simplicity.py --output /tmp/uxs02 \
  && python3 -c "import json;d=json.load(open('/tmp/uxs02/ux_probe.json'));print([d[l][k]['enter_in_filter_closed_dialog'] for l in ('zh-Hans','en') for k in ('merged_one_selected','merged_two_selected')])" \
  && QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-28/scripts/ux/probe_rules_viewport.py \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/rules/rule05_cross_ruleset_conflict.py \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/rules/rule11_ruleset_enabled_is_global.py
```
第二条命令应打印 `[False, False, False, False]`。如果 `ux_probe.json` 的顶层结构与这里不同，按实际结构取这 4 个值。

**不要做**
- 不改旧证据（`docs/reviews/2026-09-28/evidence/`）。
- 不删、不放宽任何断言。

---

## FIX-13（P3，UXS-04 遗留）术语尾巴

**修改方法**（只改值，不改键）
1. `rules.output`：“沙箱输出 / 沙箱輸出 / Sandbox output”改为“测试输出 / 測試輸出 / Test output”。
2. zh-Hant `result.row.written`：“已寫入”改为“已寫回”。FIX-11 新增的 `result.row.written_accepted` 也用“已寫回”。
3. `rules.version_v2`：**跳过**。决定 D9 已定为只保留 §11.2 的顺序，SIMP-24 会删掉 `rules.version_v1`、`rules.version_v2`、`rules.detail_version` 这组键。
4. en `scope.checkpoint_close`：“Close checkpoint reminder”改为“Close Checkpoint reminder”。

**测试**：在 `tests/unit/test_i18n.py::test_one_term_per_concept` 末尾追加：
```python
for language in ("en", "zh-Hans", "zh-Hant"):
    for key, value in catalogs[language].items():
        assert "沙箱" not in value and "sandbox" not in value.casefold(), key
for key, value in catalogs["zh-Hant"].items():
    if key.startswith("result."):
        assert "寫入" not in value, key
```
`catalogs` 用该文件中已有的加载方式获得。

**验收标准**
- [ ] `grep -n '沙箱\|[Ss]andbox' plugin/OpenCCForSigil/resources/i18n/*.json` 没有输出。
- [ ] `test_supported_catalogs_have_same_keys_and_render_placeholders` 通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_i18n.py -q
```

**不要做**：不改键名；不改 `profile.default_name` 的 en 值 “Conservative”，它是方案名。

---

## FIX-14（P3，RULE-12 尾巴）“默认规则集不能删除”的说明看不到；偏好中留下悬空引用

**位置**
- `ui/rules_window.py:542` 附近：创建 `self.ruleset_menu` 时没有开启 tooltip。
- `app/settings.py:415-428` `_remove_ruleset_references()`：只清理方案文件和 `self.active`，不清理偏好 `run_options.ruleset_ids`。未保存的默认方案在下次启动时，从这个偏好读回本次引用（`settings.py:99-109`）。

**现状**
- `evidence/rules/fix14_menu_tooltip_qt.out`：`menu.toolTipsVisible(): False`。
- `evidence/rules/fix14_deleted_ruleset_prefs.out`：`next launch: missing-ruleset notice = ('X',)`。

**修改方法**
1. 创建菜单之后：
   ```python
   set_tips = getattr(self.ruleset_menu, "setToolTipsVisible", None)
   if callable(set_tips):
       set_tips(True)
   ```
2. `_remove_ruleset_references()` 的末尾，`for identifier in identifiers: self.rules.delete(identifier)` 之前加：
   ```python
   load = getattr(self.storage, "load_preferences", None)
   update = getattr(self.storage, "update_preferences", None)
   if callable(load) and callable(update):
       options = load().get("run_options")
       saved_ids = options.get("ruleset_ids") if isinstance(options, dict) else None
       if isinstance(saved_ids, list) and any(item in removed for item in saved_ids):
           update({"run_options": {"ruleset_ids": [i for i in saved_ids if i not in removed]}})
   ```
   `update_preferences` 对 dict 做深合并，list 整体替换（`sigil/storage.py:140-148`）。

**测试**
- `tests/unit/test_rules_window.py::test_ruleset_menu_shows_tooltips`：fake Qt 下断言调用过 `setToolTipsVisible(True)`，写法参照 fake Qt 的调用记录方式。
- `tests/integration/test_ruleset_persistence.py::test_delete_ruleset_prunes_saved_run_options`
  - 照抄 `fix14_deleted_ruleset_prefs.py`，storage 用测试中已有的带偏好文件的实现。
  - 断言重新构造的 `RunSettings` 满足 `take_missing_rulesets_notice() == ()`。

**验收标准**
- [ ] `fix14_menu_tooltip_qt.py` 输出 `menu.toolTipsVisible(): True`。
- [ ] `fix14_deleted_ruleset_prefs.py` 输出 `missing-ruleset notice = ()`。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/integration/test_ruleset_persistence.py -q \
  && QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-29/scripts/rules/fix14_menu_tooltip_qt.py \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix14_deleted_ruleset_prefs.py
```

**不要做**：不改偏好 schema；不清理其他偏好键。

---

## FIX-15（P3，RULE-09、RULE-14 同类问题）分隔格式导入同时写入两个归属；窗口内改绑不清另一个归属

**位置**
- `rules/importers.py:237-238`（`_rows_to_rules`）、`:304-305`（`_opencc_rows`）：不管范围是什么，都写入 `profile_id` 和 `book_fingerprint`。
- `ui/rules_window.py:1503`、`:1507` `_rebind_owner()`：只改当前范围对应的字段。
- 对照：JSON 导入的改绑（`rules/importers.py:350-353`）会清掉另一个字段。

**现状**
- `evidence/rules/fix15_delimited_owner.out`：tsv/csv/txt 在 scope=global 和 scope=book 下，都是 `profile_id='CURRENT-PROFILE' book_fingerprint='CURRENT-BOOK'`。
- `evidence/rules/fix15_rebind_other_owner.out`：窗口改绑后 `book='CUR' profile='OLD-PROFILE'`，导入改绑后 `profile=''`。

**修改方法**
1. `importers.py` 两处都改为：
   ```python
   "profile_id": profile_id if scope == "profile" else "",
   "book_fingerprint": book_fingerprint if scope == "book" else "",
   ```
2. `_rebind_owner()`：
   - `:1503` 改为 `replace(rule, book_fingerprint=self._book_fingerprint, profile_id="")`；
   - `:1507` 改为 `replace(rule, profile_id=self._profile_id, book_fingerprint="")`。

**测试**
- `tests/unit/test_rule_import_export_roundtrip.py::test_delimited_import_fills_only_matching_owner`：对 tsv/csv/txt × global/profile/book 参数化，断言只有对应字段非空。
- `tests/unit/test_rules_window.py::test_window_rebind_clears_the_other_owner`：照抄 `fix15_rebind_other_owner.py`，断言 `profile_id == ""`。

**验收标准**
- [ ] 两个脚本的输出与上面“期望”一致。
- [ ] `rule_dedup_key` 不变，R-02 的回归测试通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_rules_window.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix15_delimited_owner.py \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix15_rebind_other_owner.py
```

**不要做**：不改 `rule_dedup_key`；不自动改绑；不迁移已保存的规则。

---

## FIX-16（P3，RULE-14 尾巴）点击“有 N 条规则属于其他书籍或方案”会带出无关规则

**决定：本条不做。** D11 批准了 SIMP-22，那一条会直接删掉这个提示，下面的步骤只作为备查保留。批次 5 跳过本条，在 `04-implementation-results.md` 中写“按 2026-09-29 决定不做，由 SIMP-22 取代”。

**位置**
- `ui/rules_window.py:1461-1468` `_filter_foreign_owner_rules()`：切到“本次不生效”筛选。
- `:628-631`：活动筛选的选项。
- `:1282-1288` `_refresh()`：筛选判定。

**现状**（`evidence/rules/fix16_foreign_owner_banner.out`）：本次没有引用该规则集时，提示写“有 1 条规则…”，点开后显示 10 条。

**修改方法**
1. 活动筛选增加第 4 项 `("filter_foreign", "foreign")`。新键 `rules.filter_foreign`：“其他书籍或方案”/“其他書籍或設定檔”/“Other book or profile”。
2. `_refresh()` 中的判定改为：
   ```python
   and (activity_filter == "all"
        or (activity_filter == "foreign" and self._foreign_owner_scope(rule) is not None)
        or (activity_filter in ("active", "inactive")
            and self._rule_is_active(rule) == (activity_filter == "active")))
   ```
3. `_filter_foreign_owner_rules()` 改为选中 `"foreign"`。

**测试**：`tests/unit/test_rules_window.py::test_foreign_owner_banner_shows_only_foreign_rules`：照抄脚本，两种 run_ids 下点击后都断言 `manager._visible_rule_ids == ["f"]`。

**验收标准**
- [ ] 脚本两行都输出 `visible after click: 1 rules`。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/unit/test_i18n.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix16_foreign_owner_banner.py
```

**不要做**：不自动改绑；不改 `book_fingerprint()`。

---

## FIX-17（P3）补齐偏弱或缺失的测试

只加测试，不改产品代码。每个测试都要在当前代码上**通过**；如果不通过，说明发现了新缺陷，停下来记录，不要改断言。

1. **UXS-07**：`tests/unit/test_scope_selection.py::test_single_initial_selection_accepts_as_selected_scope`
   ```python
   dialog = _ScopeDialog(make_with_table(), (TextFile("one", "Text/one.xhtml"), TextFile("two", "Text/two.xhtml")),
                         ("one",), "en", Translator("en"), initial_scope=Scope.SINGLE)
   dialog._accept(close=False)
   assert dialog.selection.scope is Scope.SELECTED and dialog.selection.file_ids == ("one",)
   ```
   构造参数照抄同文件中现有的 `_ScopeDialog` 测试。如果签名与这里不同，以现有测试为准。
2. **RULE-01**：`tests/unit/test_regex_rules.py::test_single_regex_search_timeout_still_stops`
   - 照抄 `scripts/rules/fix17_regex_timeout.py`：规则 `(a|aa)+$` 作用于 `"a" * 40 + "b"`；
   - 断言抛出 `RuleExecutionError`，消息匹配 `evil.*timed out`。
3. **PERF-01**：`tests/unit/test_rules_compiled.py`
   - `_random_rules` 生成的源串改为只用文本字母表里的字符，也就是从 `"词语深目汉字A012"` 中抽 1–3 个。这样随机规则才会真正命中。
   - 新增 `test_prefix_indexed_replace_stage_equals_full_scan_for_random_rules`：把 `scripts/perf/fuzz_prefix_index.py` 缩到 300 个种子，对 source/pre/post 三个阶段断言快路径与全量扫描的结果相同，包括 `RuleExecutionError` 的文案。
4. **PERF-03**：`tests/unit/test_models.py::test_change_models_use_slots` 末尾追加：
   ```python
   updated = replace(change, target="改")
   assert updated.target == "改" and updated.span is change.span and not hasattr(updated, "__dict__")
   ```

5. **spec §11.8.2 的三条必须回归用例**：仓库里只有第 1 条，在 `tests/unit/test_rules_m3.py:36`，而且走的是测试专用管线加一个假 OpenCC。新增 `tests/integration/test_rules_transform_workflow.py::test_spec_11_8_2_locked_span_regression_cases`：
   - 规则：`Rule(direction="s2twp", source="服务器", target="服務器")`、`Rule(direction="s2twp", type="protect", source="乾隆", target="乾隆")`、`Rule(direction="s2twp", type="protect", source="着", target="着")`；
   - 用 `RuleSnapshot.freeze` 冻结，构造 `ConvertRequest("s2twp", rules_snapshot=…, detailed_classification=False, diagnose_mixed=False)`，写法参照 `tests/unit/test_regex_rules.py:68` 的 `_request()`；
   - 后端用真实的 `OpenCCBackend("s2twp")`，可复用 `tests/integration/conftest.py` 的 `shared_opencc_backend_factory`，经 `OfficialBackendConverter(backend).convert(text, request).target` 取结果；
   - 断言：`这台服务器着火了 → 這臺服務器着火了`、`乾隆时期的服务器 → 乾隆時期的服務器`、`穿着睡衣去着手处理 → 穿着睡衣去着手處理`。
   - 本轮已在 HEAD 上用生产路径手工验证，三条都成立，这个测试应当直接通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_scope_selection.py tests/unit/test_regex_rules.py tests/unit/test_rules_compiled.py tests/unit/test_models.py tests/integration/test_rules_transform_workflow.py -q
```

---

## FIX-18（P3）“其他观察”三项，以及诊断标签页的数量

1. **实体说明**：在三种语言的 `resources/rule-guide.md` 规则写法一节，各加一句：
   - zh-Hans：“书中的 `&`、`<`、`>` 以实体形式保存（如 `&amp;`），含这些字符的规则在书中不会命中，规则测试里却会命中。”
   - zh-Hant、en 同步。
2. **TSV/CSV 导出按列表顺序**：`rules/exporters.py:147` 附近不再按 ID 排序，改为保持传入的顺序，也就是界面上的列表顺序。
   - 先确认 JSON 导出和哈希计算不依赖这个排序，它们必须保持不变。
   - 测试：`tests/unit/test_rule_import_export_roundtrip.py::test_tsv_export_preserves_list_order`：规则 ID 为 `b`、`a`，导出后第一条数据行是 `b` 的源文本。
3. **诊断标签页的数量**（PERF-02 的计划外改动）：`ui/preview_window.py:1769-1791`。构造时不建面板，但用已算好的诊断记录数，给标签页设文字 `preview.diagnostics_count`（先确认该键存在，参数名以 JSON 为准）。
   - 测试：`tests/unit/test_preview_diagnostics.py::test_diagnostics_tab_label_shows_count_before_opening`：3 条诊断中有 2 条是唯一的；不切换标签页，断言标签文字等于 `Translator("en").text("preview.diagnostics_count", count=2)`。
   - 验收：`benchmark_preview_ui.py` 的 `dialog_construct_seconds` 仍然 ≤ 0.75 s。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_preview_diagnostics.py tests/unit/test_i18n.py -q \
  && QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-28/scripts/perf/benchmark_preview_ui.py
```

**不要做**：不改 JSON 导出格式；不改规则集哈希。
