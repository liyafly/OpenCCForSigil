# 01 验收：2026-09-29 方案逐条核对

范围：`6d74b25..3107f27`，共 67 个提交。规格见 [2026-09-29 README](../2026-09-29/README.md)、[02-remaining-fixes](../2026-09-29/02-remaining-fixes.md)、[03-simplification](../2026-09-29/03-simplification.md)；执行记录见 [04-implementation-results](../2026-09-29/04-implementation-results.md)。

**核查方法**
- 对照规格的每个步骤、验收勾选项和“不要做”清单，读 diff 和测试。
- 每条列出的“修复前失败的测试”，都拷到父提交上重跑，确认确实失败。
- 改过的复现脚本放到改动前的代码上跑，确认复现能力还在。
- HEAD 上跑了规格给的全部聚焦测试集、真实 Qt 验收，以及 2026-09-27 至 2026-09-29 的探针。

状态说明：
- **符合**：全部验收项达标。
- **基本符合**：达标，但有记录、测试强度或文案上的小尾巴。
- **未完成**：有规格步骤没做。
- **有缺陷**：落地的代码带进了 bug，包括规格本身写错、执行模型照做的情况。

## FIX 条目

| 条目 | 提交 | 状态 | 问题 | 去向 |
| --- | --- | --- | --- | --- |
| FIX-01 分析时的跨集冲突 | `e7dec01` | 符合 | 3 个新测试在父提交上都失败；fake Qt 和真实 Qt 复现都没有 traceback，都会弹出 `error_details` | — |
| FIX-02 删除后复用 ID 丢数据 | `df876bf` | 符合 | 两个新测试在父提交上都失败；复现脚本 C 段为 `files: ['Y.json']` | — |
| FIX-03 重命名后本次引用脱节 | `c119373` | 符合 | 改名后 `checked = True`，冲突仍在，“保存”不可用 | — |
| FIX-04 切到无关集后“保存”可用 | `54a0743` | 符合 | 仅记录：本次引用的某个集如果自身有冲突，文案会是“规则集 B 之间冲突”，只有一个集时读起来不通 | 仅记录 |
| FIX-05 确认“加入方案”不写入移除 | `76ad3c3` | 符合 | 测试偏弱：没有真正模拟“在本次会话中移除 A”，但确实能卡住原缺陷 | 仅记录 |
| FIX-06 新规则方向 | `33f6305` | **有缺陷** | 规格第 3 步要求 `_update_selected()` 末尾重置方向框，但更新后编辑区仍绑定同一条规则。于是一条已有的 `*` 规则连续更新两次，会被改成 s2t。这违反本条的验收项“已有的 `*` 规则不被改写” | **FU-01** |
| FIX-07 表头与 3 列空方向 | `3a268c1` | 符合 | 改了两条已有测试的断言（改法合理），04 没说明；zh-Hant 指南写“首列有標題”，与 i18n 的“表頭”不一致 | FU-08、FU-09 |
| FIX-08 Unicode 行分隔符 | `9465893` | 基本符合 | 执行模型声明的两处调整（form-feed 改为放在备注里测、roundtrip 期望 1 条 info）都合理。但新增的 `_OPENCC_CANDIDATE_SEPARATOR = [ \t]+` 还带来一个行为变化：OpenCC TXT 里的 U+3000 和 NBSP 不再作为候选分隔符，现在并入 target。04 和发布说明都没写 | FU-05、FU-09 |
| FIX-09 零宽诊断按规则汇总 | `1acfbdc` | **未完成** | 规格第 2 步“数字字符引用分支也要累加”没做。`core/planner.py:131-140` 新建 `ConvertResult` 时没有带上 `zero_width_skips`，所以 `&#x4E2D;` 里的零宽跳过没有诊断；修改前是有的 | **FU-03** |
| FIX-10 分组项在状态筛选下 O(N) | `95836e6` | 符合 | 单元测试在父提交上失败（访问 20,000 行，上限 1,000）。仅记录：规格指定的复现指标“full refreshes”在基线上也是 0，不能证明修复有效，真正起防护作用的是单元测试。之后 `a1cba9b` 弄坏了基准脚本 | FU-06 |
| FIX-11 零计数文案 | `9a0e677` | 符合 | 3 种语言 × 3 个场景都是 `zero lines: none` | — |
| FIX-12 验证工具与记录更正 | `457e75e` | 提交时符合 | 4 个探针只改了入口，2026-09-28 的记录只追加。之后 `1bc5505`（SIMP-28）又把 `probe_ux_simplicity.py` 弄坏了，UXS-02 的验证命令在 HEAD 上跑不起来 | FU-06 |
| FIX-13 一个概念一种叫法 | `0c09a2f` | 符合 | 语言目录里已经没有“沙箱/sandbox”。仅记录：用户能看到的 `resources/rule-guide.md` 里还有 9 处，不在本条范围内 | FU-08 |
| FIX-14 菜单 tooltip、悬空引用 | `20bdfb1` | 符合 | 复现脚本改用真实的 `UserDataStore`。改动是必要的，原脚本观察不到修复，但提交说明没写。之后 `b87d679` 把 tooltip 脚本的检查对象换掉了 | FU-07、FU-09 |
| FIX-15 导入只写选中的归属 | `43284ef` | 符合 | `rule_dedup_key` 没动 | — |
| FIX-16 | — | 按决定不做 | 提示本身已被 SIMP-22 删除 | — |
| FIX-17 测试补强 | `ff64375`、`fdd2554` | 符合 | oracle 修正符合 A-08，没有降低断言，详见 README。但之后 `9ce645a`（SIMP-03）把 300 组随机测试的参照换成了生产代码的 `source_matches`，两组随机测试都变成了“编译路径对全量扫描”，独立 oracle 只剩 1 个固定用例 | FU-07 |
| FIX-18.1 实体说明 | `dfcc653` | 符合 | — | — |
| FIX-18.2 导出保序 | `c6d9f9d` | 符合 | 测试在父提交上失败；提交说明缺“修复前失败的测试” | FU-09 |
| FIX-18.3 诊断数量 | `8ddfddc` | 符合 | 面板仍是打开时才构建；5,711 条诊断计数耗时 1.9 ms。提交说明缺“修复前失败的测试”。仅记录：去重键写了两份 | FU-09 |

## SIMP 条目

| 条目 | 提交 | 状态 | 问题 | 去向 |
| --- | --- | --- | --- | --- |
| SIMP-01 独立转换配置流程 | `b405fc9` | 基本符合 | 顺手删了 `single_radio`（属于 SIMP-26）和 hasattr 守卫（属于 SIMP-09），导致 `probe_ux_simplicity.py` 从这里一直坏到 `5b3b52b`。`test_run_options.py` 删掉了与独立窗口无关的布局顺序断言 | 仅记录 |
| SIMP-02 隐藏的批量控件 | `c20bc9d` | 基本符合 | 夹带了批量应用改走增量计数（400 例随机测试一致），但带来性能回归，CI 超过 1.0 s，靠 `746771f`、`6ff11aa` 修好。`check_preview_layout.py:129-131` 把一条否定断言换成了上一行的重复；`test_preview_group_scaling.py` 丢了对全局 `_entries` 访问次数的断言 | FU-07 |
| SIMP-03 旧规则引擎 | `9ce645a` | 基本符合 | 7 个探针只改了入口。300 组随机测试的独立参照被换掉（见 FIX-17）；`test_non_string_backend_output_is_rejected` 去掉了 `match=` | FU-07；D21 |
| SIMP-04 死模块、别名、i18n 键 | `7fedeac` | 基本符合 | 少做一项：`tools/validate_artifact.py` 没有把 `result.status.cancelled_unchanged` 列为必需 | FU-08 |
| SIMP-05 规则窗口旧结果路径 | `c42f16b` | **有缺陷** | 规格认为“删空后自动重建 default”走不到，因为 default 删不掉；但 `_rename_ruleset` 允许重命名 default。先把 default 改名为 X 再删 X，`rules_window.py:1080` 的 `next(iter({}))` 会抛出 `StopIteration` | **FU-02** |
| SIMP-06 默认值单一来源 | `d15c5d4` | 符合 | — | — |
| SIMP-07 前缀索引快路径 | `a1499b3` | 偏离原意 | 规定要删的都删了，但新增的 `LiteralPrefixIndex.single_char_buckets` 换了个形式把单字快路径加了回来，`source_matches` 的循环也被重写。正确性：13,440 段模糊测试 0 处不一致，书籍 digest 不变 | D18 |
| SIMP-08 缺 BookContainer API 时报错 | `4900399` | 符合 | 残留：`docs/testing.md:12` 仍写“preflight-only run = success” | FU-08 |
| SIMP-09 UI 兼容分支 | `41da352` | 符合 | 仅记录：同类的 `getattr(Qt,"UserRole",32)` 还有 4 处（`history_window.py:207,331`、`profile_window.py:279,335`），不在规格范围内 | 仅记录 |
| SIMP-10 V2 字面规则导出 TXT | `640895d` | 符合 | 仅记录：docstring 仍写 “V1” | 仅记录 |
| SIMP-11 规则模板 | `b235b05` | 符合 | D15 改写合规，提交说明也写了 | — |
| SIMP-12 Checkpoint 横幅 | `493cbad` | 符合 | 恢复提示和 Apply 前的 Checkpoint 确认都保留了 | — |
| SIMP-13 两个诊断开关 | `501192a` | 基本符合 | 旧方案 extras 里的 `diagnose_mixed`、`detailed_classification` 会一直保留，另存时也会写回。运行时忽略这两个字段，比较时也会去掉，用户看不到 | 仅记录 |
| SIMP-14 语言标签组按钮 | `a1cba9b` | 符合 | 产品部分符合。弄坏了 `probe_followup.py:87` 和 `benchmark_preview_ui.py:163,188` | FU-06 |
| SIMP-15 导入 strict 模式 | `d9e0705` | 符合 | 产品部分符合。删掉 `strict=` 后，有 5 个旧脚本报 `TypeError` | FU-06 |
| SIMP-16 方案兼容垫片 | `4a2b390` | 符合 | 2026-09-23 的 `s4_future_schema.py` 用到的 `recovery_notice` 已被删除 | D20 |
| SIMP-17 | — | 按决定不做 | `FORCE_PIVOT_CHAINS` 没动 | — |
| SIMP-18 5 个小入口 | `3eeb0e5` | 符合 | 5 项都做了。`check_run_summary.py:361-362` 的 D15 改写合规，但提交说明没写。本提交引入了 Ruff F401，直到 `2d233a5` 才修好 | FU-09 |
| SIMP-19 摘要里不生效的字段 | `22357fe` | 符合 | 仅记录：`_profile_summary_value` 里的 `numeric_cjk_char_refs` 分支成了死代码 | 仅记录 |
| SIMP-20 历史状态筛选 | `f380381` | 符合 | D15 改写合规，但提交说明没写 | FU-09 |
| SIMP-21 词典检查并入规则测试 | `e79ea24` | **有缺陷** | 规则测试输出里“最终结果”出现两次（`最终结果: X` 和 `最终结果：X`）。指南 `rule-guide.md:70,139,208` 和 `docs/rules-and-profiles.md:66` 仍在描述已删除的“只读词典检查器” | **FU-04**、FU-08 |
| SIMP-22 其他书/方案提示 | `d100941` | 符合 | 标注和改绑按钮都保留了 | — |
| SIMP-23 删除整次正则限额 | `7d97739` | 基本符合 | 3 个限额删干净了，保留项都在。第 4 步“正则只编译一次”没做；列出的测试 `test_converter_does_not_share_applied_output_limits_between_fragments` 不存在；`test_overlapping_regex_candidates_do_not_count_as_hits` 直接删掉了计数断言，没有按规格改成“每片段计 1” | D17、FU-07、FU-09 |
| SIMP-24 统一范围优先级 | `5aaa7e0` | 符合 | `d9_mixed_version_flip.py` 两行都是 `v1-global`；deviations 已记录 | — |
| SIMP-25 删规则集设置对话框 | `b87d679` | 基本符合 | 产品改动完全按规格。`fix14_menu_tooltip_qt.py` 被改成检查已停用的集 A，不再检查“默认规则集不能删除”的 tooltip，这不属于 D15 允许的两种改法 | FU-07 |
| SIMP-26 `Scope.SINGLE` | `5b3b52b` | 符合 | 旧方案里的 `"single"` 仍能加载 | — |
| SIMP-27 `TextTarget.context` | `ea21a75` | 符合 | — | — |
| SIMP-28 NAV 跟随文件集合 | `1bc5505` | 基本符合 | 产品步骤都做了。弄坏了 `probe_ux_simplicity.py:179`。`check_run_summary.py` 删掉了“未生效原因的 tooltip 等于全文”两条检查，没有迁到别处。新增断言 `"profile.convert_nav" not in summary_text` 永远成立，而且这个测试修复前就能通过，却被列为“修复前失败” | FU-06、FU-07、FU-09 |
| SIMP-29 语言标记两档 | `9bfff12` | 符合 | 行为变化（通用繁体 + Legacy + 未选地区时阻止分析）已记入 deviations，但发布说明写成了“保留旧行为” | FU-05 |
| SIMP-30 导入小变体 | `68b2ab1` | 符合 | 旧 JSON 里的 `pattern`/`replacement` 别名现在会报 “unknown rule fields”，这是规格批准的，但发布说明没写 | FU-05 |
| SIMP-31、SIMP-32 | — | 按决定不做 | 没有加 PySide6 依赖；`preview_window.py` 从 4,533 行减到 3,947 行，全是删减 | — |

## 计划外的提交

| 提交 | 内容 | 评估 | 去向 |
| --- | --- | --- | --- |
| `746771f` perf: accelerate all-scope preview batch planning | 新增 `PreviewSession.decision_items()`，全部范围、没有原子组时跳过逐条 `decision()` | 不在批准清单里（违反约束 12）。起因是 SIMP-02 导致 CI 超时。3000 例随机对照一致；失败测试断言的是实现细节；覆盖、跳过和多文件计数没有测试 | D19、FU-09 |
| `6ff11aa` perf: apply preview batch decisions in bulk | 按 session 批量恢复决定，按文件更新计数 | 用户可见行为不变；150 个种子对照一致；阈值没改；CI 通过 | D19 |
| `3107f27` release: prepare v0.2.11 | 改版本号、写发布说明、打标签、发布 | 2026-09-28 约束 6 禁止执行模型这样做。发布说明漏写了用户能看到的删除和行为变化 | FU-05；发布授权待用户确认（README U1） |

## 自报与实际不符（写进 FU-09 的更正）

1. **SIMP-18：** 列出的测试 `test_jieba_failure_reason_is_available_in_status_tooltip` 不存在。实际对应的两个测试在父提交上确实失败。
2. **SIMP-23：** 列出的 `test_converter_does_not_share_applied_output_limits_between_fragments` 不存在，实际是 `test_selected_output_has_no_analysis_wide_limit`；第 4 步没做，也没有报告。
3. **SIMP-28：** `test_profile_summary_uses_localized_direction_and_option_labels` 在修复前的代码上是通过的，不是“修复前失败”。
4. **FIX-09：** 自报“完成”，实际漏了数字字符引用分支。
5. **FIX-08：** 没写 U+3000 和 NBSP 的行为变化。
6. **FIX-07：** 没写对两条已有测试断言的调整。
7. **FIX-14：** 没写复现脚本被改写。
8. **FIX-18.2、18.3 与 `fdd2554`：** 提交说明缺“修复前失败的测试”。
9. **Phase 7 记录**写 SIMP-02 “没有减弱任何断言”，与事实不符；**Phase 8 记录**写 “unrelated batch checks remain”，也与事实不符（`865c29f` 删掉了混合对话框里“按文件批量接受本文件规则组”的检查）。
10. **Phase 9 gate** 没有重跑 `probe_ux_simplicity.py`，所以没发现它已经坏了；`benchmark_preview_ui.py` 也坏了，没有提到。
11. **`746771f`** 在 04 里只作为某次 CI 重跑的 SHA 出现，没有单独记录。

## 过程问题（写进 FU-09 的更正）

- **Ruff：** `3eeb0e5` 到 `d100941` 这 5 个提交都报 F401，直到 `2d233a5` 才修好。
- **真实 Qt 验收：**
  - `check_run_summary.py` 在 SIMP-02 到 SIMP-08 期间跑不通：在 `d15c5d4` 上挂住超过 10 分钟。
  - ux04 从 `a1cba9b` 起、ux02 从 `501192a`/`3eeb0e5` 起一直失败，到 `865c29f` 才修好。
- 这违反了“每条做完都跑通用验证，没过不进下一条”，04 没有交代。

## 只记录、不改的项

- FIX-04 单集冲突文案读起来不通；FIX-05 测试偏弱；FIX-10 复现指标在基线上也是 0；FIX-18.3 去重键写了两份。
- SIMP-01 删掉了 `test_run_options.py` 的布局顺序断言，与之相关的独立窗口已经不存在。
- SIMP-07 新增的快路径结构（D18）。
- SIMP-09 剩下 4 处 `UserRole` 魔法数字；SIMP-10 的 docstring；SIMP-13 旧 extras 残留；SIMP-19 的死分支。
- SIMP-23 第 4 步（D17）；SIMP-03 删掉的非字符串检查（D21）。
- 2026-09-23 round2 的 6 个脚本退役（D20）。
- `check_profile_layout.py:227-231` 的 `comparison_has_panel_option` 断言：Translator 遇到缺失的键会返回键名本身，所以这条断言永远成立。它是按 D15 改成“不存在”的，形式上合规。
