# 01 交互与易用性（UXS）

基线 `c14701f`。先读 [README](README.md) 中的全局约束、术语表和批次顺序。

## 0. 现状测量

所有数据来自真实 Qt（PySide6 6.11.2，offscreen，960×640，zh-Hans），由 `scripts/ux/probe_ux_simplicity.py` 测得。

**首次使用的最少操作**（Sigil 中已选 2 个文件）：
合并窗口 → 分析 → 预览 → “更多…” → “接受全部文件” → 应用 → Checkpoint 确认 → 结果框。

一共约 8 次点击，中间出现 4 个模态窗口，另有一个进度窗。

**首屏可点击控件数：**

| 窗口 | 可点击控件 |
| --- | --- |
| 文件页 | 7 |
| 设置页（高级选项折叠） | 12 |
| 设置页（高级选项展开） | 27 |
| 预览主界面 | 13 |
| 预览“更多…”菜单 | 9 项常显，另有 2 项语言组操作 |
| 规则窗口 | 18 |

**修复前截图：** `evidence/ux/merged-one-zh-Hans-tab0.png`、`merged-one-zh-Hans-tab1.png`、`preview-zh-Hans.png`、`rules-960.png`、`rules-0.png`。

**原始数据：** `evidence/ux/ux_probe.json`。

---

## UXS-01（P1）合并设置窗口：主按钮写“继续选择转换方向”，点击后直接开始分析；方向选择藏在第二个标签页

**位置**
- `plugin/OpenCCForSigil/ui/preview_window.py:511`：`choose_scope()` 创建 `analyze_button` 时使用 `scope.analyze`。
- `ui/preview_window.py:585`：`retranslate_combined_controls()` 同样使用 `scope.analyze`。
- `ui/preview_window.py:471`：窗口标题。
- `ui/preview_window.py:503-508`：组装两个标签页。
- `ui/preview_window.py:3619-3622`：`_ConversionConfigDialog._retranslate()` 把标题设为 `scope.title`。
- i18n：`scope.analyze` = “继续选择转换方向”，`config.continue` = “分析并预览”，`scope.title` = “选择要转换的文件”。

**现状**
- 真实 Qt 实测结果：
  - 默认显示标签页 0（文件范围）；
  - 窗口标题为 “OpenCCForSigil — 选择要转换的文件”；
  - 默认按钮文字为 “继续选择转换方向”（en：“Continue to direction”）。
- 点击这个按钮会执行 `accept_combined()`，直接开始分析，不会再出现选择方向的步骤。
- 方向下拉框只在“转换设置”页里。用户不打开这一页也能开始分析，这时会沿用 s2t 或上次用过的方向。
- 这个文案是旧的两步流程留下的：以前先弹独立的 `_ScopeDialog`，再弹 `_ConversionConfigDialog`。

**期望**
- 两个标签页上都能看到方向下拉框。
- 主按钮写的就是它实际做的事：“分析并预览”。

**修改方法**
1. 在 `choose_scope()` 的合并路径里，构造 `config_dialog` 之后，把 `config_dialog.direction_label` 和 `config_dialog.combo` 移到一个外层行，放在摘要和标签页之间：
   ```python
   direction_row = qt_widgets.QHBoxLayout()
   direction_row.addWidget(config_dialog.direction_label)
   direction_row.addWidget(config_dialog.combo, 1)
   outer_layout.addWidget(summary)
   outer_layout.addLayout(direction_row)   # 新增
   outer_layout.addWidget(tabs)
   ```
   `config_dialog.explanation_label` 留在设置页。控件对象不变，所以信号、`_get_config` 和 `_retranslate` 都不用改。
2. `:511` 和 `:585` 改用 `translator.text("config.continue")`。`scope.analyze` 保留，只给非嵌入的 `_ScopeDialog` 使用（`:3842`、`:3964`）。
3. 新增 i18n 键 `main.title`：
   - zh-Hans：“简繁转换”
   - zh-Hant：“簡繁轉換”
   - en：“Chinese conversion”

   以下三处在合并窗口中改用它作为标题：
   - `choose_scope()` 里的 `outer.setWindowTitle`；
   - `_ScopeDialog._language_changed()`，在 `self._embedded` 为真时；
   - `_ConversionConfigDialog._retranslate()`，在 `self._embedded` 为真时。

**测试**
- 更新 `tests/unit/test_dialog_construction.py::test_scope_and_conversion_configuration_share_one_dialog`：
  - 布局解包改为 `summary, direction_row, tabs, footer = dialog._layout.children`；
  - 断言 `footer.children[-1].text() == "Analyze and preview"`；
  - 断言 `direction_row.children` 中包含方向下拉框。
- 新增 `tests/unit/test_scope_selection.py::test_merged_dialog_language_change_keeps_analyze_label`：切换到 zh-Hans 后，断言按钮文字等于 `Translator("zh-Hans").text("config.continue")`。

**验收标准**
- [ ] 三种语言下，主按钮文字都等于 `config.continue`。
- [ ] 真实 Qt 下，在标签页 0 就能看到并修改方向；修改后，摘要第一行的方向同步变化。
- [ ] 合并窗口的标题不再是“选择要转换的文件”。
- [ ] `docs/reviews/2026-09-27/ui-workflow/scripts/check_run_summary.py --verify` 在三种语言下仍然通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_dialog_construction.py tests/unit/test_scope_selection.py -q
```

**不要做**
- 不自动推荐或切换方向。
- 不把两个标签页拆回两个窗口。
- 不删除 `scope.analyze`。
- 不改 Jieba 的 fail-closed 逻辑。

---

## UXS-02（P1）在“筛选文件”框按 Enter 会直接开始分析

**位置**
- `ui/preview_window.py:3810`：`_ScopeDialog.__init__` 中的 `self.filter_edit.returnPressed.connect(self._focus_first_visible_item)`。
- `ui/preview_window.py:512`：`analyze_button.setDefault(True)`。

**现状**
- 真实 Qt 实测：Sigil 中选了 1 个或 2 个文件时，在筛选框输入 “chapter” 后按 Return，结果如下：
  - `enter_in_filter_closed_dialog = true`
  - `dialog_result = 1`
  - `scope.accepted = true`，`config.accepted = true`

  也就是说，窗口关闭，分析开始。见 `evidence/ux/ux_probe.json` 的 `merged_one_selected` 和 `merged_two_selected`。
- 原因：`QLineEdit` 发出 `returnPressed` 后会 ignore 这个按键，按键于是传到 `QDialog`，触发了默认按钮。
- 现有测试 `test_scope_filter_enter_focuses_first_visible_row_without_accepting` 只在 fake Qt 中调用 `returnPressed.emit()`，覆盖不到这条按键传递路径。

**期望**
在筛选框按 Enter 只把焦点移到第一个可见文件，永远不启动分析。

**修改方法**
1. 仿照 `ProgressReporter._install_non_cancellable_event_filter()`（`ui/preview_window.py:273` 附近）的写法，在 `_ScopeDialog` 中新增：
   ```python
   def _filter_enter_pressed(self) -> bool:
       self._focus_first_visible_item()
       return True  # 吃掉按键，不让它传到 QDialog 的默认按钮

   def _install_filter_enter_guard(self, qt):
       core = getattr(qt, "QtCore", None)
       qobject, qevent = getattr(core, "QObject", None), getattr(core, "QEvent", None)
       if qobject is None or qevent is None:
           return
       key_press = getattr(qevent, "KeyPress",
                           getattr(getattr(qevent, "Type", qevent), "KeyPress", None))
       keys = {_enum_value(qt.Qt, "Key_Return"), _enum_value(qt.Qt, "Key_Enter")}
       owner = self

       class _Guard(qobject):
           def eventFilter(_self, _target, event):
               return (event.type() == key_press and event.key() in keys
                       and owner._filter_enter_pressed())

       self._filter_enter_guard = _Guard(self.filter_edit)
       self.filter_edit.installEventFilter(self._filter_enter_guard)
   ```
2. 在 `:3810` 之后调用 `self._install_filter_enter_guard(qt_widgets)`。原来的 `returnPressed` 连接保留，fake Qt 测试依赖它。
3. 如果 `_enum_value` 在这个文件里不存在，就用文件中已有的、读取 Qt 枚举的辅助函数，不要另写一套。

**测试**
- 新增 `tests/unit/test_scope_selection.py::test_filter_enter_guard_consumes_key_and_focuses_first_row`：直接调用 `dialog._filter_enter_pressed()`，断言：
  - 返回值为 `True`；
  - `list_widget.currentRow()` 是第一个可见行；
  - `dialog.accepted is False`。
- 真实 Qt：在 `docs/reviews/2026-09-27/ui-workflow/scripts/check_run_summary.py --verify` 中新增一个场景：输入文字后执行 `QTest.keyClick(filter_edit, Qt.Key_Return)`，断言对话框仍然可见。

**验收标准**
- [ ] 真实 Qt 下，Sigil 已选 0、1、2 个文件时，在筛选框按 Return 或 Enter 后，对话框都还在，`accepted` 为 False。
- [ ] 按 Enter 后焦点落在第一个可见文件行。
- [ ] 焦点在列表或按钮上时按 Enter，仍按默认按钮的行为开始分析。

**验证命令**
```sh
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-28/scripts/ux/probe_ux_simplicity.py --output /tmp/uxs02
```
然后检查 `/tmp/uxs02/ux_probe.json`：两种语言的 `merged_one_selected.enter_in_filter_closed_dialog` 和 `merged_two_selected.enter_in_filter_closed_dialog` 都应为 `false`。

**不要做**
- 不去掉 `analyze_button` 的 default 属性。
- 不全局禁用 Enter。
- 不改历史窗口“查看报告”的 default 设置：`test_history_report_self_test.py:352` 专门断言了它，而且报告是只读的。

---

## UXS-03（P1）应用前必须决定每一项，但批量入口藏在“更多…”里：7 个入口互相重叠，“接受全部文件”会覆盖用户手动跳过的项

**位置**
- `ui/preview_window.py:1963-1985`：`_PreviewDialog._build()` 构建“更多…”菜单。
- `ui/preview_window.py:3208-3221`：`_accept_all()` 调用 `preview.accept_all(overwrite=True)`；`_reject_all()` 同理。
- `ui/preview_window.py:3167-3206`：`_accept_file`、`_reject_file`。
- `ui/preview_window.py:3092`：`_decide_filtered()`。
- `ui/preview_window.py:2122-2247`：`_open_batch_decision()`，其中 `:2125` 把范围写死为 `"filtered"`。
- `ui/preview_window.py:2837-2860`：`_update_summary()`。

**现状**
- 真实 Qt 实测：还有 40 项待决定时，“应用”按钮不可用，状态栏显示“剩余 40 项待决定”。
- “更多…”菜单常显 9 项：接受本文件、跳过本文件、接受筛选项、跳过筛选项、接受全部文件、跳过全部文件、恢复此项、导出报告、批量处理待决定项…。另有 2 项语言组操作。
- 其中 6 个“本文件/筛选/全部”入口，和批量对话框里的三个范围完全重叠。UX-04 计划在 UX-05 统一入口，但 UX-05 只加了对话框，旧入口没有删。
- 语义不一致：“接受全部文件”是 `overwrite=True`，一次点击就把手动跳过的项改成接受，没有确认；而批量对话框默认只处理待决定项。
- 批量对话框的两个下拉框没有标签。摘要一句话里有 8 个数字，大部分通常是 0。

**期望**
- 主界面常显一个入口：“处理剩余 N 项…”。
- 批量操作只有一条路径，默认“全部文件 · 接受 · 仅处理待决定项”，确认一次即可。
- 没有任何一键入口会静默覆盖手动决定。

**修改方法**
1. 在 `_build()` 的 `actions` 行、`apply_status_label` 右侧，新增 `self.resolve_remaining_button`。文案用新键 `preview.resolve_remaining`：
   - zh-Hans：“处理剩余 {count} 项…”
   - zh-Hant：“處理剩餘 {count} 項…”
   - en：“Resolve remaining {count}…”

   点击时调用 `self._open_batch_decision(initial_scope="all")`。在 `_update_summary()` 中：`totals["undecided"] > 0` 时显示按钮并更新数字，否则隐藏。
2. `_open_batch_decision()` 增加参数 `initial_scope: str = "filtered"`，用它替换 `:2125` 写死的 `selected_scope = "filtered"`。菜单里的“批量处理…”仍然传 `"filtered"`。
3. 批量对话框改用 `QFormLayout`，给两个下拉框加标签：新键 `preview.batch_scope_label`（“范围”）和 `preview.batch_action_label`（“操作”）。
4. `refresh_batch_summary()` 只拼接非 0 的部分，例如“将接受 36 项（2 个文件）”，按需再加“，覆盖已有决定 3 项”或“，排除语言组 1 个”。做法：把 `preview.batch_summary` 拆成 `preview.batch_summary_main` 和若干 `preview.batch_summary_part_*`，旧键不再使用时删除。
5. 从 `self.more_menu` 移除以下 6 个按钮对应的 action：`accept_file_button`、`reject_file_button`、`accept_filter_button`、`reject_filter_button`、`accept_all_button`、`reject_all_button`。
   - 菜单只保留：批量处理…、恢复此项、导出报告，以及语言组两项。
   - 这 6 个按钮对象和方法先保留，现有单元测试和决定逻辑还会用到。
6. 批量对话框的“当前文件”范围本来就排除跨文件语言组并说明原因，这一点保持不变。

**测试**
- `tests/unit/test_preview_window.py::test_resolve_remaining_button_tracks_undecided_count`：40 项待决定时按钮可见、文案含 40；逐项 `_accept_this` 全部处理完后按钮隐藏。
- `tests/unit/test_preview_window.py::test_more_menu_has_single_batch_path`：`[a.text() for a in dialog._more_actions]` 中不含 `preview.accept_all`、`preview.accept_file`、`preview.accept_filter` 的译文，并且只有一个 `preview.batch_decide`。
- `tests/unit/test_preview_batch.py::test_resolve_remaining_preserves_manual_skips`：夹具为 2 接受、3 跳过、5 待定，按 `initial_scope="all"` 的默认值确认，断言结果为 7 接受、3 跳过，且只产生 1 条撤销记录。
- 同步修改 `docs/reviews/2026-09-27/scripts/check_preview_layout.py` 第 241、265、423 行附近：这几处通过 `_more_action_by_button[accept_file_button]` 触发，改为直接调用 `accept_file_button.click()`。断言本身不能降低。

**验收标准**
- [ ] 真实 Qt 960×640 下，预览主界面能看到“处理剩余 N 项…”；点一次、确认一次之后，“应用”变为可用。
- [ ] “更多…”菜单常显项不超过 4 个（语言组两项按上下文显示）。
- [ ] 菜单和按钮中都没有任何一键路径会把“已跳过”改成“接受”。关闭“仅处理待决定项”时，仍然显示覆盖数量，并使用明确的确认文案。
- [ ] 批量摘要里不出现“0 个”这样的片段；两个下拉框都有可见标签。
- [ ] 2026-09-27 的 30 万条性能回归不退化，也不额外调用 OpenCC。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_preview_window.py tests/unit/test_preview_batch.py tests/unit/test_preview_decision_history.py -q
```

**不要做**
- 不默认、自动或按风险接受任何项。
- 不取消“应用前必须全部决定”。
- 不把批量接受和应用合并成一步。
- 不拆开规则组或语言组。
- 不删除 `PreviewSession.accept_all(overwrite=...)`。

---

## UXS-04（P2）同一概念多种叫法（放在最后一批做）

**位置**：`resources/i18n/{zh-Hans,zh-Hant,en}.json`，只改值，不改键。

**现状**（逐键核实）

| 概念 | 现有叫法 | 键 |
| --- | --- | --- |
| 未决定 | 待决定 | `preview.summary`、`preview.apply_status_pending`、`preview.batch_*` |
| | 待定 | `preview.status.pending`、`preview.filter_file_option` |
| | 未决 | `preview.next_undecided`、`preview.shortcut.next_undecided` |
| | 未处理 | `preview.filter_status.undecided`、`preview.reset_current_tooltip`、`a11y.preview.reset_current` |
| 内置署名规则 | 内置规则包 / 内置署名保护 / 内置署名规则包 | `options.active_rulesets` / `options.builtin_rules_enabled` / `rules.builtin_info` |
| 规则测试 | 规则 / 沙箱 · 测试 · 沙箱测试 | `settings.rules` · `rules.tab_test` · `rules.test_group` |
| Checkpoint | Checkpoint / 检查点 | `scope.checkpoint_notice`、`preview.checkpoint_title` / `profile.checkpoint_notice`、`a11y.banner.dismiss_checkpoint` |

其他问题：
- en 混用了 Pending 和 Undecided。
- zh-Hant 中 Profile 大多写作“設定檔”（25 处），但以下 8 个键写成了“方案”：`profile.search_placeholder`、`profile.count`、`profile.no_matches`、`profile.no_profiles`、`profile.scope_boundary`、`options.saved_profile`、`history.search_placeholder`、`history.profile_name_note`。
- `recovery.profile_recovered` 在三种语言里都硬编码了 “Conservative”，而界面显示的方案名是 `profile.default_name`（“保守转换”）。
- zh-Hans 的“配置”一词，在 `config.jieba_unavailable` 中指 OpenCC 方向，在 `profile.same_config` 中指整套设置。

**修改方法**：按 README 的术语表逐项修改。
1. zh-Hans：
   - `preview.status.pending`、`preview.filter_status.undecided` → “待决定”；
   - `preview.filter_file_option` 中的“处待定” → “处待决定”；
   - `preview.next_undecided` → “下一项待决定”；
   - `preview.shortcut.next_undecided` → “下一项待决定 (N)”；
   - `preview.reset_current_tooltip`、`a11y.preview.reset_current` 中的“恢复为未处理” → “恢复为待决定”。

   zh-Hant 对应改为“待決定”“下一項待決定”。en 统一为 “Undecided” / “to undecided”。
2. zh-Hant：上面列出的 8 个键，把“方案”改为“設定檔”。
3. `recovery.profile_recovered`：把 “Conservative” 换成 `{name}` 占位符。`ui/preview_window.py:_recovery_notice_text()` 对这个键额外传入 `name=translator.text("profile.default_name")`。其他 `recovery.*` 键不动。
4. 统一叫“内置署名保护”：
   - `options.active_rulesets` → “规则集：{ids} · 内置署名保护{builtin}”；
   - `rules.builtin_info` → “内置署名保护{status}：{rules}”；
   - zh-Hant、en 同步修改。
5. `settings.rules` → “规则与测试”（zh-Hant “規則與測試”，en “Rules & test”）；`rules.test_group` → “规则测试”。
6. `profile.checkpoint_notice` → “显示 Checkpoint（检查点）提醒”；`scope.checkpoint_notice` 中的 Checkpoint → “Checkpoint（检查点）”。
7. `profile.same_config` → “与本次设置一致。”；`config.jieba_unavailable` 中的“标准 OpenCC 配置” → “标准转换方向”。
8. 检查 UXS-01、UXS-03、RULE-* 各批新增的键，确认都符合术语表。

**测试**
在 `tests/unit/test_i18n.py` 新增 `test_one_term_per_concept`，断言：
- zh-Hans 的 `preview.*` 和 `a11y.preview.*` 值中，去掉“待决定”后不再含“待定”；也不含“未决”“未处理”。
- zh-Hant 的 `profile.*`、`history.*`、`options.*` 值中不含“方案”。
- 所有 `recovery.*` 值中不含 “Conservative”。

**验收标准**
- [ ] 新测试在三种语言下都通过；`test_supported_catalogs_have_same_keys_and_render_placeholders` 仍然通过。
- [ ] 真实 Qt 截图中，状态列、状态筛选和“下一项”按钮使用同一个词。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_i18n.py -q
```

**不要做**
- 不改键名（第 3 步的占位符除外）。
- 不翻译用户自定义名称、规则集 ID 或 OpenCC 配置 ID。
- 不破坏 `test_traditional_chinese_separates_accepting_changes_from_applying_them` 所保证的“接受/应用”区分。

---

## UXS-05 → 已合并到 [03-rules.md 的 RULE-11](03-rules.md#rule-11)

问题：规则集的“本次启用此规则集”实际是持久且全局的开关；只是浏览另一个规则集，保存时它就会被加入本次转换；保存时最多弹 2 个模态框。修改方法和验收都在 RULE-11 中。

---

## UXS-06（P2）规则窗口首屏：列表只显示 2 行，“新增”按钮要在内部滚动后才能看到

**依赖**：RULE-11 先完成，因为第 1 步要放置 RULE-11 移出的全局开关。

**位置**
- `ui/rules_window.py:533-545`：`defaults_box`（可勾选的 QGroupBox）。
- `ui/rules_window.py:548-558`：`help_box`（可勾选的 QGroupBox）。
- `ui/rules_window.py:559`：`builtin_info_label`。
- `ui/rules_window.py:665-674`：`priority_box`（可勾选的 QGroupBox）。
- `ui/rules_window.py:690-698`：`transfer_box`。
- `ui/rules_window.py:716-727`：测试页布局。
- `ui/rules_window.py:411`：默认尺寸 `(840, 540)`。
- i18n：`rules.help`。

**现状**（真实 Qt，30 条规则，`scripts/ux/probe_rules_viewport.py`）

| 窗口尺寸 | 表格视口高度 | 可见行数 | “新增并应用到草稿”按钮 | 编辑区滚动最大值 |
| --- | --- | --- | --- | --- |
| 默认（实际 768×614） | 61 px | 2 | 不可见 | 180 |
| 960×640 | 79 px | 2 | 不可见 | 154 |
| 1280×800 | — | 9 | 可见 | — |

- 首屏空间被两个空的可勾选分组框、一行内置署名说明，以及导入/导出分组里的两个全宽按钮占用。UX-06 规格要求“不占用两块空白 GroupBox”，这一条没有做到。
- 用可勾选的 QGroupBox 当折叠器，看起来像“勾选就启用”，语义不对。
- `rules.help` 的 zh 文案写“先在下方沙箱测试”，但测试早已移到“测试”标签页；en 文案比中文多两句。
- 测试页的 Tab 顺序是：测试范围 → 测试按钮 → 词典检查 → 输入 → 输出，按钮排在了输入前面。

**期望**
- 默认尺寸下表格至少显示 5 行，新增/更新按钮在首屏可见。
- 不常用的设置收进菜单。
- 三种语言的说明内容一致。
- 测试页的 Tab 顺序为：输入 → 测试。

**修改方法**
1. 在 `ruleset_row` 末尾新增 `self.ruleset_more_button`（`QToolButton`，文案 `preview.more_actions`，弹出方式为 InstantPopup）。菜单项：
   - “规则集设置…”：打开一个小 QDialog，内容为 `default_direction_combo`、`default_scope_combo`，以及 RULE-11 移出来的全局启用开关；
   - “规则行为说明”：用 `QMessageBox.information` 显示 `rules.help`；
   - “导入…”：连接 `_import`；
   - “导出…”：连接 `_export`。

   然后删除 `defaults_box`、`help_box`、`transfer_box` 三个 GroupBox。里面的控件对象保留，改由小对话框持有，这样 `_stash_ruleset` 和 `_load_ruleset_metadata` 不用改。
2. `priority_box` 改成 `run_options.RunOptionsPanel.advanced_button` 那样的写法：一个可勾选、带箭头的 `QToolButton`，加一个内容 widget。
3. `builtin_info_label` 的内容并入 `selection_details` 的占位文字，不再单独占一行。
4. `rules.help`：三种语言都把“下方沙箱”改为“可在“测试”页验证规则”。en 多出的两句补进 zh-Hans 和 zh-Hant，让三份内容一致。
5. 测试页：把 `test_layout.addWidget(self.test_input)` 移到 `test_layout.addLayout(test_buttons)` 之前。
6. 默认尺寸由 `(840, 540)` 改为 `(960, 640)`。实际尺寸仍由 `restore_window_size` 按屏幕限制。

**测试**
- `tests/unit/test_rules_window.py::test_rules_page_has_no_checkable_disclosure_groupboxes`：fake Qt 中遍历 `rules_page` 的子控件，断言没有任何 QGroupBox 调用过 `setCheckable(True)`。
- `tests/unit/test_rules_window.py::test_more_menu_exposes_defaults_help_import_export`：菜单有 4 个 action；触发“导入”会调用 `_import`。
- `tests/unit/test_i18n.py::test_rules_help_does_not_reference_below_sandbox`：三种语言的 `rules.help` 中都不含“下方”和 “below”。
- 真实 Qt：更新 `docs/reviews/2026-09-26/scripts/check_rules_layout.py --verify`，在 768×614 和 960×640 下断言：
  - `table.viewport().height() >= 5 * rowHeight`；
  - `add_button` 位于 `editor_scroll.viewport()` 可视范围内（判断方法参考 `scripts/ux/probe_rules_viewport.py` 中的 `inside()`）。

**验收标准**
- [ ] 默认尺寸和 960×640 下，表格至少显示 5 行，新增按钮不用滚动就能看到。
- [ ] 首屏没有空的分组框。
- [ ] 导入、导出、规则集设置、说明都能从“更多…”一步打开，导入导出的现有回归全部通过。
- [ ] 测试页 Tab 顺序为：测试范围 → 输入 → 测试。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/unit/test_rules_m3.py tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_i18n.py -q
```

**不要做**
- 不合并“应用到草稿”和“保存规则集”这两级提交。
- 不改草稿保护的三选一。
- 不删冲突列表。
- 不改测试的计算逻辑。

---

## UXS-07（P3）范围有 4 个单选项，“单个文件”和“选择文件”重复；固定模式下复选框能点但会弹回

**位置**
- `ui/preview_window.py:3795-3806`：四个 `QRadioButton`。
- `ui/preview_window.py:3872-3886`：初始模式判断。
- `ui/preview_window.py:4031-4044`：`selected_ids()`。
- `ui/preview_window.py:4109-4148`：`_refresh_mode_items()`。
- `ui/preview_window.py:3898-3907`：`_item_changed()`。
- i18n：`scope.spine`。

**现状**
- Sigil 中只选了 1 个文件时，窗口默认进入“单个文件”模式：列表的复选框消失，当前高亮行就是目标。点一下别的行，目标就悄悄换了；想加第二个文件，得先切到“选择文件”。
- “Spine 正文”和“全部 XHTML”模式下，列表项仍然可以勾选，但点击后会被 `_refresh_mode_items()` 还原，看起来像点了没反应。
- 规格 §6.1 只要求三种范围；“Spine”是术语。

**期望**
- 只保留三个选项：选择文件 / 按阅读顺序（Spine）/ 全部 XHTML。
- 固定模式下列表只读。

**修改方法**
1. `_ScopeDialog.__init__`：
   - 不再把 `self.single_radio` 加入 `radio_row`；对象保留，并 `setVisible(False)`。
   - 当 `initial_scope is Scope.SINGLE` 或 `len(initial_ids) == 1` 时，选中 `self.selected_radio`，并勾选该文件。
2. `_accept()`：UI 不再产生 `Scope.SINGLE`。core 里的 `resolve_target_selection` 和 `Scope.SINGLE` 保留。
3. `_refresh_mode_items()`：
   - `mode in {"spine", "all"}` 时执行 `item.setFlags(item.flags() & ~checkable)`，同时保留勾选状态的显示；
   - `mode == "selected"` 时恢复可勾选。
4. `scope.spine` 改为：zh-Hans “按阅读顺序（Spine）”，zh-Hant “按閱讀順序（Spine）”，en “Reading order (spine)”。
5. `error.scope_exactly_one` 如果不再被引用，从三份 JSON 中删除（先用 grep 确认）。

**测试**
- 更新以下两个测试，改为断言：Sigil 选中 1 个文件时，`selected_radio` 被选中、该项已勾选，`_accept()` 得到 `Scope.SELECTED` 且 `file_ids == (id,)`。
  - `tests/unit/test_scope_selection.py::test_single_scope_uses_one_row_selection_and_manual_selection_is_independent`
  - `tests/unit/test_dialog_construction.py::test_scope_dialog_constructs_and_single_file_can_continue_after_row_change`
- 新增 `test_fixed_scope_modes_make_list_read_only`。
- core 用例 `test_single_scope_requires_exactly_one_known_file` 保持不变。

**验收标准**
- [ ] 可见单选项只有 3 个。
- [ ] Sigil 选中 1 个文件时，打开窗口后可以直接再勾第二个。
- [ ] Spine/全部模式下点击列表项，勾选状态不变化，也不闪烁。
- [ ] “返回设置”后，原来的单个文件选择显示为“选择文件”加 1 项。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_scope_selection.py tests/unit/test_dialog_construction.py tests/integration/test_plugin_conversion.py -q
```

**不要做**
- Sigil 没有选择时，不默认全书；空选择必须保持禁用。
- 不读取正文。
- 不改 `TargetSelection` 的结构。

---

## UXS-08（P3）取消后也弹出一个 4 行、大多是 0 的“结果”框

**位置**
- `ui/preview_window.py:1086-1115`：`show_result()` 的 `rows`。
- `app/controller.py:387-395`、`app/controller.py:488-498`：取消路径。

**现状**
- 预览里什么都没决定就点“取消”，会弹出：“转换已取消。已分析 N 个文件 / 已写回 0 个文件（已接受 0 项…）/ 未写回 N 个…/ 全部跳过 0 个文件”。
- 成功时，数量为 0 的行也总是显示。

**修改方法**
1. `show_result()` 中，`status == "cancelled"` 时，`message` 只用新键 `result.status.cancelled_unchanged`，不拼接 `rows`：
   - zh-Hans：“转换已取消，书籍未作修改。”
   - zh-Hant：“轉換已取消，書籍未作修改。”
   - en：“Conversion cancelled; the book was not changed.”
2. 其他状态：`result.row.unwritten` 只在 `not_written > 0` 时加入；`result.files_all_skipped` 只在数量 > 0 时加入。

**测试**
- 更新 `tests/unit/test_result_counts.py` 中的以下两个测试，改为按“非 0 才出现”断言：
  - `test_result_status_and_count_rows_are_localized_line_by_line`
  - `test_result_done_states_unwritten_files_include_unchanged_subset`
- 新增 `test_cancelled_result_is_single_line`。

**验收标准**
- [ ] 取消后的结果只有 1 行。
- [ ] 成功结果中没有数量为 0 的行。
- [ ] `tests/integration/test_plugin_conversion.py::test_cancelling_preview_shows_cancelled_result_without_writing` 仍然通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_result_counts.py tests/integration/test_plugin_conversion.py -q
```

**不要做**
- 不去掉部分失败时的警告。
- 不去掉 `result.save_reminder`。
- 不改日志和历史的 summary 字段。

---

## UXS-09（P3）NAV 有两个开关；NAV 不在选择中时，选项显示为“已勾选但灰色”

**位置**
- `ui/run_options.py:109-111`：`include_nav`。
- `ui/run_options.py:328-331`：`_update_enablement()`。

**现状**
- 列表里的 NAV 复选框和设置页的“包含所选 XHTML 中的 NAV 目录”，控制的是同一件事。
- NAV 不在选择中时，设置页的选项显示为勾选且灰色，原因只写在 tooltip 里。

**修改方法**
`_update_enablement()` 中，把 `self.checks["include_nav"].setEnabled(...)` 改为 `setVisible(self._enablement["include_nav"])`。`preference_values()` 记住的值保持不变。

**测试**
`tests/unit/test_run_options.py::test_include_nav_hidden_when_nav_not_selected_and_preference_kept`：
- `set_nav_available(False)` 后，`isVisible()` 为 False，且 `preference_values()["include_nav"]` 仍是原值；
- `set_nav_available(True)` 后重新可见。

**验收标准**
- [ ] NAV 不在选择中时，设置页不出现灰色的 NAV 选项。
- [ ] UX-03 的“查看修改”明细中，NAV 一行仍显示“本次不生效”及原因。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_run_options.py tests/unit/test_run_summary.py -q
```

**不要做**
- 不改 `convert_nav` 字段。
- 不改 NAV 的计数规则。

---

## UXS-10（P3）设置窗口首屏杂项：界面语言选择器放在最上面；“方案”按钮只有名词；没有 Jieba 时也常显一行术语

**位置**
- `ui/preview_window.py:3782-3793`：`language_row`。
- `ui/run_options.py:286-290`：按钮文案 `settings.profiles`。
- `ui/preview_window.py:3419-3427`、`ui/preview_window.py:3506-3546`：Jieba 相关控件。

**现状**
- 文件页第一行是“界面语言：简体中文”。在简繁转换工具里，这很容易被误解成“目标语言”。
- “方案”按钮上只有一个名词，看不出点了会做什么。
- 没有 Jieba 的设备上，设置页始终显示“未检测到原生 Jieba 载荷…”和一个灰色复选框。

**修改方法**
1. 合并路径中，把 `scope_dialog.language_label` 和 `language_combo` 放进一个 widget，调用 `tabs.setCornerWidget(widget, Qt.TopRightCorner)`。独立的 `_ScopeDialog` 不变。
2. 先用 grep 确认 `settings.profiles` 是否还用在别处（例如窗口标题）：
   - 用在别处：新建 `settings.profiles_button` 专给按钮用，文案为“选择方案…”/“選擇設定檔…”/“Choose profile…”；
   - 只用在按钮上：直接改这个键的值。
3. `_apply_jieba_state()`：当 `self._probe_state == "unavailable"` 且 `not self._preferred_jieba` 时，`jieba_checkbox`、`jieba_status`、`jieba_details_button` 都 `setVisible(False)`。pending 状态、以及保存了 Jieba 偏好的情况，保持现状。

**测试**
- `tests/unit/test_conversion_dialog_jieba.py::test_unavailable_jieba_without_preference_is_hidden`
- `tests/unit/test_conversion_dialog_jieba.py::test_unavailable_preferred_jieba_still_explains_block`
- `tests/unit/test_dialog_construction.py`：断言 `tabs.cornerWidget()` 中包含 `language_combo`。

**验收标准**
- [ ] 文件页第一行不再是界面语言。
- [ ] 没有 Jieba 的设备上，设置页看不到 Jieba 相关文字。
- [ ] 保存了 Jieba 偏好但不可用时，分析仍被阻断并说明原因（`check_run_summary.py` 的三个 Jieba 用例通过）。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_conversion_dialog_jieba.py tests/unit/test_optional_jieba.py tests/unit/test_dialog_construction.py -q
```

**不要做**
- payload 未验证时，不显示或启用 Jieba。
- 不改 `choose_language` 的优先级。
- 不把界面语言写进 Profile。

---

## UXS-11（P3）预览表格有冗余列且右侧留白；详情里显示原始规则 ID

**位置**
- `ui/preview_window.py:1365`：`_format_change_row()` 的第 2 列。
- `ui/preview_window.py:1845-1847`：列宽设置。
- `ui/preview_window.py:2939`：`_show_current()` 中的 `change.rule_source`。

**现状**
- “变更”列只有 64 px，内容被截成“软件 →”，而且与“原文/转换后”两列的内容重复。
- 7 列总宽 718 px，在 960 宽的窗口里，右侧留下约 200 px 空白。
- 详情里写“规则：OpenCC:STPhrases”，筛选器里写“OpenCC — STPhrases”，两处不一致。

**修改方法**
1. `_show_current()` 中的规则行改用 `self._source_filter_label(change.rule_source)`。
2. 调用 `horizontalHeader().setStretchLastSection(False)`，把第 3、4 列设为 Stretch，其余列保持 Interactive。
3. 调用 `setColumnHidden(2, True)` 隐藏第 2 列，但不删除 `format_change_row` 的返回值。

**测试**
- `tests/unit/test_preview_window.py::test_detail_rule_uses_localized_source_label`
- 更新 `test_preview_table_uses_interactive_columns_with_readable_initial_widths`：断言第 2 列隐藏，第 3、4 列为 Stretch。

**验收标准**
- [ ] 960×640 下表格右侧没有大块空白。
- [ ] 详情中的来源写法与筛选器一致。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_preview_window.py tests/unit/test_preview_model.py -q
```

**不要做**
- 不格式化整张表，保持懒格式化。
- 不改报告和导出格式。
