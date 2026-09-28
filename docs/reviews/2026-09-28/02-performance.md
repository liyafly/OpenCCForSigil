# 02 性能（PERF）

基线：`c14701f`。先读 [README](README.md) 的全局约束。

以下是已经完成的优化，本文不再重复提出：组索引、紧凑的全量撤销、虚拟表模型、worker 线程分析、staging 线性拼接、CDATA bisect、每次 plan 只建一次 overlay。

## 0. 环境与基线

**环境**
- 机器：Apple M4 Pro，macOS arm64，CPython 3.14.7，PySide6 6.11.2（offscreen）。
- 后端：仓库自带的官方 OpenCC 1.4.2。
- 合成书：由 `scripts/perf/synthetic_book.py` 生成，固定随机种子。共 200 个 XHTML，2,130,070 字符，5.5 MiB。s2t 下有 33,200 个 target、396,091 处变更、5,711 条诊断。
- 计时：3 次取中位数；真实 Qt 的单击操作取 5 到 20 次的中位数。
- 数字只对这台机器有效。验收时请在同一台机器上先跑修改前的基线，再跑修改后的结果，比较两者的比例。

**基线数据**

| 项目 | 基线 |
| --- | --- |
| `plan()`（默认开启诊断和分类） | 3.31 s（s2twp 4.26 s） |
| 计划常驻内存 | **240.6 MiB**（书本身 5.5 MiB） |
| `_diagnostic_records`（主线程） | **1.18 s** |
| 真实 Qt：构造 `_PreviewDialog` | 1.76 s |
| 真实 Qt：状态筛选为“未处理”时接受当前项 | **141 ms**，每次单击调用 decision() 约 396,447 次 |
| 真实 Qt：接受本文件 | 114 ms |
| 2,000 条字面规则时的 `plan()` | **15.2 s**（无规则时 3.3 s） |
| 128 条正则规则、400 个文件 | **分析失败**，超过 3 秒运行预算 |
| 已有 1,000 个会话时，一次 `record_session` | 2.85 s（index 110 MiB） |

原始数据：`evidence/perf/pipeline.json`、`evidence/perf/preview_ui.json`。

**运行说明**
- 所有脚本都在仓库根目录运行，脚本放在 `docs/reviews/2026-09-28/scripts/perf/`。
- 下文用 `P=docs/reviews/2026-09-28/scripts/perf` 作为路径简写。
- 有些脚本带“原型模式”（例如 `benchmark_rules_book.py` 的 `indexed`），它是对 `c14701f` 源码的 monkeypatch。修复落地后只能用 `current` 模式或默认模式，并对照文中记录的 digest。

---

## PERF-01（P1）规则分析：每个 target 都用 Python 逐条扫描全部规则（O(R)）

> 已合并 RULE-16。**依赖**：RULE-01 先完成，两项都会改 `rules/matching.py`。

**位置**
- `plugin/OpenCCForSigil/core/converter.py:128`，`OfficialBackendConverter._convert_rules`：
  - L150：每次都执行 `guarded_rules = any(... for rule in overlay.rules)`；
  - L158：`unlocked = replace(request, ...)`；
  - L161：`dict(overlay.regex_patterns)`；
  - L162–163：每次重新构造 pre/post 规则的 tuple。
- `rules/compiled.py:96`，`lock_spans_compiled`：
  - L101：每次调用都重新构造 `source_rules`；
  - L104：`dict(overlay.regex_patterns)`；
  - L87–91：构建了 `CompiledOverlay.index`，但生产代码从不读取它（只有 `tests/unit/test_rules_compiled.py:138` 读取）。
- `rules/matching.py:115`，`collect_matches`：L124–135 对**每一条**字面规则都执行 `while ... text.find`。

**现状**
- 2,000 条字面规则、200 个文件时，`plan` 中位数为 **15.22 s**；不加规则时为 3.31 s。
- 字面规则扫描次数为 66,400,000，正好等于 33,200 个 target × 2,000 条规则。
- 规则数量和单文本扫描时间的关系（`scripts/rules/rule16_literal_scan_cost.py`，300k 字、3,000 段）：

  | 规则数 | 耗时 |
  | --- | --- |
  | 100 | 0.04 s |
  | 1,000 | 0.40 s |
  | 5,000 | 1.98 s |

- 原型（`benchmark_rules_book.py --modes indexed`）的结果：
  - `plan` 为 **6.15 s**，扫描次数 207,446；
  - digest 保持 `8bab6319592d5abb`；
  - `tools/benchmark_rules.py` 从 1.37 s / 1.34 s 降到 0.70 s / 0.68 s。

**修改方法**
1. 在 `CompiledOverlay.build()` 中一次性预计算以下字段（现有 `index` 字段保留）：
   - `source_rules`、`pre_rules`、`post_rules`：均为 tuple，保持 `ordered_rules` 的顺序；
   - `guarded: bool`；
   - 每个阶段的 `rule_order: Mapping[str, int]`（rule.id → 在该阶段中的序号）；
   - 每个阶段的字面规则前缀索引 `*_literal_index: Mapping[str, tuple[Rule, ...]]`，键为 `rule.source[:2]`；单字符规则的键就是这个字符本身。
2. 在 `rules/matching.py` 新增：
   ```python
   def literal_candidates(text, index, order):
       keys = set(text)
       keys.update(text[i:i + 2] for i in range(len(text) - 1))
       found = [rule for key in keys.intersection(index) for rule in index[key]]
       found.sort(key=lambda rule: order[rule.id])
       return tuple(found)
   ```
   调用方把返回结果和该阶段的**全部**正则规则合并，再按 `order` 排序后传给 `collect_matches`。
3. `lock_spans_compiled`：
   - 用 `overlay.source_rules` 加上字面规则候选，调用未修改的 `source_matches`；
   - 直接传 `overlay.regex_patterns`，因为 `MappingProxyType` 支持 `.get`，不需要复制成 dict。
4. `_convert_rules`：
   - 改为读取 `overlay.guarded`、`overlay.pre_rules`、`overlay.post_rules`；
   - `replace_stage` 增加可选参数 `literal_index=None, order=None`，提供时同样先过滤候选。沙箱等旧调用方不传这两个参数，行为不变；
   - `unlocked` 按请求对象的 identity 缓存在 converter 上：`self._unlocked = (request, value)`。
5. 以下内容必须完全不变：
   - LockedSpan 和 StageHit 的序列；
   - `RuleExecutionError` 的文案；
   - 正则预算的记账方式：每条正则规则仍然在每个文本上搜索一次；
   - change_id 和 group_id。

   为什么输出不会变：`source_matches` 和 `replace_stage` 按起点分桶，`_resolve_same_start` 用 max 和 min(id) 取结果，与候选的顺序无关；而文本中不存在其前缀的规则不可能匹配，过滤掉也不改变候选集合。

**测试**（`tests/unit/test_rules_compiled.py`）
- `test_prefix_indexed_lock_spans_equals_full_scan_for_300_random_snapshots`：
  - 复用 `_random_rules`，并加入单字符规则、前缀重叠的规则和正则规则；
  - 断言 `lock_spans_compiled(text, overlay)` 与“用全部 `overlay.source_rules` 调用 `source_matches`，再映射为 LockedSpan”的结果相等。
- `test_lock_spans_passes_only_prefix_candidates`：
  - 包装 `rules.matching.collect_matches`，记录传入的字面规则数；
  - 准备 2,000 条以“甲乙”开头的规则，文本为“漢字”×50；
  - 断言传入的字面规则数为 0，且正则规则全部传入。
- `test_convert_rules_does_not_iterate_overlay_rules_per_target`：
  - 用 `object.__setattr__` 把 `overlay.rules` 换成一个会统计 `__iter__` 次数的 tuple 子类；
  - 转换 100 个 target 后，断言迭代次数为 0。
- `tests/integration/test_rules_transform_workflow.py` 的现有用例全部通过。

**验收标准**
- [ ] `benchmark_rules_book.py --modes current` 的 `plan_median_seconds` 不超过修改前的 46%（本机：15.22 s → ≤ 7.0 s），digest 为 `8bab6319592d5abb`。
  - 如果 RULE-01 已经改变了这个夹具的输出，先在 RULE-01 完成后的提交上用 `--modes current` 重新记录基线 digest，再做比较。
- [ ] `literal_rule_scans` ≤ 300,000（修改前 66,400,000）。
- [ ] `tools/benchmark_rules.py` 两种书形都 ≤ 0.8 s。
- [ ] `make check` 通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_compiled.py tests/unit/test_regex_rules.py tests/integration/test_rules_transform_workflow.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/perf/benchmark_rules_book.py --modes current \
  && mise exec -- uv run python tools/benchmark_rules.py
```

**不要做**
- 不要把字面规则合并成一个 alternation 正则，那样会丢掉重叠候选。
- 不要跳过 `validate_rules`、冲突检查或哈希校验。
- 不要改 `ordered_rules` 或优先级。
- 不要跨 plan 或跨 profile 缓存 overlay。
- 不要引入 Aho–Corasick 等新依赖。

---

## PERF-02（P1）打开预览前，主线程上的 `_diagnostic_records` 按单文件规模平方增长

**位置**
- `plugin/OpenCCForSigil/ui/preview_window.py:715`，`_diagnostic_records`：
  - L735：对每个文件都调用 `_source_line_starts(source)`；
  - L763–785：对每条带 span 的诊断，遍历该文件的全部 changes。
- `ui/preview_window.py:670`，`_source_line_starts`：逐字符的 Python 循环。
- 调用方：
  - L1611，`_PreviewDialog.__init__`，在主线程、对话框出现之前执行；
  - L983，`_show_diagnostics_dialog`；
  - L1121，`show_result` 的零变更路径。

**现状**
- 全书 5,711 条诊断、396,091 处变更：耗时 **1.18 s**，占预览对话框构造时间 1.76 s 的 66%。
- `scripts/perf/probe_diagnostic_records.py`（10 个文件，每段一个 inline 标签）。这是 2026-09-28 的重跑结果，与子评审的数据一致：

  | 每文件段落数 | 诊断数 | 变更数 | 耗时 |
  | --- | --- | --- | --- |
  | 60 | 1,146 | 20k | 0.224 s |
  | 120 | 2,267 | 41k | 0.865 s |
  | 240 | 4,550 | 81k | 3.454 s |
  | 480 | 9,116 | 162k | **13.723 s** |

  规模每翻一倍，耗时约变为 4 倍。
- 其中 `_source_line_starts` 单独占 0.143 s；改用正则后为 0.016 s，输出完全相同。

**修改方法**
1. 行起点改用正则：
   ```python
   _LINE_BREAK = re.compile(r"\r\n?|\n")

   def _source_line_starts(source):
       return (0, *(match.end() for match in _LINE_BREAK.finditer(source)))
   ```
   并且改为惰性计算：只有当某条诊断需要从 offset 推算行列或截取片段时才计算。
2. 每个文件只有在存在合法 span 的诊断时，才建一次索引：
   - 按现有的守卫条件过滤变更（file_id 匹配，start 和 end 都是 int），并保留原始下标；
   - 按 `(start, end, 原下标)` 排序；
   - 得到 `starts` 列表，以及排序后 end 值的前缀最大值 `prefix_max_end`（单调不减）。
3. 对每条诊断：
   - `lo = bisect_left(prefix_max_end, diag_start)`，`hi = bisect_right(starts, diag_end)`；
   - 只对 `[lo, hi)` 范围内的变更套用**原来那条**判定表达式（INLINE_BOUNDARY 的判定是 `change_end == start or change_start == end`，其余诊断代码不变）；
   - 命中项按原下标升序排列后再去重，保证 `related` 的顺序与旧实现一致。

   为什么不会漏：满足判定的变更必然满足 start ≤ 诊断 end 且 end ≥ 诊断 start；`prefix_max_end` 单调，所以 `lo` 之前的变更 end 都小于诊断 start。
4. `_DiagnosticRecord` 的字段和文本保持不变。

**测试**（`tests/unit/test_preview_diagnostics.py`）
- `test_diagnostic_records_match_linear_reference_for_random_plans`：
  - 在测试文件中保留旧实现的副本，作为参照；
  - 随机生成 200 轮计划，覆盖零宽、相接、重叠的 span，INLINE_BOUNDARY / QUOTE_UNBALANCED / 无 span / 已给出行列的诊断，以及 CRLF/CR 换行；
  - 断言新旧实现得到的 records tuple 完全相等。
- `test_diagnostic_records_span_accesses_are_near_linear`：
  - 单文件 2,000 条诊断 × 20,000 处变更，把变更的 `span` 换成计数 property；
  - 断言访问次数 ≤ 20 × (变更数 + 诊断数)。
- `test_source_line_starts_handles_lf_cr_crlf`。

**验收标准**
- [ ] `probe_diagnostic_records.py` 中 480 段落那一行 ≤ 0.30 s（修改前 13.7 s），且 240→480 的耗时比 ≤ 2.5。
- [ ] `benchmark_book_pipeline.py` 的 `diagnostic_records_seconds` ≤ 0.15 s（修改前 1.18 s）。
- [ ] `benchmark_preview_ui.py` 的 `dialog_construct_seconds` ≤ 0.75 s（修改前 1.76 s）。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_preview_diagnostics.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/perf/probe_diagnostic_records.py
```

**不要做**
- 不改诊断的去重、排序、文案或关联语义。
- 不把 Translator 或 Qt 调用挪到 worker 线程。
- 不在这一项里把诊断的 QTableWidget 改成虚拟模型（5 万行也只要 0.34 s）。
- 不调用 OpenCC。

---

## PERF-03（P2）冻结计划内存：5.5 MiB 的书常驻 240.6 MiB

**位置**
- `plugin/OpenCCForSigil/core/models.py:12` 的 `SourceSpan` 和 `:80` 的 `TokenChange`：都是 `@dataclass(frozen=True)`，没有 slots。
- `core/planner.py:284`，`_absolute_change`：L331 构造 TokenChange；L321–324 生成 change_id。
- `core/converter.py:90`：切片得到 source/target 字符串。
- `document/tokenizer.py:257`，`_make_target`：L280 执行 `context=source[...]`，但全仓库没有代码读取 `TextTarget.context`（已用 grep 核实）。

**现状**（tracemalloc，`scripts/perf/probe_plan_memory.py`）

| 分配位置 | 内容 | 内存 |
| --- | --- | --- |
| planner.py:331 | TokenChange 对象 | 71.8 MiB |
| converter.py:90 | 变更字符串 | 46.0 MiB（其中不重复的只有 4.8 MiB） |
| planner.py:334 | SourceSpan 对象 | 33.2 MiB |
| planner.py:324 | change_id | 24.6 MiB |
| planner.py:295–296 | int 对象 | 24 MiB |
| tokenizer.py:280 | context | 9.5 MiB |

原型叠加三项修改后为 **158.6 MiB**，digest 保持 `592c07451e572517`。

**修改方法**
1. `SourceSpan` 和 `TokenChange` 改为 `@dataclass(frozen=True, slots=True)`。修改前先 grep，确认没有代码对它们用 `__dict__`、`vars()` 或 pickle。
2. `build_conversion_plan` 中建一个 `strings: dict[str, str] = {}`，传给 `_absolute_change`。构造 TokenChange 之前，对 `change_source` 和 `target_text` 各执行一次 `strings.setdefault(x, x)`，让相同内容共用同一个字符串对象。
3. `_make_target` 改为传 `context=""`。字段本身保留；在 docstring 中注明 `context_radius` 已不再使用。
4. 所有字段值、change_id、变更顺序、`replace()` 和相等比较的语义都保持不变。

**测试**
- `tests/unit/test_models.py::test_change_models_use_slots`：断言实例没有 `__dict__`，且 `replace`、相等比较、hash 的行为不变。
- `tests/unit/test_converter_diff.py::test_plan_shares_equal_change_strings`：构造多个都包含“这”的 target，断言同一 source 的变更对象，其 `.source` 用 `is` 比较为真。
- `tests/unit/test_models.py::test_tokenizer_does_not_copy_target_context`。

**验收标准**
- [ ] 不加参数运行 `probe_plan_memory.py`：`retained_mib` ≤ 170（修改前 240.7），digest 为 `592c07451e572517`。
- [ ] `benchmark_book_pipeline.py` 的 `plan_seconds` 比修改前慢不超过 5%。
- [ ] 全量 `make check` 通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_models.py tests/unit/test_converter_diff.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/perf/probe_plan_memory.py
```

**不要做**
- 不改 change_id 的算法或长度。
- 不丢掉 `PlannedDocument.tokenized` 或 `plan.targets`。
- 不做跨会话的全局缓存。

---

## PERF-04 → 已合并到 [03-rules.md 的 RULE-01](03-rules.md#rule-01)

问题：正则运行预算按整本书累计 3 秒。128 条几乎不命中的正则规则，在 400 个文件（约 11.5 MB）上会让整次分析失败。验证脚本是 `scripts/perf/probe_regex_budget.py --regex-rules 128 --files 200,400`。

---

## PERF-05（P2）状态筛选下的单次决定，以及“本文件”决定，仍然是 O(全部变更)

**位置**（`ui/preview_window.py`）
- L2705，`_refresh`：L2710 判断状态筛选是否生效；L2721 调用 `_visible_entries()` 全量扫描；L2722 用 `next(enumerate(...))` 按身份再扫一遍；L2738 调用 `set_entries`，触发 `beginResetModel`。
- L2974，`_decide_entry`：分组分支在 L2984 传入 `recalculate_counts=True`。
- L2533，`_file_decision_entries`：遍历全部 `self._entries`。
- L3187，`_decide_file`：L3197 遍历全部 entry。
- L2357，`_recompute_counts`：O(N)。

**现状**（真实 Qt，396,091 处变更，`scripts/perf/benchmark_preview_ui.py`）

| 操作 | 耗时 | decision() 调用次数 |
| --- | --- | --- |
| 无筛选时接受当前项 | 5.7 ms | 147 |
| **状态筛选为“未处理”时接受当前项** | **141.5 ms** | 396,447 |
| **接受本文件** | **113.8 ms** | 400,459 |

**修改方法**
1. 在 `__init__` 中一次性构建 `self._entries_by_file = {file_id: tuple(entries)}`，保持原有顺序。`_file_decision_entries` 和 `_decide_file` 只遍历对应文件的 tuple。
2. 分组、文件、筛选三类决定已经通过 `_capture_decisions` 记录了 `before`。决定之后，对每一项调用 `_record_decision_change(file_id, before, preview.decision(id))` 做增量计数，并去掉 `recalculate_counts=True`。撤销、重做和“全部接受”保留现有的一次性重算。
3. 状态筛选下的刷新：
   - 新增 `_refresh_after_decision(affected)`；
   - 为当前可见 tuple 惰性维护一个 `identity → row` 字典，每次筛选变化只建一次，而不是每次单击都建；
   - 离开筛选集合的行，用 `beginRemoveRows/endRemoveRows` 按连续区间删除；
   - 如果有行新进入筛选集合（例如恢复为未处理），回退到完整的 `_refresh()`。
4. 选择行为保持 F-01 冻结的语义：当前行消失后，焦点移到它之后的下一条可见记录；到达末尾时从头继续。

**测试**
- `tests/unit/test_preview_filters.py::test_undecided_filter_accept_does_not_rescan_all_entries`：
  - 2 万个 entry，复用 `test_preview_group_scaling.py` 中的 `VisitCountingEntries`，同时统计 decision() 调用；
  - 断言 decision() ≤ 1,000 次、可见数减 1、焦点落到下一行。
- `tests/unit/test_preview_group_scaling.py::test_accept_file_visits_only_that_file`：
  - 100 个文件 × 200 项；
  - 断言 entry 访问次数 ≤ 3 × 200 + 50；
  - 断言 `_totals`、`_file_filter_counts`、`_accepted_count_by_file` 与重新调用 `_recompute_counts()` 得到的结果相等。
- `tests/unit/test_preview_decision_history.py` 全部通过。

**验收标准**
- [ ] `accept_this_status_undecided` 中位数 ≤ 25 ms，`decision_calls_per_action` ≤ 2,000。
- [ ] `accept_file` ≤ 25 ms，decision() 调用 ≤ 10,000 次。
- [ ] `accept_this_no_filter` ≤ 8 ms，不退化。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_preview_filters.py tests/unit/test_preview_group_scaling.py tests/unit/test_preview_decision_history.py tests/unit/test_preview_window.py -q \
  && QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python docs/reviews/2026-09-28/scripts/perf/benchmark_preview_ui.py
```

**不要做**
- 不拆开原子组。
- 不改 Apply 的可用条件。
- 不改撤销历史的格式或预算。
- 不引入 QSortFilterProxyModel 重写整个表模型。

---

## PERF-06（P3）默认的混合简繁诊断逐字符统计汉字；s2twp/s2hkp 对同一文本重复做 s2t 比较

**位置**
- `core/diagnostics.py:46`：`sum(char.isalpha() and _is_han(char) ...)`。
- `core/diagnostics.py:120`：`_is_han` 对每个字符都遍历一遍范围 tuple。
- `core/converter.py:61–71`：诊断调用 s2t 和 t2s。
- `core/converter.py:82–83`：随后 `classify_conversion`（`core/classifier.py:63–65`）在 s2twp 下再请求一次 s2t。

**现状**（`scripts/perf/probe_default_diagnostics.py`）
- 统计汉字：全书 0.355 s；改用正则后为 0.019 s，计数完全相同。
- 端到端：
  - s2t：3.59 s → 3.21 s；
  - s2twp：s2t 比较调用从 38,478 次降到 20,265 次，耗时 4.32 s → 4.02 s；
  - digest 保持不变。

**修改方法**
1. 统计汉字改用正则：
   ```python
   _HAN_RUN = re.compile("[㐀-䶿一-鿿豈-﫿\U00020000-\U0002fa1f]+")
   evidence = sum(len(run) if run.isalpha() else sum(c.isalpha() for c in run)
                  for run in _HAN_RUN.findall(text))
   ```
   这四段范围与 `core/diagnostics.py:120` 中 `_is_han` 的范围 tuple 逐一对应（已核对）。不要删除 `_is_han`。
2. 在 `convert()` 内建一个只作用于当前这段文本的 memo，初始值为 `{request.config: official}`，并包装成 `compare_once(config)`，同时传给 `diagnose_mixed_script` 和 `classify_conversion`（两者都接受 callable）。

**测试**
- `tests/unit/test_diagnostics.py::test_han_evidence_matches_character_reference`：随机字符串，与逐字符的参照实现比较。
- `tests/unit/test_m4_transforms.py::test_s2twp_requests_each_comparison_config_once_per_text`：用计数的 fake backend，断言每段文本对每个比较配置只调用一次。

**验收标准**
- [ ] `probe_default_diagnostics.py` 的 current 行：s2t ≤ 3.3 s，s2twp ≤ 4.05 s，s2t 比较调用 ≤ 20,300 次。
- [ ] digest 为 `06781c1d491c31f7`（s2t）和 `6284eef800e5b462`（s2twp）。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_diagnostics.py tests/unit/test_m4_transforms.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/perf/probe_default_diagnostics.py
```

**不要做**
- 不关闭默认的诊断或分类。
- 不跨 target 缓存 OpenCC 的输出。
- 不把多个比较配置串联起来调用。
- 不使用手写的简繁对照表。

---

## PERF-07（P3）历史索引：每次提交都全量读、全量校验、带缩进重写，耗时随历史线性增长

**位置**
- `logging_ext/history.py:181`，`record_session`：L211 调用 `self.load()`，全量校验。
- `logging_ext/history.py:30`，`_atomic_json`：L43 执行 `json.dump(..., indent=2, sort_keys=True)`。
- 调用方：`app/controller.py:795` 的 `_record_history`，在主线程执行。

**现状**（`scripts/perf/probe_history_growth.py`，每个会话 200 个文件）

| 已有会话数 | index 大小 | record_session | load |
| --- | --- | --- | --- |
| 0 | 0.1 MiB | 0.003 s | 0.001 s |
| 50 | 5.6 MiB | 0.109 s | 0.024 s |
| 200 | 22.2 MiB | 0.466 s | 0.169 s |
| 1,000 | 110.3 MiB | 2.850 s | 0.940 s |

1,000 个会话时，带缩进写入耗时 1.231 s；改为紧凑格式后只要 0.282 s。

**修改方法**
1. `_atomic_json` 改为紧凑写入（这是产品决定 D6）：
   ```python
   text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
   handle.write(text + "\n")
   ```
   读取端一直使用 `json.load`，兼容新格式。
2. 保留对已有记录的校验，确保损坏仍能被发现。
3. 在 `docs/privacy.md` 或 `docs/architecture.md` 描述历史文件的地方，注明 index 为紧凑 JSON。

**测试**
`tests/unit/test_history_report_self_test.py::test_history_index_is_compact_and_round_trips`：写入两个会话，断言文件中没有 `"\n  "`，并且 `load()` 读出的内容和写入的一致。

**验收标准**
- [ ] 1,000 个会话那一行：`record_session` ≤ 1.6 s，`index_mib` ≤ 75。
- [ ] `load` ≤ 0.95 s。
- [ ] 隐私过滤相关的测试全部通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_history_report_self_test.py tests/unit/test_history_filters.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/perf/probe_history_growth.py
```

**不要做**
- 不自动删除历史。
- 不跳过 `_privacy_value`。
- 不改 `schema_version`。
- 不把正文写入历史。
