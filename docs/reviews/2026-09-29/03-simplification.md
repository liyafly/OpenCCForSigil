# 03 可删除的复杂边界：SIMP-01 至 SIMP-32

基线 `6d74b25`。先读 [README](README.md)。

**分组与决定**（2026-09-29 已全部按推荐拍板，见 README“已拍板的决定”）
- **A 组（SIMP-01 至 SIMP-10）：全部做。** 都是死代码、只有测试在用的代码，或修 bug，用户看到的行为不变。
- **B 组（SIMP-11 至 SIMP-22）：除 SIMP-17 外全部做。** 这些是用户能看到的功能或兼容行为，删掉后界面更简单。
- **C 组（SIMP-23 至 SIMP-32）：做 SIMP-23 至 SIMP-30；SIMP-31、SIMP-32 本轮不做。** 涉及规则语义、spec 条文或新依赖。

**保留，不要删**
- INVARIANTS.md 的任何条款。
- 规则的阶段、动作、匹配方式、`priority` 字段、global/profile/book 范围与归属、通配方向 `*`、16 个方向。
- NCX 和元数据开关，`language_preset` 的 legacy/bcp47（spec §15.1）。
- Jieba 探测与 fail-closed（INVARIANTS #15）。
- Apply 时的 Checkpoint 确认（§9.5）。
- 偏好和规则集的 schema 迁移与 `.v1.bak` 备份（§71/§72）、恢复提示。
- RULE-14 的“其他书/方案”标注与改绑按钮。

**执行规则**
- 每条单独提交。每条做完都运行 README 的“每批通用验证”。
- 删 i18n 键时三份 JSON 一起删，并同步 `tools/validate_artifact.py` 里的必需键列表。
- 删键前先核对下面“动态拼接的 i18n 键”一节，避免误删动态引用的键。
- 旧的验收探针和复现脚本如果引用了被删的对象，只改入口，不降低断言（2026-09-28 全局约束 7）。实在无法保留原断言时，停下来记录，不要删断言。

**关于数量**：“约 −N 行”是删除量的估计，只作参考，不是验收标准。

---

## 总表

| ID | 组 | 候选 | 约删行数 | 风险 | 决定依据 | 本轮 |
| --- | --- | --- | --- | --- | --- | --- |
| SIMP-01 | A | 已不可达的两步式设置流：独立的“选文件”窗口、“方向”窗口和“上一步” | 250 | 低 | — | 做 |
| SIMP-02 | A | 预览里 6 个隐藏的批量按钮及其整条调用链 | 255 | 低 | — | 做 |
| SIMP-03 | A | `rules/engine.py` 中只有测试在用的第二条规则管线 | 310 | 低–中 | — | 做 |
| SIMP-04 | A | 13 个从未被 import 的空壳模块、约 35 个零调用名字、14 个未用 i18n 键 | 450 | 低 | — | 做 |
| SIMP-05 | A | `RuleWindowResult` 的旧结果形状、`_managed` 和删空后自动重建 default 的分支 | 30 | 低 | — | 做 |
| SIMP-06 | A | `resources/defaults/conservative.json`：第二个、而且与第一个不一致的默认方案来源 | 50 | 低 | — | 做 |
| SIMP-07 | A | PERF-01 多出的 3 条快路径，以及 4 份重复的 skipped 收集代码 | 80 | 低 | — | 做 |
| SIMP-08 | A | “宿主没有文本 API 就空跑、返回成功”的 Phase-0 路径 | 30 | 低 | — | 做 |
| SIMP-09 | A | 真 Qt 和 fake Qt 下都从没走过的防御分支，以及抄错的 `UserRole` 兜底值 | 250 | 低 | — | 做 |
| SIMP-10 | A | **bug**：导出 OpenCC TXT 时丢掉所有 V2 规则，新规则集导出为空文件 | 1 | 低 | — | 做 |
| SIMP-11 | B | 4 个规则模板：全部生成正则，其中“整理空格”就是 RULE-01 事故的源头 | 155 | 低 | D11 | 做 |
| SIMP-12 | B | 文件页的 Checkpoint 横幅，与 Apply 时的确认重复 | 80 | 低 | D11 | 做 |
| SIMP-13 | B | 两个诊断开关：关掉会让 §10.4 要求的“地区词汇”筛选失效 | 40 | 低 | D11 | 做 |
| SIMP-14 | B | “接受/跳过语言标签组”两个按钮：逐项决定本来就会连带整组 | 65 | 低 | D11 | 做 |
| SIMP-15 | B | 导入的 strict 模式复选框 | 20 | 低 | D11 | 做 |
| SIMP-16 | B | 方案文件的兼容垫片，顺带修掉 `zhTW` 静默无效的 bug | 100 | 低 | D11 | 做 |
| SIMP-17 | B | 中转链下拉框：只有 t2s 有多条链，其中两条会把“軟體”改回“软体” | 50 | 低–中 | D11 | **不做** |
| SIMP-18 | B | 5 个重复的小入口 | 130 | 低 | D11、D15 | 做 |
| SIMP-19 | B | 方案摘要里 8 个不生效的字段，例如显示“正则规则：否”，正则却照常执行 | 30 | 低 | D11 | 做 |
| SIMP-20 | B | 历史窗口的“状态”筛选：生产数据只可能是“已完成” | 20 | 低 | D11、D15 | 做 |
| SIMP-21 | B | “词典检查”并入“规则测试”：两个按钮调用同一个函数 | 130 | 低 | D11 | 做 |
| SIMP-22 | B | 规则窗口顶部的“有 N 条规则属于其他书籍或方案”提示 | 30 | 低 | D11 | 做（FIX-16 不做） |
| SIMP-23 | C | 正则的 3 个整次分析限额 | 80 | 中 | D8 | 做 |
| SIMP-24 | C | V1/V2 两张范围表合并为 spec §11.2 的顺序 | 100 | 中 | D9 | 做 |
| SIMP-25 | C | `RuleSet.enabled` 的全局开关并入“用于本次转换”，并删掉“规则集设置”对话框 | 60 | 中 | D13 | 做 |
| SIMP-26 | C | `Scope.SINGLE` 与隐藏的 `single_radio` | 10 | 低 | D13（撤销旧 D4） | 做 |
| SIMP-27 | C | `TextTarget.context` / `context_radius`：值恒为空字符串 | 10 | 低 | D13 | 做 |
| SIMP-28 | C | `include_nav` 并入“文件列表里是否勾选 NAV” | 45 | 中 | D13、D15 | 做 |
| SIMP-29 | C | 语言标记的“建议”和“强制”合并 | 20 | 低 | D13 | 做 |
| SIMP-30 | C | 导入格式的小变体 | 30 | 低 | D13 | 做 |
| SIMP-31 | C | 用真 PySide6 offscreen 替换 fake_qt | 净删约 1,400 | 中–高 | D12 | **不做** |
| SIMP-32 | C | 拆分 `ui/preview_window.py`（4,533 行，约 45% 与预览无关） | 0（只搬移） | 中 | D14 | **不做** |

**B 组勾选（D11，2026-09-29 已定）**：执行模型只做打了 `x` 的项。

- [x] SIMP-11 规则模板
- [x] SIMP-12 文件页 Checkpoint 横幅
- [x] SIMP-13 诊断两个开关
- [x] SIMP-14 语言标签组两个按钮
- [x] SIMP-15 导入 strict 模式
- [x] SIMP-16 方案兼容垫片
- [ ] SIMP-17 中转链改为固定链（**不做**）
- [x] SIMP-18 重复的小入口（①②③④⑤ 全部）
- [x] SIMP-19 方案摘要里不生效的字段
- [x] SIMP-20 历史状态筛选
- [x] SIMP-21 词典检查并入规则测试
- [x] SIMP-22 其他书/方案的提示

---

## A 组：直接做

### SIMP-01 已不可达的两步式设置流

**证据**
- 控制器的两处 `choose_scope(...)` 调用（`app/controller.py:194-216`）都展开了 `merged_dialog_options()`（`:179-189`），而这个函数总是带着 `available_configs`。因此 `ui/preview_window.py:433-461` 的 `if available_configs is None:` 分支不可达。
- 合并窗口确认时总会返回 `configuration`（`preview_window.py:633-636`），`reselect_scope`（`controller.py:231-264`）也同样设置它。所以 `controller.py:272-285` 调用的 `choose_conversion_config(...)` 永远走不到。
- `"back_to_scope"` 只由非嵌入的 `_ConversionConfigDialog._back_to_scope`（`preview_window.py:3956-3959`）产生，所以 `controller.py:287-300` 也不可达。
- 有 17 个集成测试 monkeypatch 了 `choose_conversion_config`，**测的正是这条死路径**，而生产路径反而缺少集成覆盖。

**删除步骤**
1. `ui/preview_window.py`：
   - 删除 `ConfigOutcome`（`:121-125`）和 `choose_conversion_config`（`:345-394`）。
   - `choose_scope` 删掉 `:433-461`，`available_configs` 改为必填。
   - `_ConversionConfigDialog` 删掉非嵌入分支：`:3715-3720`、`:3732-3733`、`:3754-3755`、`:3777-3796`、`_back_to_scope`、`:3983-3986`。
   - `_ScopeDialog` 删掉 `:4096-4100`、`:4134-4136`、`:4183-4202`、`:4330-4332`。
2. `app/controller.py:269-311`：直接使用 `pending_config_choice`，删掉 back_to_scope、cancel、continue 三个分支，以及 `:113` 对 `choose_conversion_config` 的导入。
3. i18n 删 `scope.analyze`、`scope.back`（三种语言），同时删 `tools/validate_artifact.py:98-99`。

**受影响的测试**：把 fake 的 `choose_scope` 改成返回 `ScopeOutcome(..., configuration=ConfigurationChoice(...))`，涉及：
- `tests/integration/test_plugin_conversion.py` 中 11 个；
- `test_jieba_probe_flow.py` 中 3 个；
- `test_ruleset_persistence.py::test_deleted_ruleset_is_reported_once_by_controller_and_not_planned`；
- `test_settings_history.py::test_back_to_settings_discards_old_plan_and_rebuilds`；
- `test_error_reporting.py` 中的 monkeypatch。

另外：
- 删除 `test_plugin_conversion.py::test_settings_back_to_scope_preserves_selected_direction`。
- 以下测试改为 `embedded=True` 构造：`test_scope_selection.py` 中 9 个、`test_run_options.py` 中 3 个、`test_conversion_dialog_jieba.py` 中 4 个。原来断言 `continue_button` 的，改为断言 `_continue_is_allowed()`。
- 探针 `docs/reviews/2026-09-27/ui-workflow/scripts/probe_ui_workflow.py:59` 只改入口。

**验证**
```sh
mise exec -- uv run pytest tests/unit/test_scope_selection.py tests/unit/test_dialog_construction.py tests/unit/test_run_options.py tests/unit/test_conversion_dialog_jieba.py tests/integration -q
grep -rn 'choose_conversion_config\|_back_to_scope\|"scope.analyze"\|"scope.back"' plugin tests tools   # 应无输出
```

**不要做**：不把两个标签页拆回两个窗口；不改 Jieba 的 fail-closed 逻辑。

### SIMP-02 预览里 6 个隐藏的批量按钮

**证据**
- UXS-03 第 5 步当时写的是“这 6 个按钮对象和方法**先保留**”。现在它们 `setVisible(False)`（`preview_window.py:2091-2096`），不在菜单里，也没有快捷键。
- 批量对话框（`_open_batch_decision`，`:2258-2406`）已经覆盖“本文件 / 筛选结果 / 全部 × 接受/跳过 × 是否覆盖”。

**删除步骤**（`ui/preview_window.py`）
1. 按钮本身：`:2048-2053`、`:2091-2096`、`:2131-2136`、`:2166-2168`、`:3116-3119`，以及 `:3132` 元组中的对应项。
2. 只被这些按钮调用的方法：
   - `_decide_filtered`（`:3422-3446`）、`_confirm_filtered_group_expansion`（`:3448-3484`）；
   - `_accept_file`、`_reject_file`、`_decide_file`（`:3498-3542`）；
   - `_accept_all`、`_reject_all`、`_set_all_decision_counts`（`:3544-3595`）；
   - `_history_entries_for_grouped_action`（`:2837-2842`）、`_file_decision_entries`（`:2844-2859`）、`_record_bulk_decision_action`（`:2751-2757`）。
3. `_BulkDecisionHistoryOperation`（`:74-86`），以及 `_apply_history_side` 中的对应分支（`:2873-2887`）。
4. 顺带删掉两处同类死代码：`self.export_full_diff`（`:2069-2071`，从不显示，也从不读取）和 `_selected_change_id`（`:2937-2939`）。
5. i18n 删：
   - `preview.{accept,skip}_{file,filter,all}`；
   - `preview.group_expansion_{title,confirm,yes,cancel}`；
   - 同步删 `tools/validate_artifact.py:110-113`。
6. **保留** `PreviewSession.accept_all/reject_all(overwrite=)`，这是 UXS-03“不要做”里的要求。
7. `docs/architecture.md:37` 删掉 “Accept all / Skip all” 的说法。

**受影响的测试**：改为走批量对话框，或者直接用 `plan_batch_decision` 加 `restore_decision`。
- `test_preview_window.py` 中 9 个；
- `test_preview_decision_history.py` 中 5 个；
- `test_preview_group_scaling.py` 中 2 个；
- `test_preview_model.py::test_three_hundred_thousand_preview_build_filter_and_accept_all_stay_bounded`：改走新路径，时间上限不变。
- 探针只改入口：`docs/reviews/2026-09-27/scripts/check_preview_layout.py:312, 336, 376, 381, 494`，以及 `docs/reviews/2026-09-28/scripts/perf/benchmark_preview_ui.py:119-122`。benchmark 中的 `accept_file` 行改为通过批量对话框的“当前文件”范围测量。

**验证**
```sh
mise exec -- uv run pytest tests/unit/test_preview_window.py tests/unit/test_preview_decision_history.py tests/unit/test_preview_group_scaling.py tests/unit/test_preview_model.py tests/unit/test_preview_batch.py -q
grep -n "accept_file_button\|accept_all_button\|_decide_filtered\|_BulkDecisionHistoryOperation" plugin -r   # 应无输出
```

### SIMP-03 `rules/engine.py` 的第二条规则管线

**证据**
- 在 `plugin/` 下 grep `convert_with_overlay|lock_spans\b|RuleEngine`，只命中定义本身和 `rules/__init__.py:3,12-13` 的再导出。生产代码只用到 engine 里的 `LockedSpan`（`rules/compiled.py:182`）。
- 生产的规则转换走 `core/converter.py` 的 `_convert_rules`，沙箱也走 `OfficialBackendConverter`。
- `convert_with_overlay` 调用 `replace_stage` 时不传索引，也不产生零宽诊断，与生产路径**并不等价**。所以现在用它的测试，测的不是用户实际用的代码。

**删除步骤**
1. 把 `LockedSpan`（`rules/engine.py:18-29`）移进 `rules/compiled.py`，然后删除 `rules/engine.py`。
2. `rules/__init__.py` 去掉 `OverlayResult`、`convert_with_overlay`、`lock_spans` 的再导出。
3. 测试改用 `OfficialBackendConverter(backend).convert(text, ConvertRequest(...))`（可复用 `tests/unit/test_regex_rules.py:68` 的 `_request()`），或者 `lock_spans_compiled(text, CompiledOverlay.build(...))`。
4. FIX-17 第 5 项（spec §11.8.2 三条回归用例）必须先完成。

**受影响的测试**（13 个）
- `test_rules_m3.py` 中 9 个，例如 `test_locked_targets_are_never_reconverted_and_longest_match_wins`、`test_v1_book_rule_beats_v2_global_rule_at_same_position`、`test_new_ruleset_precedence_changes_without_changing_legacy_order`。
- `test_rules_compiled.py` 中的 `_legacy_lock_spans`，以及 2 个用它的测试。**300 组随机等价测试要保留**，参照对象改为 `source_matches` 全量扫描。
- `test_ruleset_persistence.py::test_builtin_tw2sp_protection_covers_bracketed_and_unbracketed_credits`。
- 复现脚本只改入口：`docs/reviews/2026-09-28/scripts/rules/{rule02_precedence_semantics,rule15_zero_width_and_entities,rule10_ui_defaults_qt,probe_edge_cases}.py`、`scripts/perf/benchmark_rules_book.py`，以及本目录的 `scripts/rules/d9_mixed_version_flip.py`。

**验证**
```sh
mise exec -- uv run pytest tests/unit/test_rules_m3.py tests/unit/test_rules_compiled.py tests/unit/test_regex_rules.py tests/integration/test_ruleset_persistence.py tests/integration/test_rules_transform_workflow.py -q
```

### SIMP-04 空壳模块、零调用名字、未用的 i18n 键

**A. 从未被任何代码 import 的 12 个 .py 文件（共 103 行），外加 1 个 JSON**
- 位于 `plugin/OpenCCForSigil/` 下：
  - `app/commands.py`、`core/pipeline.py`；
  - `document/{attribute_scanner,metadata,protected_content,ruby,svg,text_targets,xhtml_processor}.py`；
  - `opencc_backend/interface.py`、`sigil/preferences.py`、`transforms/annotations.py`；
  - `resources/schemas/profile.schema.json`。
- 本轮已复核：plugin、tests、tools 中对这些模块的 import 都是 0。
- 它们只是为了对齐 spec §22 的目录建议。§22 是“最终仓库建议”，其中列出的 `ui/main_window.py` 等文件本来就不存在。
- 删除前运行 `tools/validate_artifact.py`，确认它没有把这些文件列为必需成员。如果列了，一并去掉。

**B. 只在定义处和 `__all__` 中出现的名字**（删除定义，并从 `__all__` 中去掉）

| 位置 | 名字 |
| --- | --- |
| `rules/importers.py:146-163` | `parse_rules`、`import_tsv/csv/json/opencc_txt` |
| `rules/exporters.py:176-197` | `export_json/tsv/csv/opencc_txt` |
| `rules/store.py:222-229` | `save_ruleset`、`load_ruleset` |
| `rules/precedence.py:57-63`、`:92` | `precedence_key`（2026-09-28“其他观察”要求删除；它的 docstring 与实际排序相反） |
| `rules/validators.py:37-41` | `ValidationIssue` |
| `rules/models.py:55, 234-235` | `_new_id`、`RuleSnapshot.build/from_rules` |
| `rules/conflicts.py:140` | `detect_conflicts` |
| `rules/compiled.py:35, 84-110` | `CompiledOverlay.index` 首字符桶，已被 `*_literal_index` 取代。`test_rules_compiled.py:138` 对它的断言改为断言 `source_literal_index` |
| `core/classifier.py:120-129` | `comparative_classification` |
| `core/diagnostics.py:94-108, 137-138` | `diagnose_script`、`diagnostic_schema_version` |
| `core/converter.py:20-22` | `Converter` Protocol |
| `document/diagnostics.py:77-86` | `inline_boundary_codes`、`find_inline_boundaries` |
| `document/tokenizer.py:257-258, 559-565` | `tokenizer_strategy`、`_split_entity_boundaries` |
| `document/xml_processor.py:181-182` | `processor_name` |
| `transforms/punctuation.py:70-73`、`transforms/quotations.py:85-88` | `transform_punctuation`、`convert_quotations` |
| `logging_ext/report.py:22-23, 239-247` | `report_schema_version`、`validate_report` |
| `logging_ext/retention.py:94-110` | `cleanup_history` |
| `logging_ext/history.py:227-231` | `report_inputs` |
| `app/profiles.py:454-463` | `load_profile` |
| `app/errors.py:44-49` | `ConversionError`、`VerificationError` |

每删一个名字，先用 `grep -rn "<名字>" plugin tests tools docs/reviews/2026-09-2*/scripts` 确认零引用。如果某个复现脚本引用了它，按全局约束只改脚本入口。

**C. 未用的 i18n 键**（三种语言一起删，并同步 `tools/validate_artifact.py`）
- 完全没有引用：`rules.default_settings`、`scope.run_summary_documents`、`scope.selected_file`。
- 运行时从不使用，只被校验器列为必需：
  - `history.select`；
  - `result.status.cancelled`：代码实际用 `cancelled_unchanged`，校验器改列新键；
  - `rules.new_ruleset`：实际用 `new_set`；
  - `rules.opencc_label`、`rules.pre_rules_label`、`rules.post_rules_label`：实际用 `*_stage`；
  - `rules.transfer_group`；
  - `preview.apply_decisions`：实际用 `_one`/`_many`；
  - `rules.confidence.medium`：分类器只产生 high/low，见 `core/classifier.py:200-203`。
- 生产中不可能出现的动态值：`history.status.partial_failure`、`history.status.failed`、`history.status.cancelled`。历史只接受 success 和 completed（`logging_ext/history.py:197-201`）。

**验证**
```sh
mise exec -- uv run ruff check plugin tests tools
mise exec -- uv run pytest tests/unit/test_i18n.py tests/unit/test_artifact_validator.py tests/unit/test_rules_m3.py tests/unit/test_rules_compiled.py tests/unit/test_package_smoke.py -q
```

### SIMP-05 `RuleWindowResult` 的旧形状、`_managed`、删空后自动重建 default

**证据**
- `edit_rules` 总是传 `rulesets=`，所以 `_managed=True`（`ui/rules_window.py:391`）。`_apply` 因此总是返回带 `run_ruleset_ids` 的结果（`:2328-2333`）。
- `app/settings.py:332-340`（结果是 tuple 的分支）和 `:364-367`（`run_ruleset_ids is None` 的分支）只有测试会走到。
- 在托管模式下永远存在不能删除的 default，所以 `ui/rules_window.py:1254-1256`（删空后自动重建 default）不可达。

**删除步骤**
1. 删除 `settings.py:332-340` 和 `:364-367`。`RuleWindowResult.run_ruleset_ids` 的默认值改为 `()`，类型改为 `tuple[str, ...]`。
2. 删除 `_managed` 字段及其判断（`:359`、`:391`、`:2327`）。
3. 删除 `:1254-1256`。

**受影响的测试**：`test_ruleset_persistence.py` 中构造 `RuleWindowResult` 时没有传 `run_ruleset_ids` 的用例（例如 `test_renamed_ruleset_id_can_be_reused_without_deleting_the_new_set`），显式补上。

**验证**：`mise exec -- uv run pytest tests/integration/test_ruleset_persistence.py tests/unit/test_rules_window.py -q`

### SIMP-06 `conservative.json`

**证据**
- 真正的默认方案来自 `app/settings.py:99-109` 的 `_conservative_profile()`，用的是 `Profile()` 的默认值。
- JSON 文件只在 `app/controller.py:67` 被读取，而且只取了 `"conversion"`。
- `_load_conservative_profile`（`:956-976`）还校验了 7 个根本用不到的键；文件本身用的也是旧字段名。

**删除步骤**
1. 删除 `plugin/OpenCCForSigil/resources/defaults/conservative.json`。
2. `controller.py:67` 改用 `Profile().conversion`，然后删除 `_load_conservative_profile`。
3. 从 `tools/validate_artifact.py` 的必需成员和运行时资源检查中去掉它（`:436`、`:541-543`）。

**受影响的测试**：`test_artifact_validator.py` 中参数化到这个文件的一项，以及 `::test_validator_rejects_profile_missing_controller_field`。

**验证**：`mise exec -- uv run pytest tests/unit/test_artifact_validator.py tests/integration/test_plugin_conversion.py -q`

### SIMP-07 PERF-01 多出的快路径，以及重复的 skipped 收集

**证据**（本机测量）
- **LRU 候选缓存**（`core/converter.py:31, 168-174`，`rules/compiled.py:184-199`，测试 `test_compiled_source_candidate_cache_reuses_entries_and_stays_bounded`）：
  - 去掉后，tools 基准从 0.548/0.523 s 变为 0.649/0.603 s，仍 ≤ 0.8 s；
  - 真实 OpenCC 书的耗时在噪声范围内。
  - tools 基准的命中率是 91.8%，真实规则书只有 44.6%。容量 256 恰好对上 tools 基准“每 247 个节点重复一次”的规律，看起来像是按基准调出来的。
- **`include_single_char_rules` 与 `*_has_single_char_literals`、`*_regex_rules` 字段**（`rules/compiled.py:50-52, 124-134`；`rules/matching.py:146-154, 166-170, 384`）：收益为 0%（0.549 对 0.548 s）。
- **无保护区间时的重复循环**（`rules/matching.py:312-334`）：tools 基准快 3.5–9%，真实书在噪声内。它还复制了一份 RULE-04 的 skipped 收集逻辑。
- **4 份相同的 skipped 收集代码**：`rules/matching.py:296-302, 318-324, 344-350, 423-428`。

**删除步骤**
1. 删除 LRU 候选缓存及其测试。
2. 删除 `include_single_char_rules` 参数和 3 个相关字段。`replace_stage` 的签名只保留 `literal_index`、`order` 和 `skipped`。
3. 删除 `matching.py:312-334` 的特化循环，统一走通用循环。
4. 把 4 份 skipped 收集代码抽成一个函数 `_note_skipped(skipped, candidate, winner)`。
5. 保留以下两项：`_unlocked_request`，这是计划要求的，但要在 `__init__` 中初始化为 `None`，不要再用 `getattr` 读取；`_index_change_spans` 的 TokenChange 快路径，它实测快 33%。

**验收**
- `mise exec -- uv run python docs/reviews/2026-09-29/scripts/perf/fuzz_prefix_index.py` 输出 `mismatches=0`。这个脚本会按现有签名传参。
- `tools/benchmark_rules.py` 两种书形都 ≤ 0.8 s。
- `benchmark_rules_book.py --modes current` 的 digest 仍为 `8bab6319592d5abb`，plan 中位数不比删除前慢 10% 以上。

### SIMP-08 Phase-0 的“空跑成功”路径

**证据**
- `plugin.xml` 声明 `<type>edit</type>`，Sigil 的 edit 插件总会拿到带 `text_iter` 和 `readfile` 的 BookContainer（spec §3）。
- 现在宿主缺这两个 API 时，插件静默返回 0，也就是“成功”，日志事件名叫 `skeleton_noop`（`app/controller.py:107-110, 750-762, 868-871`，`app/session.py:98-101`）。

**删除步骤**：删除上述分支。缺 API 时走正常的错误路径：`_book_supports_conversion` 返回 False，改为抛出带明确信息的异常，并显示本地化错误。

**受影响的测试**：删除 `tests/integration/test_plugin_noop.py` 和 `test_session.py::test_session_uses_explicit_phase0_noop_path`。另加一个测试，断言缺 API 时返回非 0，并显示本地化错误。

**验证**：`mise exec -- uv run pytest tests/unit/test_session.py tests/integration -q`

### SIMP-09 两边都没走过的防御分支，以及抄错的兜底值

**证据**
- 以覆盖率对 500 个探测点分类：295 个在 fake 测试和真 PySide6 offscreen 下都没走过。
- 根因：`tests/support/fake_qt.py:141-153` 的 `Base.__getattr__` 让任何方法都“存在”并返回 None，于是生产代码加了大量 `is None` 兜底。
- `getattr(Qt, "UserRole", 32)`（`ui/rules_window.py:1305, 1386, 1405, 1847`）里的 32 抄自测试替身，真实值是 256。
- `ProgressReporter._elided_filename`（`ui/preview_window.py:229-253`）按像素截断的分支依赖 `QProgressDialog.label()`，但 PySide6 和 PyQt5 都没有这个方法，所以生产中实际一律按 55 个字符截断。

**删除步骤**（这是最后一个 A 组条目，逐文件做，每删一个文件就跑一次该文件的测试）
1. 删除 `_visible_entries_cache` 的 10 处 `getattr(self, "_visible_entries_cache", …)`。它在 `:1752` 已经初始化。
2. 删除不可能为假的守卫：`hasattr(self, "list_widget")`（`:4432-4433, 4463`）、`hasattr(self, "options_panel")`（`:3879`）、`hasattr(self, "filter_edit")`（`:4450`）。
3. `ui/qt.py` 的 `exec_dialog` 只保留 `exec`（两个绑定都有）；`enum_value`（`:131-150`）只保留平铺查找。
4. `UserRole` 的兜底值改为读取 `qt.Qt.ItemDataRole.UserRole` 或 `qt.Qt.UserRole`，不写魔法数字。
5. `_elided_filename` 删掉按像素截断的分支，保留 55 字符截断。
6. 以上以外的“两边都没走过”的分支，**本条不删**，留给 SIMP-31。

**验证**：`mise exec -- uv run pytest -q`，再跑一遍真实 Qt 验收 `check_ui_acceptance.py --verify`。

### SIMP-10 导出 OpenCC TXT 时丢掉所有 V2 规则（bug）

**证据**
- `rules/exporters.py:127` 的 `_opencc_txt_rules` 要求 `semantic_version == 1`。
- v0.2.5 以后新建的规则集都是 V2，所以导出 TXT 得到空文件（`evidence/rules/fix07_fix08_import_edges.out` 最后一行：`TXT export text: '' warnings: (True, 1)`）。
- TXT 格式里本来就没有版本信息，导入时版本取目标规则集的版本（RULE-02 第 1 步），所以这个条件没有意义。

**删除步骤**：删除 `:127` 这一行条件。`:110` `_delimited_loses_semantics` 中的 `semantic_version != 1` **本条不动**，等 D9 决定后在 SIMP-24 中处理。

**测试**：`tests/unit/test_rule_import_export_roundtrip.py::test_opencc_txt_export_keeps_v2_literal_rules`：`import_rules("软件\t軟體\n", format="tsv", direction="s2t")` 得到的规则导出为 TXT，结果非空，且再导入后源和目标不变。同时调整 `test_rules_m3.py` 中断言“跳过”数量的两个测试。

**验证**：`mise exec -- uv run pytest tests/unit/test_rules_m3.py tests/unit/test_rule_import_export_roundtrip.py -q`

---

## B 组：已批准（SIMP-17 除外）

### SIMP-11 规则模板

- **是什么**：规则编辑器里的“模板”按钮和 4 个模板（`rules/templates.py`，78 行；`ui/rules_window.py:738-745` 的按钮和 `:1756-1827` 的 `_fill_template`）。
- **为什么删**：spec 没有要求。4 个模板都生成正则，与 INVARIANTS #24“regex 默认关闭”的方向相反。“整理空格”就是 RULE-01 事故的源头；“署名保护”与内置规则包重复。
- **删除内容**：
  - 上述代码；
  - `rules.template_*` 共 12 个键 × 3 种语言，以及 `tools/validate_artifact.py:355-366`；
  - `rule-guide.md` 和 `docs/rules-and-profiles.md` 里介绍模板的句子。
- **受影响的测试**：
  - 删除 `test_regex_rules.py::test_signature_template_protects_marked_credit_and_horizontal_spacing`。
  - `test_collapse_spaces_template_plans_600_matches_across_60_files` 是 RULE-01 的回归测试，**不能删**，改为直接构造同样的规则。
  - `test_rules_window.py` 中与模板相关的 2 个测试。
  - `../2026-09-28/scripts/rules/rule01_regex_hit_budget.py` 和本目录的 `d8_regex_run_cap.py` 只改入口：把 `collapse_horizontal_spaces(1)` 的返回值内联到脚本里。
- **验证**：`mise exec -- uv run pytest tests/unit/test_regex_rules.py tests/unit/test_rules_window.py tests/unit/test_i18n.py -q`

### SIMP-12 文件页的 Checkpoint 横幅

- **为什么删**：spec 只要求 Apply 时的确认（§9.5、§21.2），这部分保留（`preview_window.py:3635-3661`）。横幅说的是同一件事，而且它出现时插件已经在运行。
- **删除内容**：
  - `preview_window.py:4092-4094, 4120-4121, 4313-4330, 4344-4390`；
  - `choose_scope` 的相关参数；
  - `controller.py:162, 200-201, 211-212, 218, 246, 251-252`；
  - 4 个键：`scope.checkpoint_notice/hide/close`、`a11y.banner.dismiss_checkpoint`，以及 `validate_artifact.py:100-102`。
- **受影响的测试**：删除 `tests/unit/test_scope_checkpoint_notice.py`；修改 `test_scope_selection.py::test_scope_notice_banners_use_information_icons_and_palette_surface` 和 `test_plugin_conversion.py::test_scope_cancel_preserves_checkpoint_and_window_preferences`。
- **验证**：`mise exec -- uv run pytest tests/unit/test_scope_selection.py tests/integration/test_plugin_conversion.py -q`

### SIMP-13 两个诊断开关

- **为什么删**：关掉 `detailed_classification` 后，`core/converter.py:94` 不再做比较分类，于是不会再产生 `regional` 类别和 REVIEW 风险，而 §10.4 要求有“地区词汇”筛选。也就是说，这个开关本身会让 spec 要求的功能失效。
- **删除内容**：
  - `ui/run_options.py:15-18, 24, 163-164, 447`；
  - `ui/profile_compare.py:15, 23-25, 43-45`；`ui/profile_window.py:458-466, 625-634`；
  - `controller.py:358-359` 不再传这两个参数，使用 `ConvertRequest` 的默认值 True。`ConvertRequest` 的字段保留，沙箱还在用；
  - `settings.current_profile` 要过滤掉这两个面板键，否则它们会留在方案的 extras 里；
  - 删除 `options.diagnostics`、`options.diagnose_mixed`、`options.detailed_classification` 三个键。
- **受影响的测试**：`test_profile_compare.py` 中 2 个。
- **验证**：`mise exec -- uv run pytest tests/unit/test_run_options.py tests/unit/test_profile_compare.py tests/unit/test_profile_window.py -q`

### SIMP-14 “接受/跳过语言标签组”两个按钮

- **为什么删**：语言标签作为一组显示（§15.2），这个语义保留（`core/planner.py:117-129`、`core/preview.py:29-41`）。但整本书只有一个 `language_metadata` 组，而逐项接受或跳过时本来就会连带整组（`preview_window.py:3301-3312`）。
- **删除内容**：
  - `preview_window.py:1799-1815`；菜单项 `:2104-2111`；
  - `_update_group_controls`、`_decide_current_file_groups`（`:3380-3420`）；
  - 键 `preview.accept_language_group`、`preview.skip_language_group`、`preview.group_prompt`。
- **受影响的测试**：`test_preview_window.py` 中 3 个，`test_preview_decision_history.py` 中 1 个。
- **验证**：`mise exec -- uv run pytest tests/unit/test_preview_window.py tests/unit/test_preview_decision_history.py -q`

### SIMP-15 导入的 strict 模式

- **为什么删**：`rules.skip_invalid` 复选框默认勾选，即 lenient 模式；批量粘贴固定用 lenient。strict 模式在第一行错误就抛异常，不给预览。spec §12.2 的流程是 Parse → Validate → … → Preview，lenient 加预览已经满足。
- **删除内容**：
  - `strict` 参数和 `rules/importers.py` 中的 4 个分支（`:128, 257, 316, 358`）；
  - 复选框（`ui/rules_window.py:2152-2153, 2170, 2192`）；
  - 键 `rules.skip_invalid`。
  - JSON 整体结构损坏时仍然抛异常，这部分不变。
- **受影响的测试**：
  - 删除 `test_rule_import_export_roundtrip.py::test_strict_json_import_fails_on_first_invalid_record_without_result`；
  - 另有 3 个测试改为断言 diagnostics。
- **验证**：`mise exec -- uv run pytest tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_rules_m3.py tests/unit/test_rules_window.py -q`

### SIMP-16 方案文件的兼容垫片

- `app/profiles.py:44-85` 的 `_KNOWN_FIELDS`：零引用，与 `from_dict` 里内联的 `known` 重复，删除。
- 字段别名（`:144-152, 200-205`：`include_nav/ncx/metadata`、`svg_text`、`quotation`、`punctuation`）：所有发布版都写规范字段名，删除。之后别名键会落进 extras，不报错。
- 5 个兼容属性（`:291-311`，如 `.include_nav`）：生产代码和测试都不访问，删除。
- schema 0 迁移（`:378-387`）：所有发布版都写 `schema_version`，删除。之后遇到这种文件会显示加载错误，不会静默出错。
- `language_region` 的多种写法（`profiles.py:91, 124`；`settings.py:29-30`；`profile_compare.py:28-29`；`profile_window.py:93`）：在 `from_dict` 中一次性把 `auto→""`、`zhTW→zh-TW`、`zhHK→zh-HK`，删除另外 3 处归一化。**这同时修掉一个 bug**：`zhTW` 现在能通过校验，但 `transforms/language_tags.py:26` 只认 `zh-TW`，所以设置了也不生效。
- `RunSettings.recovery_notice` 单值属性（`settings.py:47, 203-204`）：生产代码只用列表形式，删除。
- **保留**：`language_preset: "legacy"`，这是 spec §15 规定的选项。
- **验证**：`mise exec -- uv run pytest tests/unit/test_profiles_m3.py tests/unit/test_profile_compare.py tests/unit/test_profile_window.py tests/unit/test_storage_recovery.py tests/integration/test_plugin_conversion.py -q`

### SIMP-17 中转链改为固定链：**本轮不做**

下面的内容只作为备查保留。不做的原因：还不确定是否有人依赖 t2s 的其他 4 条中转链。


- **事实**：`core/transformation.py:18-31` 的 `FORCE_PIVOT_CHAINS` 里，除 t2s 外，每个目标只有 1 条链。t2s 有 5 条，其中 `(s2twp, t2s)` 和 `(s2hkp, t2s)` 会把“软件→軟體”再转成“软体”。
- **修法**：t2s 固定用 `("s2t", "t2s")`，其他目标用唯一的那条链。删除 `ui/run_options.py:169, 245, 256-259, 276-278, 309-322, 364-368, 651-660`，以及 `option_enablement` 和 `_profile_for_values` 里的 pivot 部分。方案字段 `pivot_chain` 保留，加载时归一。
- **受影响的测试**：`test_run_options.py` 中 5 个与 pivot 相关的测试。
- **验证**：`mise exec -- uv run pytest tests/unit/test_run_options.py tests/unit/test_m4_transforms.py -q`

### SIMP-18 5 个重复的小入口（5 项都做）

1. **方案窗口的“从当前设置新建”**（`ui/profile_window.py:271-276, 290, 551-564`，键 `profile.from_current`）：与设置页的“保存为方案”重复。删除按钮、处理函数和键。
2. **“规则集设置…”里的默认方向、默认范围**（`ui/rules_window.py:578-603, 967-980`）：RULE-10 和 FIX-06 之后，新规则一律用当前方向，这两个设置只剩下误导作用。
   - 删除 `default_direction_combo`、`default_scope_combo`，以及设置对话框里对应的两行 `addRow`、`:805` 的信号连接、`_load_ruleset_metadata` 和 `_ruleset_metadata_changed` 中读写这两个控件的代码。
   - `_stash_ruleset()` 改为原样保留 `current.default_direction` 和 `current.default_scope`，不从控件读取。
   - `_apply_rule_defaults()` 改为：方向一律预选 `base_direction(self._config)`，范围一律预选 `"global"`。它不再读取规则集的默认值，已经写在磁盘上的 `default_direction` 也就不再影响预选。
   - schema 字段保留；`import_rules(default_direction=…)` 仍用导入对话框里选的方向补缺失值。
   - 删除键 `rules.default_direction`、`rules.default_scope`。先用 grep 确认没有其他引用。
   - 本项做完后，“规则集设置…”对话框里只剩全局启用复选框；SIMP-25 会把整个对话框删掉。
3. **Jieba 的“详情”按钮**（`ui/preview_window.py:3763-3767, 3800, 3873, 3878, 3911-3919`）：原因已经写在 `jieba_status` 标签和 tooltip 里。删除按钮及其处理函数，以及键 `config.jieba_details`、`config.jieba_details_title`。受影响的测试：`test_conversion_dialog_jieba.py::test_jieba_details_is_hidden_without_error_and_visible_after_failure`，改为断言失败原因出现在 `jieba_status.toolTip()` 中。
4. **规则窗口和方案窗口里的“正在检测 Jieba”提示**（`ui/rules_window.py:516-520`，`ui/profile_window.py:209-212, 444-446, 469-471`）：这两个窗口不做分析，删除这个提示。
5. **合并窗口摘要中重复的 Jieba 状态行**（`ui/preview_window.py:565-573` 的 `capability` 一段）：删除这一段。
   - 同一段文字已经显示在设置页的 `jieba_status` 标签里（`:3853-3859`）。
   - 按 D15 改写探针：`docs/reviews/2026-09-27/ui-workflow/scripts/check_run_summary.py:348-356` 中，`translator.text(...) in report["summary"]` 这两处断言改为检查设置页的状态标签，即 `in captured["config"].jieba_status.text()`。`captured` 已经在该函数里保存了配置对话框。断言的内容不变，只改检查位置。
   - `available` 分支里的 `translator.text("config.jieba") in report["summary"]` 断言检查的是方向名称里的“Jieba”，不属于被删的段落，保持不变。

**验证**
```sh
mise exec -- uv run pytest tests/unit/test_profile_window.py tests/unit/test_rules_window.py tests/unit/test_conversion_dialog_jieba.py tests/integration/test_jieba_probe_flow.py tests/integration/test_ruleset_persistence.py -q
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-27/ui-workflow/scripts/check_run_summary.py --verify
```
`check_run_summary.py` 的参数以它的 argparse 为准。

### SIMP-19 方案摘要里 8 个不生效的字段

下面 8 个字段显示在方案摘要和方案比较里，但在运行时从不被读取，或者只能取固定值。本轮已用 grep 核实：除 `app/profiles.py`、`ui/profile_window.py`、`ui/profile_compare.py` 外，运行时代码里没有读取这些字段；`run_options.py:21-27` 只是把它们列为“方案专有字段”。

| 字段 | 为什么不生效 |
| --- | --- |
| `scope` | 运行范围来自范围选择，不来自方案（`deviations.md`：“A loaded profile never widens the target set”） |
| `preview_required` | 从不被读取；预览本来就是强制的（INVARIANTS #18） |
| `tofu_policy` | 实际值取自 manifest（`opencc_backend/backend.py:288`），§13 也说它不属于方案参数 |
| `regex_rules` | `profiles.py:340-342` 规定只能是 False，但界面显示“正则规则：否”的同时，正则规则照样执行 |
| `convert_svg_text` | 只能是 False |
| `review_annotations` | 只能是 False，从不被读取 |
| `checkpoint_notice` | 真正的开关在偏好里（`settings.py:503-511`），方案里的这个字段从不被读取 |
| `numeric_cjk_char_refs` | 从不被读取；生效的是 `decode_numeric_cjk_refs` |

**改动**
1. 从 `ui/profile_window.py:33-65` 的 `_PROFILE_SUMMARY_KEYS` 删除这 8 个键。
2. 从 `:69-72` 的 `_PROFILE_COMPARISON_PRIORITY` 删除其中出现的键（`scope`、`regex_rules`、`tofu_policy`、`numeric_cjk_char_refs`）。
3. `ui/profile_compare.py:50-52` 的运行时字段列表中如果有这些字段，一并删除。
4. schema、`Profile` 字段、校验都不动；方案文件照常读写这些字段。
5. 删除只被这几行使用的 i18n 键，例如 `profile.preview_required`、`profile.regex_rules`、`profile.review_annotations`、`profile.numeric_cjk_char_refs`、`profile.tofu_policy.*`。每个键都先 grep 确认，`profile.tofu_policy.{value}` 是动态键，见文末。

**保留**：`mathml`（它确实生效，只转换 `mtext`，而且没有界面控件，摘要是用户唯一能看到它的地方；`check_run_summary.py:228-235` 断言它可见）、`attributes`、`protected_elements`、`segmentation`、`convert_nav`。`convert_nav` 在 SIMP-28 中处理。

**受影响的测试**：`test_profile_window.py`、`test_profile_compare.py` 中断言这些行的测试，改为断言它们不出现。

**验证**：`mise exec -- uv run pytest tests/unit/test_profile_window.py tests/unit/test_profile_compare.py tests/unit/test_run_options.py -q`

### SIMP-20 历史窗口的“状态”筛选

- **证据**：`logging_ext/history.py:197-201` 只接受 success 和 completed，两者显示出来都是“已完成”。
- **删除内容**：
  - `ui/history_window.py:148-159` 的 `history_status_filter` 及其信号连接；
  - `ui/history_filters.py:15, 30-33` 的状态参数和判断；
  - 键 `history.filter_all_statuses`。
  - 方向筛选和搜索框保留。
- **按 D15 改写探针**：`docs/reviews/2026-09-27/ui-workflow/scripts/check_history_layout.py:78-94`。
  - 删掉两处 `dialog.history_status_filter.setCurrentIndex(...)`。
  - 先读该脚本生成 `records` 的代码，找出 `expected` 表达式里哪个取模条件对应 status，只删掉这一个条件，其余条件不变。
  - `anded_filters_match_exact_metadata` 检查仍然要求 `len(expected) > 0`。
- **受影响的测试**：`test_history_filters.py::test_unknown_status_is_an_exact_filter_value` 删除；`::test_thousand_history_rows_use_anded_metadata_filters_and_normal_text` 去掉状态条件。
- **验证**：
  ```sh
  mise exec -- uv run pytest tests/unit/test_history_filters.py tests/unit/test_history_report_self_test.py -q
  QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-27/ui-workflow/scripts/check_history_layout.py --verify
  ```
  `check_history_layout.py` 的参数以它的 argparse 为准。

### SIMP-21 “词典检查”并入“规则测试”

- **现状**：测试区有两个按钮。`_test`（`ui/rules_window.py:1915-1968`）在窗口内显示结果；`_inspect`（`:1970-2004`）另开一个对话框（`:182-268`）。两者调用的是同一个 `inspect_dictionary()`（`:119-179`）。
- **改动**：
  1. 把 `_inspect` 里“输入框为空时，取可见选中规则的 source”的逻辑（`:1976-1980`，用 `_rule_index_at_row`）搬到 `_test` 开头；两处都为空时显示 `input_required`。然后把 `show_dictionary_inspector` 显示的 comparison 行和署名行（配置名、分类、规则标签）追加到 `_test` 的输出末尾，写法照抄 `show_dictionary_inspector` 里拼这些行的代码。
  2. 删除 `_inspect`、`show_dictionary_inspector`、`inspect_button`（`:764-768, 812`），以及键 `rules.inspect`、`rules.inspector_title`（同步 `validate_artifact.py:320-321`）。
  3. 删除偏好键 `dictionary_inspector_dialog_size` 的读写。
  4. `docs/deviations.md` 追加：“The read-only Dictionary Inspector (spec §86, SHOULD) is shown inline in the rule test output instead of a separate dialog.”
- **受影响的测试**：
  - `test_rules_window.py::test_dictionary_inspector_localizes_config_classification_and_rule_labels`：改为断言 `_test` 的输出里有这些本地化行。
  - RULE-13 的回归测试 `test_inspect_without_input_uses_the_visible_selected_rule`：改为断言输入框为空时，`_test` 使用的是可见的选中行，也就是过滤后检查的是“乙方”。**断言强度不变**。
  - 直接测 `inspect_dictionary()` 的用例保留。
- **验证**：`mise exec -- uv run pytest tests/unit/test_rules_window.py tests/unit/test_i18n.py tests/unit/test_artifact_validator.py -q`

### SIMP-22 “有 N 条规则属于其他书籍或方案”提示

- **为什么删**：表格里已经标出“其他书籍/其他方案”，详情里有原因，“本次不生效”筛选也在。这个提示还会带出无关规则（`evidence/rules/fix16_foreign_owner_banner.out`）。
- **删除内容**：
  - `ui/rules_window.py:614-618` 的 `foreign_owner_button`；
  - `:1453-1468` 的 `_update_foreign_owner_button` 和 `_filter_foreign_owner_rules`，以及 `_refresh()` 中对前者的调用；
  - 键 `rules.foreign_owner_count`。
- **保留**：`_foreign_owner_scope()`、“其他书籍/其他方案”标注、改绑按钮。
- **受影响的测试**：`test_rules_window.py` 中断言这个提示的测试删除。`test_foreign_book_rule_is_labelled_other_book`、`test_rebind_button_binds_current_book_only_on_click` 保留。本目录的 `scripts/rules/fix16_foreign_owner_banner.py` 以后会报 AttributeError，这是预期的；在 `04-implementation-results.md` 中注明“按 SIMP-22 删除”。
- **FIX-16 不做。**
- **验证**：`mise exec -- uv run pytest tests/unit/test_rules_window.py tests/unit/test_i18n.py -q`

---

## C 组：已批准 SIMP-23 至 SIMP-30；SIMP-31、SIMP-32 不做

### SIMP-23 正则的 3 个整次分析限额（D8：删除）

**哪些保留，哪些删除**

| 限额 | 作用范围 | spec §11.5 | 处理 |
| --- | --- | --- | --- |
| 单次搜索 50 ms | 单次调用 | “禁止灾难性回溯；单规则超时” | 保留 |
| 每条规则 512 次命中 | 单规则 × 单片段 × 单阶段 | “最大替换次数保护” | 保留 |
| 候选数 20,000 | 单规则 × 单片段 | 内存保护 | 保留 |
| 正则最多 128 条、每条最多 512 字符 | 规则集 | — | 保留 |
| 时间预算 3 s + 2 s/百万字符 | **整次分析** | 未要求 | 删除 |
| 总命中 100,000 | **整次分析** | 未要求 | 删除 |
| 已采用输出 2,000,000 字符 | 整次分析 | 未要求 | 删除，它已被候选输出覆盖 |
| 候选输出 2,000,000 字符 | 整次分析 | — | 保留，改为按片段计 |

**证据**
- `evidence/rules/d8_regex_run_cap.out` 和 `d8_regex_tiny_fragments.out` 都是合法的书在整次限额上失败。
- 沙箱每次都新建 converter，这些限额在沙箱里永远不会触发。这就是“沙箱通过、真书失败”反复出现的根源。
- 共享预算只在 `overlay.guarded` 时生效（`core/converter.py:163-165`）。结果是：加一条 replace 规则，字面规则的输出上限就从“每段”变成了“整本书”。
- 同一条正则会被编译 3 次（`rules/compiled.py:69, 86-103`）。

**改动**
1. `rules/matching.py`：删除 `REGEX_RUN_BUDGET_SECONDS`、`REGEX_SECONDS_PER_MILLION_CHARS`、`REGEX_MAX_HITS_PER_RUN`、`REGEX_MAX_OUTPUT_CHARS_PER_RUN`，以及 `RegexBudget` 中对应的字段和方法（`scanned_chars`、`note_scan`、`allowance`、`regex_seconds`、`regex_hits` 等）。`timeout_for` 直接返回单次超时 50 ms。
2. 候选输出改为按片段计数：在 `collect_matches()` 内用局部变量累计，超过 2,000,000 字符时抛出与现在相同格式的 `RuleExecutionError`。
3. `RegexBudget` 只保留 `zero_width_skips`。删除 `guarded` 标志，以及 converter 里跨 target 共享的预算对象（`core/converter.py:161-165`）；每次 `convert()` 新建一个 `RegexBudget`，只用来收集零宽计数。
4. `rules/compiled.py`：每条正则只编译一次，复用 `validate_rules` 编译出的 pattern，删除 `:86-103` 的重复编译和重复检查。
5. 同步更新 `docs/rule-format.md` 和三种语言的 `rule-guide.md`：删掉“整次分析最多 100,000 处”和时间预算的说法，保留“每条正则在一段文字中最多替换 512 处；单次搜索超过 50 ms 即停止”。

**受影响的测试**（`tests/unit/test_regex_rules.py`）
- 删除或改写：`test_expired_regex_budget_stops_with_rule_identity`、`test_regex_budget_allowance_grows_with_scanned_text`、`test_replacement_output_budget_covers_every_stage`、`test_replacement_output_budget_accepts_exact_limit_and_protect_does_not_use_it`、`test_a_new_converter_starts_a_fresh_rule_output_budget`。
- `test_overlapping_regex_candidates_do_not_count_as_hits`：改为断言每片段命中计数为 1。
- 保留：`test_runaway_regex_in_one_fragment_still_stops`、`test_regex_candidate_budget_is_per_rule_and_fragment`、`test_collapse_spaces_template_plans_600_matches_across_60_files`（SIMP-11 之后改为直接构造规则），以及 FIX-17 新增的 `test_single_regex_search_timeout_still_stops`。

**验收**
- `scripts/rules/d8_regex_run_cap.py` 输出 `ok`。这个脚本读 `budget.regex_hits`，删除后按全局约束只改入口：打印 `ok` 和已处理段数即可。
- `scripts/rules/d8_regex_tiny_fragments.py` 四行都是 `ok`。脚本中打印 `allowance()`、`regex_seconds` 的部分同样只改入口。
- `scripts/rules/fix17_regex_timeout.py` 仍然在约 50 ms 时报错。
- `../2026-09-28/scripts/perf/probe_regex_budget.py --regex-rules 128 --files 200,400` 两行都是 ok。

**验证**
```sh
mise exec -- uv run pytest tests/unit/test_regex_rules.py tests/unit/test_rules_compiled.py tests/integration/test_rules_transform_workflow.py -q
for s in d8_regex_run_cap d8_regex_tiny_fragments fix17_regex_timeout; do mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/$s.py; done
```

**不要做**：不删单次超时、每片段命中上限或候选上限；不改 `cursor = found.start() + 1`。

### SIMP-24 V1/V2 两张范围表合并（D9：只用 §11.2 的顺序）

**现状**
- spec 全文没有 V1/V2 这个概念，它是 2026-09-26 的 v0.2.5 才引入的。
- V1 表是书 > 全局 > 方案，与 §11.2 一致；V2 表是书 > 方案 > 全局，与 §11.2 相反，也没有记入 `docs/deviations.md`。
- 同一起点只要有一条 V2 候选，就整体切换到 V2 表，所以会发生非局部的翻转（`evidence/rules/d9_mixed_version_flip.out`）。

**改动**
1. `rules/precedence.py:45-54`：`scope_rank` 只保留 V1 表 `{"book": 3, "global": 2, "profile": 1, "builtin": 0}`，删除 `legacy` 参数。
2. `rules/matching.py:120-128`：`_resolve_same_start` 删除按候选计算 `legacy` 的代码，直接用 `scope_rank(rule)`。
3. `rules/precedence.py:74-78` 的 `ordered_rules`：去掉对 `legacy` 的传参，只用一张表。
4. `rules/exporters.py:110`：`_delimited_loses_semantics` 删除 `rule.semantic_version != 1` 条件。
5. 删除规则详情中的版本行（`ui/rules_window.py:1576-1578`），以及 `rules.detail_version`、`rules.version_v1`、`rules.version_v2` 三个键。
6. `semantic_version` 字段保留，因为它还决定 `action/stage/match_type` 的解读和校验，只是不再影响范围顺序。`rule_dedup_key` 不变。
7. **必须保留** V2 的“source 非空即可”校验，否则已有的纯空白规则会让整个规则集被隔离。`docs/deviations.md` 追加：“Rule sets created since v0.2.5 (semantic version 2) accept any non-empty source; the whitespace/punctuation-only source rejection of spec §11.8.3 applies to version 1 rules only. Scope precedence follows spec §11.2 (book > global > profile) for every rule.”
8. `docs/rules-and-profiles.md:54-59` 改为只描述一种范围顺序：书 > 全局 > 方案。

**代价**：v0.2.5 之后建立的方案规则与全局规则在同一起点竞争时，胜者由方案规则变为全局规则。在 `CHANGELOG.md` 的 Unreleased 一节写明这一点。

**受影响的测试**
- `test_rules_m3.py::test_new_ruleset_precedence_changes_without_changing_legacy_order`：改为断言 V2 规则也按书 > 全局 > 方案。
- 其余约 9 个测试按实际失败逐个调整，每个调整的理由都写进提交说明。
- 300 组随机等价测试保留。
- 新增 `test_rules_m3.py::test_unrelated_v2_rule_does_not_flip_v1_scope_winner`：照抄 `scripts/rules/d9_mixed_version_flip.py`，断言前两种情况的胜者都是 `v1-global`。

**验收**：`d9_mixed_version_flip.py` 的第 1、2 行都是 `v1-global`。如果 SIMP-03 已经删掉 `rules.engine.lock_spans`，脚本按全局约束只改入口，改用 `lock_spans_compiled(text, CompiledOverlay.build(...))`。

**验证**
```sh
mise exec -- uv run pytest tests/unit/test_rules_m3.py tests/unit/test_rules_compiled.py tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_regex_rules.py tests/unit/test_rules_window.py tests/integration/test_rules_transform_workflow.py tests/integration/test_ruleset_persistence.py -q
```

**不要做**：不迁移磁盘上的规则或规则集版本；不改 JSON schema；不从 `rule_dedup_key` 删除 `semantic_version`。

### SIMP-30 导入格式的小变体（在 SIMP-24 之后做）

| 变体 | 位置 | 处理 |
| --- | --- | --- |
| `keep_legacy_blank_direction` | `rules/importers.py:215, 224` | FIX-07 已经删掉，这里不再处理 |
| 旧版带引号 TSV 的警告 | `rules/importers.py:248-255, 266-270`，`ui/rules_window.py:2200`，以及 i18n 键 `rules.import_tsv_quoted_field` | 删除。字段仍然原样导入，只是不再提示 |
| JSON 字段别名 `pattern→source`、`replacement→target` | `rules/models.py:117-120` | 删除，没有测试覆盖 |
| BOM 剥离重复三次 | `rules/importers.py:168-184` | 合并为一次：只在 `_read_import_text`（或同等的入口函数）里剥离一次，删掉 `_delimited_rows` 里的 `lstrip("﻿")` |
| 字符串路径猜测 `"\n" not in value and path.exists()` | `rules/importers.py:166-177` | `ui/rules_window.py` 的导入调用改为传 `Path` 对象；删掉对字符串的路径猜测，字符串一律当作文本内容 |

**受影响的测试**：`test_rule_import_export_roundtrip.py::test_legacy_quoted_tsv_field_warns_but_stays_unchanged` 改为断言字段原样导入且没有诊断；传字符串路径的测试改为传 `Path`。

**验证**：`mise exec -- uv run pytest tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_rules_window.py tests/unit/test_rules_m3.py -q`

### SIMP-25 “规则集设置”对话框整个删掉，`RuleSet.enabled` 只保留“重新启用”（在 SIMP-18 第 2 项之后做）

**现状**
- 用户已经可以用“用于本次转换”（会话）、“保存方案”（持久）和“删除规则集”（RULE-12）来排除规则集。
- 全局停用开关是 03-rules §0 列出的第 2 个开关。它还带着 tooltip、取消勾选前的确认、下拉框后缀、原因文案这一串东西。

**改动**（`ui/rules_window.py`）
1. 删除 `ruleset_settings_dialog` 及其关闭按钮、菜单项“规则集设置…”（`menu_items` 中的对应一项，键 `rules.ruleset_settings`）。
2. 删除 `ruleset_enabled_check`（`:563-564`），以及 `_ruleset_enabled_changed`、`_update_ruleset_enabled_tooltip` 两个方法和它们的所有调用、信号连接。
3. 新增 `self.reenable_ruleset_button = qt.QPushButton(self._translator.text("rules.reenable_ruleset"))`，放在 `ruleset_row` 里 `use_in_run_check` 之后。
   - 只有当前规则集的 `enabled` 为 False 时才可见；可见性在 `_load_ruleset_metadata()` 里设置。
   - 点击时执行 `self._rulesets[self._ruleset_id] = replace(current, enabled=True)`，然后 `self._populate_rulesets()`、`self._refresh()`、`self._mark_test_result_stale()`。
   - 新键 `rules.reenable_ruleset`：“重新启用（此规则集已全局停用）”/“重新啟用（此規則集已全域停用）”/“Re-enable (this rule set is disabled globally)”。
4. `_stash_ruleset()` 和 `_ruleset_metadata_changed()`：不再读取被删的控件，`enabled`、`default_direction`、`default_scope` 原样保留当前值。`_ruleset_metadata_changed` 如果只剩空操作，就删除它和它的调用。
5. 保持不变：规则集下拉框的“· 已停用”后缀、`_rule_is_active()`、`_run_candidates()`、`app/settings.py` 的 `freeze_rules()` 中 `if ruleset.enabled`。已经停用的旧规则集在重新启用之前仍然不生效。
6. 删除键：`rules.ruleset_enabled`、`rules.ruleset_enabled_tooltip`、`rules.disable_shared_ruleset_confirm`、`rules.ruleset_settings`。每个键先用 grep 确认没有其他引用，并同步 `tools/validate_artifact.py`。
7. `RuleSet.enabled` 字段和 schema 不变。

**受影响的测试**
- 删除：`tests/integration/test_ruleset_persistence.py::test_disabling_shared_ruleset_asks_when_other_profiles_reference_it`，以及断言全局开关文案的 `test_i18n.py` 用例（RULE-11 加的“`rules.ruleset_enabled` 不含本次”）。
- 新增：`tests/unit/test_rules_window.py::test_disabled_ruleset_shows_reenable_button_and_click_enables`。构造一个 `RuleSet("A", enabled=False)`，断言按钮可见；点击后 `manager._rulesets["A"].enabled is True`，按钮隐藏，`_apply()` 的结果里 A 为启用。
- 新增：`test_enabled_ruleset_hides_reenable_button`。
- 其余引用 `ruleset_enabled_check`、`default_direction_combo` 的测试（约 7 处），按上述行为改写。
- 旧复现脚本只改入口：
  - `../2026-09-28/scripts/rules/rule10_ui_defaults_qt.py:58` 改为打印 `window.use_in_run_check.text()`；
  - `../2026-09-28/scripts/ux/probe_ux_simplicity.py:238` 同样改为 `use_in_run_check.text()`，JSON 里的键名保留；
  - `../2026-09-28/scripts/rules/rule11_ruleset_enabled_is_global.py:39` 的第一段不能再“取消勾选”，改为：直接把 `shared.json` 写成 `enabled: false`，打开窗口点击 `reenable_ruleset_button`，打印保存后的 `enabled`；
  - 本目录 `scripts/rules/fix03_fix05_rename_new_confirm.py` 的 E 段删掉 `ruleset_enabled_check.setChecked(False)` 那一步，只统计删除和新增的模态框数。

**验证**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/integration/test_ruleset_persistence.py tests/unit/test_i18n.py tests/unit/test_artifact_validator.py -q
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-26/scripts/check_rules_layout.py --verify --width 960 --height 640
```

**不要做**：不删除 `RuleSet.enabled` 字段；不自动重新启用已停用的规则集；不把本次引用写进偏好。

### SIMP-26 `Scope.SINGLE`（撤销 2026-09-28 的 D4）

- **证据**：
  - spec §6.1 只要求三种范围；
  - 生产代码里没有任何地方产生 SINGLE（`ui/preview_window.py:4510-4517`）；
  - `sigil/adapter.py:130-149` 本来就不支持 SINGLE，会抛 `unsupported scope`。
- **删除内容**：
  - `sigil/scope.py:9, 72-75`：`Scope.SINGLE` 及其在 `resolve_target_selection` 中的分支；
  - `preview_window.py:4138-4139, 4148, 4304` 的 `single_radio`（SIMP-01 做完后行号会变，按名字找）；
  - `_ScopeDialog.__init__` 中 `initial_scope is Scope.SINGLE` 的判断改为只看 `len(initial_ids) == 1`；
  - 键 `scope.single`，以及 `tools/validate_artifact.py:90`。
  - `app/profiles.py:86` 的 `_VALID_SCOPES` **保留**字符串 `"single"`，让旧方案文件仍能加载。
- **测试**：
  - 26 处测试夹具里的 `TargetSelection(Scope.SINGLE, ...)` 机械替换为 `Scope.SELECTED`；
  - 删除 `test_scope_selection.py::test_single_scope_requires_exactly_one_known_file`；
  - FIX-17 新增的 `test_single_initial_selection_accepts_as_selected_scope` 改为不传 `initial_scope=Scope.SINGLE`，只传一个初始 ID，断言不变；
  - 探针 `../2026-09-28/scripts/ux/probe_ux_simplicity.py:123` 只改入口。
- **验证**：`mise exec -- uv run pytest tests/unit/test_scope_selection.py tests/unit/test_dialog_construction.py tests/integration -q`，然后 `grep -rn "Scope.SINGLE\|single_radio" plugin tests` 应无输出。

### SIMP-27 `TextTarget.context`

- **现状**：`document/tokenizer.py:281` 固定写 `context=""`，生产代码里没有任何地方读取它。
- **删除内容**：
  - `core/models.py:32` 的 `context` 字段；
  - `document/tokenizer.py` 中的 `context_radius` 参数（`:44-69` 附近的签名和 docstring）和 `:281` 的 `context=""`；
  - 先 grep `context_radius`，调用方都一并去掉这个参数。
- **测试**：删除 `tests/unit/test_models.py:36-40` 中关于 context 的断言，以及 PERF-03 的 `test_tokenizer_does_not_copy_target_context`，改为断言 `not hasattr(target, "context")`。perf 脚本如果引用了它，只改入口。
- **deviations.md**：追加“`TextTarget` does not carry the `context` field listed in the spec §8 data model; preview context is computed from the frozen source when displayed.”
- **验证**：`mise exec -- uv run pytest tests/unit/test_models.py tests/unit/test_converter_diff.py tests/unit/test_preview_diagnostics.py -q`

### SIMP-28 NAV 是否转换只看它在不在文件集合里（在 SIMP-13 之后做）

**现状**
- `include_nav` 只起“排除”作用：`sigil/adapter.py:112` 在 NAV 已经在文件集合里时，把它剔除出去，它从不会把 NAV 加进集合。
- “选择文件”模式下 NAV 本身就是列表里的一行，所以这个开关与列表重复。UXS-09 已经在 NAV 不在选择中时把它隐藏。

**改动**
1. `ui/run_options.py`：
   - `:109-111` 的循环去掉 `("include_nav", True)`，只保留 NCX 和元数据；
   - 删除 `:38`（`option_enablement` 返回的 `include_nav`）、`:192-194`（`_add_check` 中的 NAV 分支）、`:262-263`、`:272` 元组中的 `"include_nav"`、`:328-331`、`:523` 的 `"convert_nav"` 覆盖、`:537` 中的 `convert_nav/include_nav`；
   - 删除所有只为 NAV 开关服务的 `_nav_available` 逻辑。`_nav_available` 如果还被摘要使用则保留。
2. `app/controller.py:318`：去掉 `include_nav=options.get("include_nav", True),`。
3. `sigil/adapter.py:112-113`：删除 `if file_id == nav_id and not selection.include_nav: continue`。NAV 仍然标记为 `"nav"`。
4. `sigil/scope.py:29`：删除 `TargetSelection.include_nav` 字段。先 grep 所有 `include_nav=` 的构造调用，一并去掉。
5. `ui/run_summary.py:27-28`：删除 `nav_requested`；`nav_included = nav_available`。`ui/preview_window.py:547-548` 删除 `nav_disabled` 分支和键 `scope.run_summary_nav_disabled`。
6. `app/settings.py:22` 的 `ALIASES` 删除 `"include_nav": "convert_nav"`。`Profile.convert_nav` 字段和 schema 保留：读写照旧，但不再影响运行。`ui/profile_window.py:37` 从 `_PROFILE_SUMMARY_KEYS` 删除 `convert_nav`。
7. i18n 删除 `options.include_nav`、`options.nav_unavailable`（先 grep）。
8. `docs/deviations.md` 追加：“NAV conversion follows the resolved file set. The optional NAV checkbox of spec §6.1 is not offered: NAV is converted whenever it is in the chosen files (always for ‘all XHTML’, when checked for ‘selected files’, when present in the spine for ‘reading order’). This keeps the §6.2 default of converting NAV when it exists.”

**按 D15 改写探针**：`docs/reviews/2026-09-27/ui-workflow/scripts/check_run_summary.py:223-229`。
- 删键之前，先把三种语言 `options.include_nav` 的值抄成脚本里的字面量。
- 把 `nav_values = detail["rows"][translator.text("options.include_nav")]` 和其后三条 NAV 断言，改为一条：`assert <该语言的字面量> not in detail["rows"]`。
- `mathml_visible_when_unchanged` 相关的断言不变。

**受影响的测试**（`grep -rn include_nav tests` 约 35 处）
- 删除：`test_run_options.py::test_include_nav_hidden_when_nav_not_selected_and_preference_kept`（UXS-09）、`tests/integration/test_plugin_conversion.py::test_nav_preference_is_saved_while_nav_is_outside_scope`。
- 改写：`test_run_summary.py` 中的 `nav_requested`；构造 `TargetSelection(..., include_nav=...)` 的地方去掉这个参数。
- 新增：`tests/integration/test_plugin_conversion.py::test_nav_in_selected_files_is_always_converted`。选中的文件里包含 NAV，断言计划中有 `document_kind == "nav"` 的变更。

**验证**
```sh
mise exec -- uv run pytest tests/unit/test_run_options.py tests/unit/test_run_summary.py tests/unit/test_profiles_m3.py tests/integration/test_plugin_conversion.py -q
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-27/ui-workflow/scripts/check_run_summary.py --verify
grep -rn "include_nav" plugin   # 应无输出
```

**不要做**：不改 `Profile.convert_nav` 字段；不改 NAV 的计数和 `document_kind: nav` 标记；Sigil 没有选择时仍然不默认全书。

### SIMP-29 语言标记只保留“保持不变”和“更新中文标签”

**现状**：两者只在“通用繁体 + legacy + 未选地区”这一种情况下不同：“建议”什么都不改，“强制”报错（`transforms/language_tags.py:17-39`）。其他情况下输出完全一样，而且所有变更都要在预览里逐项决定。

**改动**
1. `transforms/language_tags.py` 新增：
   ```python
   def normalize_language_mode(mode: str) -> str:
       return "force" if mode == "suggest" else mode
   ```
   `target_language()` 开头先执行 `mode = normalize_language_mode(mode)`。取值校验仍接受 `{"keep", "suggest", "force"}`。
2. `app/profiles.py`：`from_dict` 读取 `language_metadata` 后，调用 `normalize_language_mode`。`_VALID_LANGUAGE_METADATA` 保留 `"suggest"`，这样旧文件仍能加载。
3. `ui/run_options.py:156`：下拉框只保留 `("keep", "force")`。把值写进下拉框的地方（构造时的初始值，以及 `_tool("profiles")` 中 `for key, combo in self.combos.items()` 的循环）都先经过 `normalize_language_mode`，避免保存过的 `"suggest"` 找不到选项、被静默变成“保持不变”。
4. i18n：`options.force` 改为“更新中文标签”/“更新中文標籤”/“Update Chinese tags”；删除 `options.suggest`（先 grep）。
5. 通用繁体 + legacy + 未选地区时，沿用现有的 `options.region_required` 提示，阻止分析。
6. `docs/deviations.md` 追加：“Language tags offer Keep and Update. The separate ‘suggest’ mode of spec §15 is folded into Update: for generic Traditional Chinese with the Legacy preset and no explicit region, analysis is blocked with the region prompt instead of silently changing nothing. Saved ‘suggest’ values load as Update.”

**受影响的测试**：`grep -rn "suggest" tests`，约 7 处，改为 `"force"` 或补上 region。新增 `tests/unit/test_run_options.py::test_saved_suggest_language_mode_loads_as_update`：方案里写 `"suggest"`，加载后下拉框的当前值为 `"force"`。

**验证**：`mise exec -- uv run pytest tests/unit/test_run_options.py tests/unit/test_profiles_m3.py tests/unit/test_m4_transforms.py tests/integration/test_plugin_conversion.py -q`

**不要做**：不为通用繁体自动写 `zh-TW` 或 `zh-HK`（§15.1）；不改 `language_preset`。

### SIMP-31 用真 PySide6 offscreen 替换 fake_qt：**本轮不做**（D12）

下面的内容只作为备查保留。

**现状**
- 163 个测试用到 `tests/support/fake_qt.py`（1,045 行），另有约 550 行内联 fake。
- PySide6 不在 `pyproject.toml`、`uv.lock` 和 CI 里。
- 有 10 个历史复现脚本 import 了 fake_qt。

**以后如果做，分三个阶段**
1. 在 dev 依赖中加一个 `qt` 组（`PySide6-Essentials==6.11.2`），在 conftest 里加 qapp fixture。
2. 从小的测试文件开始逐个迁移。每迁完一个文件，就删掉对应的“只有 fake 会走”的守卫。
3. 最后删除 `fake_qt.py`。

风险：Linux CI 可能需要 `libegl1` 和 `libxkbcommon0`，这一点**没有在 CI 上验证过**。

### SIMP-32 拆分 `ui/preview_window.py`：**本轮不做**（D14）

`ui/preview_window.py` 共 4,533 行，约 45% 与预览无关：
- `:127-323` 是进度窗；
- `:345-637` 和 `:3679-4533` 是设置窗口，约 1,150 行；
- `:1113-1350` 是结果窗和错误窗。

可以机械地拆成 `ui/run_setup.py`、`ui/progress.py`、`ui/result_dialogs.py`。代价是测试中约 40 处 `"ui.preview_window.choose_scope"` 之类的 monkeypatch 字符串要跟着改。

SIMP-01、02、12、14 会先从这个文件里删掉约 650 行。A、B、C 三组都完成后，再单独评估是否拆分。

---

## 动态拼接的 i18n 键（删键前必须先核对）

| 文件 | 拼接模式 |
| --- | --- |
| `ui/history_window.py:47, 155` | `history.status.{status}` |
| `ui/rules_window.py:239` | `preview.category_value.{category}` |
| `ui/rules_window.py:243` | `rules.confidence.{conf}` |
| `ui/rules_window.py:2345` | `rules.conflict.{kind}` |
| `ui/rules_window.py:585, 690, 1483, 2145` | `rules.scope_{scope}`，经 CatalogView |
| `ui/rules_window.py:1449` | `rules.scope_{scope}_other` |
| `ui/rules_window.py:1949` | `rules.{stage}_stage_name` |
| `ui/i18n.py:93` | `rules.field.{field}` |
| `ui/i18n.py:124` | `config.{base}` |
| `ui/preview_window.py:219` | `progress.phase.{phase}` |
| `ui/preview_window.py:552` | `scope.run_summary_{name}` |
| `ui/preview_window.py:836` | `diagnostic.name.{code}` |
| `ui/preview_window.py:1419, 1849, 3268` | `preview.category_value.*` |
| `ui/preview_window.py:1420, 1856, 3270` | `preview.risk_value.*` |
| `ui/preview_window.py:1458, 1461` | `preview.group_{verb}` / `preview.{group}_{verb}` |
| `ui/preview_window.py:1535` | `preview.column.{name}` |
| `ui/preview_window.py:1868` | `preview.filter_status.{status}` |
| `ui/preview_window.py:3751, 3974` | `config.{config}` |
| `ui/preview_window.py:4130` | `language.name.{code}` |
| `ui/profile_window.py:89` | `scope.{value}` |
| `ui/profile_window.py:91, 94, 123` | `options.{value}` |
| `ui/profile_window.py:112` | `profile.element.{item}` |
| `ui/profile_window.py:119` | `profile.tofu_policy.{value}` |
| `ui/profile_window.py:449, 459` | `profile.{name}` / `options.{name}` |
| `ui/run_options.py` 多处 | `"settings." + name`、`"options." + name` |
| `ui/rules_window.py` 全文 | `CatalogView("rules")`，`self._labels["x"]` 对应 `rules.x` |
| `ui/profile_window.py` 全文 | `CatalogView("profile")` |
