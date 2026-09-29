# 01 逐条验收：2026-09-28 方案在 HEAD `6d74b25` 上的实际状态

先读 [README](README.md)。

**状态写法**
- `DONE`：达标。
- `PARTIAL`：部分达标。
- `NOT DONE`：未达标。
- `NOT VERIFIED`：本轮无法验证。
- `BROKEN TOOL`：计划指定的验证工具本身坏了。

**证据写法**
- 文件位置写作 `path:line`（HEAD 行号）。
- 命令输出引用原文。
- `E/` 指本目录的 `evidence/`。

**本轮跑过的命令**
- 各条“验证命令”里的 pytest 全部通过，数字见各节。
- 真实 Qt：`check_ui_acceptance.py --verify` 13/13 PASS；`check_rules_layout.py --verify` 在 768×614 和 960×640 下都通过。
- 2026-09-28 的复现脚本全部重跑，并与 `../2026-09-28/evidence/` 对照。

---

## UXS（交互）

### UXS-01 方向前置、按钮如实：DONE

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 三种语言下主按钮 = `config.continue` | DONE | 真实 Qt：Analyze and preview / 分析并预览 / 分析並預覽；`ui/preview_window.py:524`、`:598` |
| 标签页 0 就能改方向，摘要同步变化 | DONE | 方向行在摘要和标签页之间（`:516-521`）；改为 t2s 后，摘要首行由“简体中文 → 繁体中文”变为“繁体中文 → 简体中文” |
| 标题不再是“选择要转换的文件” | DONE | 标题为“OpenCCForSigil — 简繁转换”；`main.title` 用在 `:473`、`:3965`、`:4289` |
| `check_run_summary.py --verify` 三语通过 | DONE | acceptance 中 `ux03_summary_{en,zh-Hans,zh-Hant}` 都是 PASS |

pytest：`test_dialog_construction.py` 加 `test_scope_selection.py` 共 26 passed。新测试放在 `test_dialog_construction.py:158`，计划写的是 `test_scope_selection.py`。断言比计划更强，这个位置偏差可以接受。

### UXS-02 筛选框 Enter：行为 DONE，验证工具 BROKEN TOOL

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 选 0/1/2 个文件时，按 Return 或 Enter 窗口都不关闭 | DONE | 自写的真实 Qt 探针覆盖三种语言 × 两个键 × 0/1/2 个文件，全部 `dialog_visible=true`、`scope_accepted=false`；守卫在 `:4238-4262` |
| 焦点落在第一个可见行 | DONE | `current_row == first_visible_row` |
| 焦点在列表或按钮上时 Enter 仍开始分析 | DONE | `dialog_result=1` |
| 计划指定的验证命令 `probe_ux_simplicity.py` | BROKEN TOOL | HEAD 上报 `AttributeError: 'RuleManagerDialog' object has no attribute 'help_label'`（`../2026-09-28/scripts/ux/probe_ux_simplicity.py:236`），不生成 `ux_probe.json`。只改这一行入口后，所有 `enter_in_filter_closed_dialog` 都是 `false`。→ FIX-12 |

### UXS-03 “处理剩余 N 项”：PARTIAL

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 960×640 下可见；点一次、确认一次后“应用”可用 | DONE | 真实 Qt：按钮在窗口内；apply 由 false 变 true；3 个手动跳过保留 |
| “更多…”常显项不超过 4 个 | DONE | 常显 3 项：恢复此项 / 导出报告 / 批量处理…，另有语言组 2 项按上下文显示 |
| 没有一键路径把“已跳过”改成“接受” | DONE | 6 个旧按钮 `setVisible(False)`，不在菜单里，也没有快捷键；关闭“仅处理待决定项”后显示“确认并覆盖 3 项已有决定（共 38 项）” |
| 批量摘要中不出现“0 个”；两个下拉框有标签 | PARTIAL | 对话框内的摘要是干净的。但确认之后，状态栏追加“已批量处理 10 项修改，涉及 0 个组。”（`E/ux/fix11_zero_count_fragments.out`，来自 `:2401-2403`）；没有可处理项时，禁用的确认按钮显示“处理 0 项修改”（`:2365-2371`）。→ FIX-11 |
| 30 万条性能不退化 | DONE | `benchmark_preview_batch.py` median 0.382 s（2026-09-27 证据为 0.466 s） |

pytest：61 passed。

### UXS-04 术语统一：PARTIAL

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| `test_one_term_per_concept` 三语通过，同键测试仍通过 | DONE | `tests/unit/test_i18n.py:83`；19 passed |
| 真实 Qt 截图中，状态列、状态筛选、“下一项”用同一个词 | DONE | 重跑 `capture_uxs04_preview_terms.py`，结果 PASS |
| 第 8 步：各批新增的键符合术语表 | PARTIAL | 以下几处不符合，→ FIX-13：`rules.output` 仍是“沙箱输出 / 沙箱輸出 / Sandbox output”；zh-Hant 的 `result.row.written` 用“已寫入”，而 `result.row.unwritten` 用“未寫回”；`rules.version_v2` 的 zh-Hans 是“新版（…）”，zh-Hant 和 en 是“V2（…）”；en 的 `scope.checkpoint_close` 用小写 checkpoint |

### UXS-06 规则窗口首屏：DONE（验证工具之一 BROKEN TOOL）

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 默认尺寸和 960×640 下至少 5 行，新增按钮不用滚动就能看到 | DONE | `check_rules_layout.py --verify`：768×614 为 9 行，960×640 为 10 行，三种语言下 add 按钮都在视口内 |
| 首屏没有空分组框 | DONE | 只剩 `editor_box`（`ui/rules_window.py:733`） |
| 导入/导出/设置/说明从“更多…”一步打开 | DONE | 菜单 6 项，多出的“批量添加”“删除规则集”来自 RULE-06/12 |
| 测试页 Tab 顺序 | DONE | 测试范围 → 输入 → 测试 → 词典检查 → 输出 |
| 探针 `probe_rules_viewport.py` | BROKEN TOOL | `AttributeError … 'import_button'`（`../2026-09-28/scripts/ux/probe_rules_viewport.py:28`）。→ FIX-12 |

pytest：141 passed、1 skipped（`test_rules_window.py:450`，fake Qt 算不出布局尺寸）。

### UXS-07 范围 3 项：DONE，测试 PARTIAL

四个验收项都已 DONE：
- 可见单选项有 3 个；
- 选中 1 个文件时，可以直接再勾第二个；
- Spine/全部模式下列表只读，`itemChanged` 计数为 0；
- “返回设置”后显示为“选择文件”加 1 项。

`error.scope_exactly_one` 已从三份 JSON 删除。

测试缺计划要求的断言：“不做任何改动直接 `_accept()`，得到 `Scope.SELECTED` 且 `file_ids == (id,)`”。现有两个测试都是先勾第二个文件再接受。→ FIX-17

### UXS-08 结果框：PARTIAL

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 取消后的结果只有 1 行 | DONE | `test_cancelled_result_is_single_line` |
| 成功结果中没有数量为 0 的行 | NOT DONE | `E/ux/fix11_zero_count_fragments.out`：no-op 时出现“已写回：0 个文件（已接受 0 项变更，已跳过 0 项）”；成功时出现“已跳过 0 项”“其中没有建议变更：0 个”。代码在 `ui/preview_window.py:1141-1152`，`result.row.written` 总是加入。→ FIX-11 |
| `test_cancelling_preview_shows_cancelled_result_without_writing` 仍通过 | DONE | 50 passed |

### UXS-09 NAV：DONE

真实 Qt 结果：
- NAV 不在选择中时，选项 `visible=false`，偏好仍为 True；
- 勾上 NAV 后，选项重新可见；
- “查看修改”里显示“停用（本次不生效：当前范围未包含导航文档。）”。

### UXS-10 设置窗首屏：DONE

- 界面语言放在 corner widget 里（`:507-512`）。
- 按钮文案 `settings.profiles` 只被按钮使用，所以直接改了它的值。
- 在 unavailable 且无偏好时，Jieba 三个控件都隐藏；在 preferred 且 unavailable 时仍阻断，acceptance 中 3 个 Jieba 用例 PASS。

### UXS-11 表格：DONE

- `header_length 916 = viewport 916`，右侧空白为 0。
- 详情中的“规则：OpenCC — STPhrases”与筛选器一致。

---

## PERF（性能）

本机数字。测量期间机器负载在 7 到 125 之间，接近阈值的项都跑了多次，全部列出。

### PERF-01 前缀索引：DONE，测试偏弱

| 验收项 | 目标 | 实测 | 状态 |
| --- | --- | --- | --- |
| `benchmark_rules_book.py --modes current` 的 plan 中位数 | ≤ 修改前的 46% | HEAD 5.35–6.25 s；同机修改前（`e19c73c`）16.95 s，即 34–37% | DONE |
| digest | `8bab6319592d5abb` | 一致 | DONE |
| `literal_rule_scans` | ≤ 300,000 | 207,446 | DONE |
| `tools/benchmark_rules.py` | 两种书形 ≤ 0.8 s | 0.541 / 0.516 s | DONE |

**偏差 1：测试偏弱。** `tests/unit/test_rules_compiled.py:38-59` 的 `_random_rules` 生成形如 `词x12` 的源串，但文本字母表里没有 `x`，所以随机规则永远不会命中；pre/post 阶段也没有等价测试。这轮补跑的 `scripts/perf/fuzz_prefix_index.py` 覆盖 13,440 段文本，0 处不一致，因此实现本身没问题。→ FIX-17

**偏差 2：计划外加了 3 条快路径。**
- LRU 候选缓存（`core/converter.py:31, 168-174`，`rules/compiled.py:184-199`）；
- `include_single_char_rules` 相关字段；
- 无保护区间时的重复循环（`rules/matching.py:312-334`）。

拿掉这 3 条后，真实书的耗时在噪声范围内，tools 基准只慢 3–18%，仍 ≤ 0.8 s。LRU 容量 256，恰好对上 tools 基准“每 247 个节点重复一次”的规律，看起来像是按基准调出来的。→ SIMP-07

### PERF-02 诊断索引：DONE，计划外改动

| 验收项 | 目标 | 实测 | 状态 |
| --- | --- | --- | --- |
| `probe_diagnostic_records.py` 480 段落行 | ≤ 0.30 s，240→480 比值 ≤ 2.5 | 0.058 s，比值 1.87 | DONE |
| `benchmark_book_pipeline.py` 的 `diagnostic_records_seconds` | ≤ 0.15 s | 0.078–0.090 s（四种模式） | DONE |
| `benchmark_preview_ui.py` 的 `dialog_construct_seconds` | ≤ 0.75 s | 0.473 / 0.555 s | DONE |

**计划外改动：** 诊断标签页改成打开时才构建（`ui/preview_window.py:1769-1791, 2026-2035`），打开前标签只显示“计划诊断”，不带数量。立即构建只多 0.10 s，仍然达标。→ FIX-18

**执行记录与实测不符：** 执行记录说完整的 pipeline 基准“跑了 3 分钟以上仍未结束”。本机用默认参数在后台跑，**162 s 跑完**，最大 RSS 888 MiB，其中 63% 的时间花在 4 次 tracemalloc 下的 plan。→ FIX-12

### PERF-03 计划内存：DONE

| 验收项 | 目标 | 实测 | 状态 |
| --- | --- | --- | --- |
| `probe_plan_memory.py` 的 `retained_mib` | ≤ 170 | 167.3，digest `592c07451e572517` | DONE |
| `plan_seconds` 不慢于修改前 5% | — | 同机对比四种模式都没有变慢 | DONE |

测试 `test_change_models_use_slots` 没有断言 `replace()`。→ FIX-17

### PERF-04（并入 RULE-01）：DONE

`probe_regex_budget.py --regex-rules 128 --files 200,400` 两行都是 ok，400/200 耗时比为 1.28–1.87，要求 ≤ 2.2。

### PERF-05 状态筛选下的决定：PARTIAL

| 验收项 | 目标 | 实测 | 状态 |
| --- | --- | --- | --- |
| `accept_this_status_undecided` | ≤ 25 ms，decision() ≤ 2,000 次 | 12.1 / 11.6 ms，266 次 | DONE |
| `accept_file` | ≤ 25 ms，≤ 10,000 次 | 7.5 / 7.3 ms，6,330 次 | DONE |
| `accept_this_no_filter` | ≤ 8 ms | 5.3 / 6.7 ms | DONE |
| 修改方法第 3 步：可见行映射每次筛选变化只建一次 | — | 只有“单项且带 `preferred_row`”的路径能避开重建。**有分组的项**在状态筛选下每次单击都重建 `_visible_row_map`（`ui/preview_window.py:2513-2522`，调用处在 `:2626`，删行后在 `:2677-2678` 置空）：39.6 万行时分组接受要 54–61 ms；`E/perf/fix10_row_map_rebuilds.out` 显示 5 次单击重建 5 次，共遍历 99,980 项 | NOT DONE → FIX-10 |

增量计数的正确性：`E/perf/fuzz_incremental_counts.out` 为 `seeds=400 failures=0`。

### PERF-06 汉字计数、比较去重：PARTIAL

| 验收项 | 目标 | 实测 | 状态 |
| --- | --- | --- | --- |
| s2t current | ≤ 3.3 s | 3.469 / 3.375 / 3.255 s | PARTIAL（1/3 达标） |
| s2twp current | ≤ 4.05 s | 4.506 / 4.025 / 3.925 s | PARTIAL（2/3 达标） |
| s2t 比较调用次数 | ≤ 20,300 | 19,600 | DONE |
| digest | `06781c1d491c31f7` / `6284eef800e5b462` | 一致 | DONE |

同机、紧挨着跑的基线：`c14701f` 的 s2t 为 3.573 s，s2twp 为 4.488 s。HEAD 与之的比值是 0.911 / 0.875，提速达到计划预期。

执行记录把绝对阈值没达标归因于“macOS 27.0 对 26.5.2”，**这个解释不成立**：本机就是 macOS 26.5.2，与基线证据的平台相同。该探针计时前没有 `gc.collect()`，加上以后，s2t 为 3.09–3.10 s。→ FIX-12

### PERF-07 历史 index：DONE

| 验收项 | 目标 | 实测 | 状态 |
| --- | --- | --- | --- |
| 1,000 会话时 `record_session` | ≤ 1.6 s | 1.825 / 1.470 / 1.438 s（同机修改前 3.555 / 2.900 s） | DONE（低负载下） |
| `index_mib` | ≤ 75 | 70.8 | DONE |
| `load` | ≤ 0.95 s | 1.345 / 0.935 / 0.905 s | DONE（低负载下） |
| 文档注明紧凑 JSON | — | `docs/privacy.md:11-12` | DONE |

---

## RULE（规则）

### RULE-01 正则只计已采用的命中：DONE（D1 的边界另议）

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 脚本 (a) 输出 `regex_hits: 1`，(b)(c) 都能完成 | DONE | 重跑 `rule01_regex_hit_budget.py`：`(a)… budget.regex_hits: 1`、`(b) … OK`、`(c) … planned 60 files` |
| `probe_regex_budget.py` 两行都是 ok，比值 ≤ 2.2 | DONE | 见 PERF-04 |
| 单次搜索超过 50 ms 仍报错 | DONE，但没有自动化测试 | `E/rules/fix17_regex_timeout.out`：0.066 s 报 `timed out`。→ FIX-17 |
| 文档中的数字与常量一致 | DONE | `docs/rule-format.md:23-31`、`rule-guide.md` 三种语言；常量在 `rules/matching.py:18-21` |

**D1 的两个边界，需要决定：**
- `E/rules/d8_regex_run_cap.out`：自带“整理空格”模板处理一部 10 万段、每段以全角空格开头的长篇（约 4.6M 字）时，在第 100,001 段报 `exceeded 100000 hits`。
- `E/rules/d8_regex_tiny_fragments.out`：128 条正则、每片段 8 个字时，处理到第 26,540 个片段报 `exceeded its 3.42 second budget`，这时实际才跑了 4.7 s。

→ 已定：D8 删除整次限额，执行 SIMP-23

### RULE-02 去掉隐藏版本维度：DONE（D2 的副作用另议）

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 脚本输出 `頭髮(书)` | DONE | `final: ('頭髮(书)', …)` |
| RULE-02c 中出现 `SAME_SOURCE_DIFFERENT_TARGET` | DONE | `conflicts: ['SAME_SOURCE_DIFFERENT_TARGET']` |
| 只有 V1 时结果不变（300 组随机测试） | DONE | 通过 |
| “不要做”：迁移 V1、改 dedup key、改 schema | 未违反 | `rule_dedup_key` 在 `rules/importers.py:38-44`，没有改动 |

**D2 的副作用：** `E/rules/d9_mixed_version_flip.out`：
- 只有 V1 全局规则和 V1 方案规则时，全局规则胜出；
- 再加一条无关的更短 V2 规则“软→軟”，胜者翻转为方案规则，而冲突检测报告为空。

→ 已定：D9 只用 §11.2 的顺序，执行 SIMP-24

“其他观察”里建议顺手删除的 `precedence_key()` 没有删（`rules/precedence.py:57-63`，没有调用方）。→ SIMP-04

### RULE-03：DONE

脚本输出 `with long+short: ('太乾隆', …)`；原有的两个测试和 300 组随机测试都通过。

### RULE-04：DONE

- 说明句已写进 `docs/rules-and-profiles.md:60-63`、三种语言的 `rule-guide.md` 和 `rules.help`。
- 沙箱能显示被抢先的规则，开关 trace 时补丁完全相同。
- trace 的接入点在 `core/converter.py:167-229`，不是计划写的 `rules/engine.py`。沙箱实际走的就是这条路径，所以没有影响。

### RULE-05 跨规则集冲突：PARTIAL，另有缺陷

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 两个规则集在窗口里都能看到冲突，保存被禁用 | PARTIAL | 在带正确入口参数的临时脚本中成立。但计划附带的复现脚本在 HEAD 上输出 `conflicts …: []`、`save enabled …: True`，原因是 RULE-11 改了入口，脚本没跟着改。→ FIX-12 |
| 导入 B 时，导入预览显示冲突 | DONE | 临时脚本验证 |
| **分析之前就能得到本地化的冲突说明** | **NOT DONE** | `E/rules/fix01_analyze_conflict_qt.out`：点击后控制台出现 traceback `app.errors.RuleConflictError: blocking rule conflicts: a1 (A), b1 (B)`，随后 `accepted = False`、`dialog visible = True`、`message boxes = []`，用户什么也看不到。→ FIX-01 |
| 不同方向、书、方案互不阻断 | DONE | `test_freeze_rules_ignores_rules_owned_by_another_book_or_profile` |

**另外两个缺陷：**
- 切到一个与冲突无关的规则集后，“保存”又可用（`E/rules/fix04_switch_ruleset_reenables_save.out`）。→ FIX-04
- 重命名后冲突消失。→ FIX-03

### RULE-06 两列表格与批量添加：PARTIAL，另有缺陷

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 两列、三列（无方向列）、中文表头都能导入 | DONE | `rule06_import_formats.py` 重跑输出与计划一致 |
| 旧的 4 列格式和往返不变 | DONE | `probe_edge_cases`：`TSV roundtrip identity: True` |
| 批量添加经过导入预览；取消时列表不变 | DONE | 临时脚本输出 `True` |
| 三种语言的 `rule-guide.md` 加入两列示例 | PARTIAL | 只在“批量粘贴”一节有示例；文件导入的 2/3 列格式和中文表头，在 guide 和 `docs/rule-format.md` 里都没写。→ FIX-07 |

**缺陷：**
- **表头误判：** 首字段是表头词（例如“备注”“目标”“原文”“source”）的数据行会被静默丢弃（`E/rules/fix07_fix08_import_edges.out` 前 5 行，以及 `E/rules/fix07_bulk_add_header.out`）。
- **相对 0.2.8 的回归：** 3 列、方向栏为空的行现在报 `source must not be empty`，以前使用对话框选的方向。
- 以上两点 → FIX-07。
- **批量添加生成通配规则：** 编辑区方向是 `*` 时，批量添加会生成一批 `*` 规则（`E/rules/fix06_bulk_add_wildcard.out`）。→ FIX-06

### RULE-07 TSV 引号：DONE，有回归

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 两个示例都按行得到结果 | DONE | `'"引号"'`；不成对引号的例子得到 3 条 |
| 导出再导入与原来一致 | PARTIAL | 值里含 U+2028、U+2029 或 NEL 时，往返后 target 从“軟␤體”被截成“軟”，而且静默加入（`E/rules/fix07_fix08_import_edges.out` 的 RULE-07 段）。0.2.8 的 csv 读取不会在这些字符处断行，所以这是回归。→ FIX-08 |
| CSV 行为不变 | DONE | 仍用 `csv.reader`/`writer` |

### RULE-08 物理行号：DONE

- TSV/CSV/TXT 报告物理行号，JSON 报告记录序号；CRLF、BOM 和 CSV 多行记录都正确。
- 1 列行的消息是 “rule 2: expected …”，这里的 2 是行号，但写法容易误读成规则序号。→ FIX-08 顺带修

### RULE-09 JSON 导入：DONE，同类问题残留

- 三个验收项都已 DONE：全局规则往返后 canonical 相等（`canonical equal: True diff: {}`），属于其他书或方案的规则有提示，默认不改写归属。
- **同类问题：** TSV/CSV/TXT 导入无论选什么范围，都同时写入 `profile_id` 和 `book_fingerprint`（`E/rules/fix15_delimited_owner.out` 的 6 行都是 `profile_id='CURRENT-PROFILE' book_fingerprint='CURRENT-BOOK'`）。→ FIX-15

### RULE-10 新规则默认当前方向：PARTIAL，另有缺陷

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 脚本第一行的预选方向为 `s2t` | DONE | 真实 Qt 下 `preselected: s2t` |
| 已存在的 `*` 规则不被改写 | DONE | 临时脚本 `unchanged: True` |
| 三种语言的文案齐全 | DONE | — |

**缺陷（违反 D7“新规则默认使用当前方向”）：**
- `E/rules/fix06_default_direction_persist.out`：在 s2t 会话里加规则并保存后，`default.json` 的 `default_direction` 变成 `s2t`；下一次 t2s 会话打开，仍预选 `s2t`，新规则 `applies to this t2s run: False`。原因是 `app/settings.py:298-299, 303-305` 把会话方向写进了占位规则集。
- `E/rules/fix06_wildcard_inherit.out`：选中一条 `*` 规则再删除后，下一条新规则静默继承 `*`。
- 以上两点 → FIX-06

### RULE-11 “本次使用”与“全局启用”分开：PARTIAL，另有缺陷

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 只是浏览另一个规则集再保存，本次引用不变 | DONE | 用真实窗口复验：`after : ('default',) \| questions: []` |
| 一次保存最多 1 个模态框 | DONE | `E/rules/fix03_fix05_rename_new_confirm.out` E 段：保存时 1 个 |
| 全局开关文案不含“本次”；有引用时取消勾选需要确认 | DONE | — |
| R-01 和重命名的现有用例通过 | DONE | 但新出现的重命名缺陷没有用例覆盖 |
| “不要做”：未经确认不写入已保存的方案 | **违反** | `fix03_fix05_rename_new_confirm.out` D 段：只问了“把 N 加入方案 Saved？”，结果 `saved profile now: ('default', 'N')`，用户从没被问过的“移除 A”也写进了方案。→ FIX-05 |

**缺陷：重命名后本次引用脱节。**
- `E/rules/fix02_fix03_ruleset_rename_delete.out` A 段：改名后窗口显示“不用于本次转换”；用户勾上再取消，结果仍是 `('default', 'B')`，也就是没法把它移出本次。
- 同文件 A2 段：改名后冲突消失、保存可用，分析时抛 `RuleConflictError`。
- `fix03_fix05_rename_new_confirm.out` A3 段：改名后再新建一个同名规则集，新集显示“已勾选”，实际并不在本次。
- 以上三点 → FIX-03

另外，`../2026-09-28/scripts/rules/rule11_ruleset_enabled_is_global.py` 的第二段在 `b34d02d` 里被改成直接返回 `run_ruleset_ids=()` 的桩，不再经过真实窗口，永远不会失败。→ FIX-12

### RULE-12 删除规则集：PARTIAL，另有缺陷（丢数据）

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 删除后没有悬空的引用 | PARTIAL | 方案文件中已清干净，但偏好 `run_options.ruleset_ids` 里还留着，下次启动提示 `missing-ruleset notice = ('X',)`（`E/rules/fix14_deleted_ruleset_prefs.out`）。→ FIX-14 |
| `default` 不能删除，并说明原因 | PARTIAL | 删除项已禁用，也设了 tooltip，但菜单没有开启 `toolTipsVisible`，用户看不到说明（`E/rules/fix14_menu_tooltip_qt.out`：`menu.toolTipsVisible(): False`）。→ FIX-14 |
| 取消窗口时不删除任何文件 | DONE | `test_cancel_after_delete_keeps_ruleset_file` |

**缺陷（P1，丢数据）：** `E/rules/fix02_fix03_ruleset_rename_delete.out`
- B 段：删除 X 后新建 X、加规则、保存，结果 `X.json exists after save: False`。
- C 段：删除 X 后把 Y 改名为 X，保存后 `files: []`，Y 的规则丢失。

→ FIX-02

### RULE-13：DONE

脚本输出 `inspector opened for: 乙方 (expected 乙方)`，过滤和未过滤两种情况都有测试覆盖。

### RULE-14 其他书/方案的归属：DONE，有小问题

- 三个验收项都已 DONE：表格显示“其他书籍”；只有点击按钮才改绑；R-02 的回归测试通过。
- **小问题 1：** 本次没有引用该规则集时，点击“有 1 条规则属于其他书籍…”会切到“本次不生效”，列出全部 10 条规则（`E/rules/fix16_foreign_owner_banner.out`）。→ 已定删除这个提示，执行 SIMP-22（FIX-16 不做）
- **小问题 2：** 窗口内改绑时没有清掉另一个归属字段：`book='CUR' profile='OLD-PROFILE'`；导入时改绑则会清掉（`E/rules/fix15_rebind_other_owner.out`）。→ FIX-15

### RULE-15 零宽匹配：DONE，诊断不合格

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 不再因零长度匹配中止分析 | DONE | 脚本末行输出 `他说「」然后` |
| 时间和命中预算仍有效 | DONE | 每次搜索都经过 `timeout_for`/`note_regex_time` |
| 诊断和日志不含原文 | DONE | 消息为 `rule z: skipped 1 zero-width match(es)` |
| 修改方法第 2 步：分析结束后，每条规则一条诊断 | NOT DONE | `E/rules/fix09_zero_width_diagnostics.out`：6 个文件、每个 10 段，产生 60 条诊断；预览中是 6 条记录，名称显示“其他诊断：REGEX_ZERO_WIDTH_SKIPPED”，描述是“…：1 处”，看不到规则 ID 和实际次数 10。→ FIX-09 |

### 其他观察（03-rules.md 末尾）：NOT DONE

| 项 | 状态 | 去向 |
| --- | --- | --- |
| `rule-guide.md` 补充实体说明 | NOT DONE | FIX-18 |
| 删除 `precedence_key()` | NOT DONE | SIMP-04 |
| TSV 导出按列表顺序 | NOT DONE（仍按 ID 排序，`rules/exporters.py:147`） | FIX-18 |

---

## 对 `../2026-09-28/04-implementation-results.md` 的更正

执行 FIX-12 时，按 README 全局约束 10，把下列内容**追加**到那份文件末尾，不改原有的行：

1. 批次 6（PERF-02）：“完整的 `benchmark_book_pipeline.py` 跑不完”改为：本机默认参数 162 s 跑完，`diagnostic_records_seconds` 为 0.078–0.090 s（要求 ≤ 0.15），达标。
2. 批次 12（PERF-06）：删掉“macOS 27.0 对 26.5.2”的解释。改为记录同机配对数据：HEAD 与 `c14701f` 的比值为 s2t 0.911、s2twp 0.875；绝对阈值只在低负载时满足。
3. 批次 5、10（RULE-05、RULE-11）：“Complete”改为“有缺陷，见 2026-09-29 FIX-01、FIX-03、FIX-04、FIX-05”。
4. 批次 10（RULE-12）：“Complete”改为“有缺陷，见 2026-09-29 FIX-02、FIX-14”。
5. 批次 9（RULE-06、RULE-07）：“Complete”改为“有回归，见 2026-09-29 FIX-07、FIX-08”。
6. 批次 13（UXS-08）：“zero-count rows are omitted”改为“只处理了未写回和全部跳过两行，见 2026-09-29 FIX-11”。
