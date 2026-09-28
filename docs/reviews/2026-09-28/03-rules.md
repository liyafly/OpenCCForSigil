# 03 规则：语义、正确性与易用性（RULE）

基线 `c14701f`。开始前请先读 [README](README.md) 中的全局约束和产品决定 D1、D2、D3、D7。

复现脚本放在 `docs/reviews/2026-09-28/scripts/rules/`，修复前的输出放在 `evidence/rules/<同名>.out`。运行方式：

```sh
mise exec -- uv run python docs/reviews/2026-09-28/scripts/rules/<脚本>.py
```

下列条目不与以下已完成的内容重复：2026-09-24 的 A-08、A-09、A-10，2026-09-26 的 R-01～R-12、U-01，2026-09-27 的 UX-06、UX-07。

## 0. 用户看到的规则模型：概念太多

**决定一条规则会不会生效，共有 7 个开关：**
1. 本次运行是否引用了这个规则集；
2. 规则集自身的“启用”，实际上是持久、全局的（见 RULE-11）；
3. 规则自身的“启用”；
4. 方向：16 个具体方向或 `*`，必须完全相等；
5. 范围：全局、当前方案、当前书；
6. 归属：属于哪个方案或哪本书，界面上看不出来（见 RULE-14）；
7. 内置规则包开关。

**冲突时谁赢，有 6 层隐含排序：**
动作（保护 > 最终写法 > 替换）＞ 隐藏的语义版本 V1/V2 ＞ 范围 ＞ 最左位置 ＞ 匹配长度 ＞ 优先级 ＞ ID。

**本轮目标：** 普通用户只需要理解“规则集（这次用不用）”和“规则（源 → 目标、方向、范围）”。

- RULE-11 把第 1、2 个开关分开，并说清楚各自的作用。
- RULE-02 去掉“隐藏版本压过范围”这一层。
- RULE-04 把“最左位置优先”写进文档和测试窗口。
- RULE-10、RULE-06 让最常见的操作（加一条规则、粘贴一个词表）直接可用。

---

<a id="rule-01"></a>
## RULE-01（bug，P1）正则预算把重叠候选也算成命中，并且按整本书累计：自带的“整理空格”模板会让普通书的分析中止（已合并 PERF-04）

**位置**
- `plugin/OpenCCForSigil/rules/matching.py:163`：`collect_matches()` 对**每个候选**都调用 `budget.note_regex_hit`。
- `rules/matching.py:184`：`cursor = found.start() + 1`，这会让同一段文字产生 N 个重叠候选。
- `rules/matching.py:69-80`：`RegexBudget.note_regex_hit`。
- `rules/matching.py:14`：`REGEX_RUN_BUDGET_SECONDS = 3.0`。
- `rules/matching.py:17-18`：`REGEX_MAX_HITS_PER_RULE = 512`、`REGEX_MAX_HITS_PER_RUN = 4096`。
- `rules/matching.py:54-67`：`timeout_for`、`note_regex_time`。
- `core/converter.py:152-154`：每个 converter 只有一个预算对象；`core/workflow.py:179` 整次分析只用一个 converter，所以预算按全书累计。
- `rules/templates.py:59`：`collapse_horizontal_spaces()`。

**现状**

`scripts/rules/rule01_regex_hit_budget.py` 的输出：
```
(a) text='你好世界再见' pattern=\p{Han}+ -> candidates: 6 budget.regex_hits: 6 (only 1 replacement is applied)
(b) 600-char paragraph: RuleExecutionError rule han: regular expression exceeded 512 hits near offset 512
(c) 60 files x 10 paragraphs with one double space: RuleExecutionError rule spaces: regular expression exceeded 512 hits near offset 1
(d) 40 files: 400 changes, OK
```
- 60 章、每章 10 处双空格的书，用自带模板就会让整次分析失败。
- 沙箱每次测试都新建预算，所以沙箱里总是通过，只有在真实书上才失败。

`scripts/perf/probe_regex_budget.py --regex-rules 128 --files 200,400` 的结果：128 条几乎不命中的正则规则，在 400 个文件（约 11.5 MB）上报错 `exceeded its 3 second budget`。单次搜索只需约 0.6 µs，但整书累计的时间超过了 3 秒。

**期望**
- `docs/rule-format.md:23` 写的是 “512 hits per rule”，用户理解为实际替换次数。Spec §11.5 保护的对象是替换次数。
- 自带模板在普通书上必须能用。
- 预算只应在规则真的昂贵时耗尽；灾难性回溯仍然要 fail-closed。

**修改方法**（按 README 的 D1）
1. 新增常量，并修改原有常量：
   ```python
   REGEX_MAX_HITS_PER_RULE = 512            # 语义改为：单规则、单文本片段、单阶段内已采用的命中数
   REGEX_MAX_HITS_PER_RUN = 100_000         # 整次分析已采用的命中数
   REGEX_MAX_CANDIDATES_PER_FRAGMENT = 20_000  # 单规则、单文本片段的候选数，仅作内存保护
   REGEX_SECONDS_PER_MILLION_CHARS = 2.0
   ```
2. 在 `RegexBudget` 中：
   - 新增 `self.scanned_chars = 0`，以及方法 `note_scan(self, length: int)`；
   - 新增 `allowance()`，返回 `REGEX_RUN_BUDGET_SECONDS + REGEX_SECONDS_PER_MILLION_CHARS * self.scanned_chars / 1_000_000`；
   - `timeout_for` 和 `note_regex_time` 中的 `REGEX_RUN_BUDGET_SECONDS` 全部改为 `self.allowance()`。报错文案保持 `exceeded its {N:g} second budget` 的格式，N 取当时的 allowance。
3. `collect_matches()`：
   - 在进入 regex 循环之前，如果这一批 `rules` 中含有 regex 规则，调用一次 `budget.note_scan(len(text))`。每次调用只记一次，不按规则数重复记；
   - 删除 `:163` 的 `budget.note_regex_hit(...)`，改为对本规则维护一个局部计数 `candidates`；超过 `REGEX_MAX_CANDIDATES_PER_FRAGMENT` 时抛出 `RuleExecutionError(f"rule {rule.id}: regular expression produced more than {N} candidates near offset {pos}")`；
   - `note_candidate_output` 保持不变。
4. 修改 `source_matches()` 和 `replace_stage()`：
   - 每次调用建一个局部 `dict` 作为 `fragment_hits`；
   - 对最终**被采用**、且 `chosen.rule.match_type == "regex"` 的匹配，调用 `budget.note_regex_hit(chosen.rule, chosen.start, fragment_hits)`。
5. `note_regex_hit(rule, position, fragment_hits)`：
   - 单规则上限改用 `fragment_hits[rule.id]` 计数，不再用 `self._hits_by_rule`；
   - 整次上限仍用 `self.regex_hits`；
   - 删除 `self._hits_by_rule`（先 grep，确认没有其他地方引用）。
6. 同步修改 `docs/rule-format.md:20-27` 和 `resources/rule-guide.md` 三种语言中的数字和描述：“每条正则在一段文字中最多替换 512 处，整次分析最多 100,000 处”。

**测试**（`tests/unit/test_regex_rules.py`）
- `test_overlapping_regex_candidates_do_not_count_as_hits`：`\p{Han}+` 作用于 `你好世界再见`，走一遍 `replace_stage`，断言 `budget.regex_hits == 1`。
- `test_collapse_spaces_template_plans_600_matches_across_60_files`：复用脚本 (c) 的书，断言 `flow.plan()` 成功，并且变更总数为 600。
- `test_runaway_regex_in_one_fragment_still_stops`：用 monkeypatch 把 `REGEX_MAX_HITS_PER_RULE` 改为 3，在同一片段上产生 4 次已采用命中，断言抛出 `RuleExecutionError`，且消息中含规则 ID。
- `test_regex_budget_allowance_grows_with_scanned_text`：
  - monkeypatch `rules.matching.time.monotonic`，让每次 search 推进 1 ms；
  - 10,000 个长度为 100 的 target、1 条规则，应当通过；
  - 另一个场景中，单次 search 被模拟为耗时 3.1 s（大于当时的 allowance），仍然报错。
- 现有的 `test_expired_regex_budget_stops_with_rule_identity`、`test_replacement_output_budget_*` 继续通过。

**验收标准**
- [ ] 脚本输出中，(a) 为 `regex_hits: 1`，(b) 和 (c) 都能正常完成。
- [ ] `probe_regex_budget.py --regex-rules 128 --files 200,400` 两行都是 `ok`，且 400 个文件的 plan 时间不超过 200 个文件的 2.2 倍。
- [ ] 单次搜索超过 50 ms 仍然报错。
- [ ] 文档中的数字与常量一致。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_regex_rules.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/rules/rule01_regex_hit_budget.py \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/perf/probe_regex_budget.py --regex-rules 128 --files 200,400
```

**不要做**
- 不取消时间预算、单次超时、输出上限或候选上限。
- 不把候选枚举改成不重叠（`cursor = found.end()`），那样会改变跨规则的选择结果。
- 不把多个 target 拼成一段来搜索。
- 不修改正则方言。

---

## RULE-02（bug，P1）隐藏的语义版本压过了范围：V2 规则不看范围就能击败 V1；TSV/CSV/TXT 导入一律生成 V1；冲突检测看不到这种对立

**依赖**：RULE-05 先完成。本条会把跨版本的同源异目标变成阻断冲突，用户必须能在规则窗口里看到冲突并解决。

**位置**
- `rules/matching.py:97-100`，`_rank()`：
  ```python
  return (type_rank(rule), rule.semantic_version, scope_rank(rule),
          match.end - match.start, int(rule.priority))
  ```
- `rules/precedence.py:62-86`，`ordered_rules()`：排序中使用了 `-semantic_version`。
- `rules/conflicts.py:46-58` 和 `97-108`：冲突分组键中包含 `semantic_version`。
- `rules/importers.py:197-207` 的 `_rows_to_rules()`、`241-250` 的 `_opencc_rows()`：都不写 `semantic_version`，所以默认为 1。
- `ui/rules_window.py:1356-1360`，`_rule_from_form()`：新规则的版本取决于它所在的规则集。

**现状**

`scripts/rules/rule02_precedence_semantics.py` 的输出：
```
final: ('頭髮(全局)', [('v2-global', '头发', '頭髮(全局)')])   ← 同一位置，书籍 V1 规则输给了全局 V2 规则
conflicts reported: []
TSV-imported rule semantic_version: [1]
additions: [('软件', '軟件', 1)] duplicates: 0 conflicts: []
runtime winner: ('軟體', [('ui', '软件', '軟體')])            ← 导入的更正规则永远不会生效
```
用户用 TSV 导入“软件→軟件”，想更正已有的“软件→軟體”。导入预览显示“新增 1、冲突 0”，但导入的规则永远不会生效。界面上完全看不到版本信息。

**期望**
- Spec §11.2：书籍范围的 exact 规则优先于全局范围的 exact 规则。
- §11.8.3：同范围、同优先级、同源、不同目标，就是阻断冲突，与版本无关。

**修改方法**（按 README 的 D2）
1. 在 `import_rules(..., semantic_version: int = 2)` 中，`_rows_to_rules` 和 `_opencc_rows` 把以下字段写进 `values`：`semantic_version`、`action="override"`、`match_type="literal"`、`stage="source"`。
   `RuleManagerDialog._import()` 调用时传入 `self._rulesets[self._ruleset_id].semantic_version`。
2. `matching._rank` 删除 `semantic_version` 这一维。`_resolve_same_start(candidates)` 改为：
   ```python
   def _resolve_same_start(candidates):
       legacy = all(c.rule.semantic_version <= 1 for c in candidates)
       def rank(c):
           r = c.rule
           return (type_rank(r), scope_rank(r, legacy=legacy), c.end - c.start, int(r.priority))
       ...  # 其余逻辑（max + 最小 id 作为平局裁决）保持不变
   ```
   `scope_rank` 增加关键字参数 `legacy`：为 True 时使用 V1 表 `{book:3, global:2, profile:1, builtin:0}`，否则使用 V2 表（即现在的 V2 顺序）。
   `_rank` 的其他调用方要一并检查，都改为经过 `_resolve_same_start`，或者显式传入 `legacy`。
3. `ordered_rules` 同步删除 `-semantic_version`。它只用于确定排序，删除后结果必须仍然是确定的。
4. `conflicts.find_conflicts` 的两个分组键删除 `semantic_version`。`rule_dedup_key` 保持不变（R-03 的要求）。
5. 规则详情增加一行，新键 `rules.detail_version`：
   - zh-Hans：“规则格式：{version}”，其中 V1 显示“旧版（范围顺序：书 > 全局 > 方案）”；
   - zh-Hant 和 en 同步。
6. 在 `docs/rules-and-profiles.md:54` 附近补一句：同一位置的候选中只要有一条 V2 规则，就统一使用 V2 的范围顺序。

**测试**
- `tests/unit/test_rules_m3.py::test_v1_book_rule_beats_v2_global_rule_at_same_position`：断言最终结果为 `頭髮(书)`。
- `tests/unit/test_rules_m3.py::test_cross_version_same_source_different_target_is_blocking`：断言 `blocking_conflicts([...])` 非空。
- `tests/unit/test_rule_import_export_roundtrip.py::test_tsv_import_uses_target_ruleset_semantic_version`：断言 `semantic_version == 2`。
- 以下现有测试保持通过：`test_new_ruleset_precedence_changes_without_changing_legacy_order`、`test_compiled_lock_spans_matches_legacy_ordering_for_300_random_snapshots`。

**验收标准**
- [ ] 脚本中 RULE-02 一段输出 `頭髮(书)`。
- [ ] RULE-02c 一段的 `review.conflicts` 中含有 `SAME_SOURCE_DIFFERENT_TARGET`。
- [ ] 只含 V1 规则的规则集，转换结果不变（300 组随机等价测试通过）。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_m3.py tests/unit/test_rules_compiled.py tests/unit/test_rule_import_export_roundtrip.py -q
```

**不要做**
- 不自动把磁盘上的 V1 规则迁移成 V2。
- 不从 `rule_dedup_key` 中删除 `semantic_version`。
- 不改 JSON schema。

---

## RULE-03（bug，P2）同一起点最长的覆盖规则与保护区间重叠时，整个起点被放弃，更短的规则不再尝试

**位置**：`rules/matching.py:215-226`，`source_matches()`：
```python
chosen = _resolve_same_start(override_candidates[start])
if (protected_index < len(protected)
        and protected[protected_index].start < chosen.end):
    continue
```

**现状**（`rule02_precedence_semantics.py`）
```
with long+short: ('大乾隆', [('p', '乾隆', '乾隆')])
short only     : ('太乾隆', [('short', '大', '太'), ('p', '乾隆', '乾隆')])
```
多加一条“大乾→大幹”后，原本生效的“大→太”反而失效了，行为不单调。

**期望**：按 2026-09-24 A-08 修改步骤第 2 条：“跳过这个候选，尝试同一起点的下一个候选”。

**修改方法**
```python
blocker = protected[protected_index] if protected_index < len(protected) else None
if blocker is not None and blocker.start <= start:
    continue  # start 本身落在保护区间内
allowed = [c for c in override_candidates[start]
           if blocker is None or c.end <= blocker.start]
if not allowed:
    continue
chosen = _resolve_same_start(allowed)
```
先确认 `protected_index` 在循环中推进的方式，使 `blocker` 是第一个 `end > start` 的保护区间。现有逻辑如果不是这样，按现有推进逻辑取“下一个可能重叠的保护区间”。保护区间第一遍的选择逻辑不变。

**测试**：`tests/unit/test_rules_compiled.py::test_shorter_override_at_same_start_survives_overlapping_protect`
- 规则：protect `乾隆`、`大乾→大幹`、`大→太`；
- 断言 `lock_spans_compiled("大乾隆", overlay)` 的 source 依次为 `["大", "乾隆"]`，target 依次为 `["太", "乾隆"]`。

**验收标准**
- [ ] 新测试通过。
- [ ] `test_protect_rule_wins_over_earlier_overlapping_exact_match`、`test_exact_rule_still_matches_when_it_does_not_overlap_a_protect_span`，以及 300 组随机等价测试，全部通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_compiled.py -q
```

**不要做**
- 不改“保护优先”的原则。
- 不让被淘汰的更长候选以截断的形式生效。

---

## RULE-04（design，P2）“最左位置优先”压过了范围和优先级，但文档和测试窗口都没有说明

**位置**
- `rules/matching.py:215-219`（`source_matches()`）、`246-251`（`replace_stage()`）：按起点从左到右贪心选择。
- `docs/rules-and-profiles.md:54-57`；i18n 中的 `rules.help`；`ui/rules_window.py:_test()` 的 trace。

**现状**（`rule02_precedence_semantics.py`）
```
global '大乾' vs book '乾隆帝'(priority 100000) on '大乾隆帝': ('G隆帝', [('g', '大乾', 'G')])
```
一条优先级最高的书籍规则，输给了一条位置更靠左的全局规则。文档没有说明范围和优先级只在**同一起点**的候选之间比较。

**期望**：实现符合 Spec §11.8.3（前提是“同一位置有多条规则匹配”），但需要一句面向用户的解释，并在测试窗口里显示哪些候选没有被采用。

**修改方法**
1. 在 `docs/rules-and-profiles.md:54`、三种语言的 `resources/rule-guide.md`，以及三种语言的 `rules.help` 中，加一句：“规则按出现位置从左到右生效；范围和优先级只在同一起点的候选之间比较。”
2. `replace_stage` 和 `source_matches` 增加可选参数 `skipped: list | None = None`。只有调用方传入列表时，才收集因 `start < cursor` 或与保护区间重叠而跳过的候选。
3. `rules/engine.py` 的沙箱路径在 `include_rule_trace=True` 时传入这个列表，trace 中追加新键 `rules.rule_skipped_overlap`，文案为“{id} 未采用：与 {winner} 在 {start}–{end} 重叠”（三种语言）。

**测试**
- `tests/unit/test_rules_window.py::test_sandbox_lists_candidates_skipped_by_an_earlier_overlap`：断言输出中同时含 `b 未采用` 和 `g`。
- `tests/unit/test_regex_rules.py::test_skipped_candidate_trace_does_not_change_patches`（现有 `include_rule_trace` 测试就在这个文件中）：断言开启和关闭 trace 时，补丁完全相同（沿用 R-07 的约束）。

**验收标准**
- [ ] 文档和帮助中都有这一句说明。
- [ ] 沙箱能显示被抢先的规则。
- [ ] 开启和关闭 trace 时，转换结果和补丁完全相同。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/unit/test_i18n.py -q
```

**不要做**
- 不改成全局最优匹配。
- 不为显示 trace 而重复执行正则。

---

## RULE-05（bug，P1）同一次运行中不同规则集之间的冲突，在规则窗口和导入预览里看不到，直到分析时才整体失败

**位置**
- `ui/rules_window.py:1165`，`_refresh()`：`conflicts = find_conflicts(self.rules)`，只检查当前规则集。
- `ui/rules_window.py:84`，`review_import()`：同样只检查当前规则集。
- `app/settings.py:381-412`，`freeze_rules()`：把所有规则集拼接在一起。
- `rules/compiled.py:64`：`validate_no_blocking_conflicts(candidates)` 在分析时才抛出异常。

**现状**（`scripts/rules/rule05_cross_ruleset_conflict.py`）
```
conflicts shown while editing set A: []
conflicts shown while editing set B: []
analysis: BlockingRuleConflict -> blocking rule conflicts: BLOCKING CONFLICT: SAME_SOURCE_DIFFERENT_TARGET: '软件' ...
```
两个规则集都能保存，沙箱也只报通用的“无法完成规则操作”，真正开始转换时才失败，而且走的是通用错误路径 `controller_failed`。

**期望**：按 Spec §83，必须在开始之前就能看到阻断冲突，并且能看到冲突双方是谁。

**修改方法**
1. `RuleManagerDialog` 新增 `_run_candidates()`：
   - 取 `self._run_options["ruleset_ids"]` 中各规则集的草稿；如果当前规则集有未保存的草稿，先调用 `_stash_ruleset()`；
   - 只取启用的规则集；
   - 按 `applies_to(config, profile_id, book_fingerprint)` 过滤规则。
2. `_refresh()`：在当前规则集的冲突之外，再计算 `blocking_conflicts(_run_candidates())` 中涉及当前规则集规则 ID 的那些冲突：
   - 在冲突列表中显示为新键 `rules.conflict_other_ruleset` =“与规则集 {ruleset} 冲突：{detail}”（三种语言）；
   - 这类冲突同样禁用“保存规则集”按钮。
3. `review_import(existing, imported, *, other_run_rules=())`：把其他规则集的规则纳入冲突计算。`_import()` 调用时传入这个参数。
4. `RunSettings.freeze_rules()` 返回之前，对适用于本次的规则调用 `validate_no_blocking_conflicts`：
   - 失败时抛出带规则 ID 和规则集 ID 的 `app.errors.RuleConflictError`；如果这个类不存在，就新建，继承现有错误基类；
   - controller 捕获后显示本地化的说明，新键为 `error.rule_conflict`。

**测试**
- `tests/unit/test_rules_window.py::test_conflict_with_another_run_ruleset_is_listed_and_blocks_save`。
- `tests/integration/test_ruleset_persistence.py::test_freeze_rules_reports_cross_ruleset_conflict_with_ruleset_ids`：断言 `pytest.raises(RuleConflictError)`，且消息中含 `a1` 和 `b1`。
- 现有的 `test_conflicts_in_an_unselected_direction_do_not_block_this_run` 继续通过。

**验收标准**
- [ ] 脚本中的两个规则集，在规则窗口里能看到冲突，并且“保存”被禁用。
- [ ] 导入到 B 时，导入预览中显示这个冲突。
- [ ] 分析之前就能得到本地化的冲突说明，而不是通用的失败提示。
- [ ] 不同方向、不同书、不同方案的规则互不阻断。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/integration/test_ruleset_persistence.py tests/unit/test_rules_compiled.py -q
```

**不要做**
- 不对未被本次引用的规则集阻断保存。
- 不放宽 `CompiledOverlay.build` 的阻断。
- 本条不新增“SHADOWED（被遮蔽）”冲突种类，留作以后单独设计。

---

## RULE-06（design，P1）最简单的“源<Tab>目标”两列表格导入会被拒绝，中文表头不识别，也没有批量粘贴

**位置**
- `rules/importers.py:195-207`，`_rows_to_rules()`：`len(row) < 3` 时直接报错，并且固定把第 0 列当作方向。
- `rules/importers.py:296-298`，`_is_header()`：只识别英文表头。
- `ui/rules_window.py:638`：只能逐条录入规则。

**现状**（`scripts/rules/rule06_import_formats.py`）
```
2-col TSV: rules= [] diagnostics= [(1, 'line', 'rule 1: expected direction, source, target, comment'), ...]
3-col TSV without direction column: rules= [] ... "direction is required ..."
Chinese header row: rules= [('s2t', '软件', '軟體')] diagnostics= [(1, 'line', "rule 0: direction: ...")]
```
导入对话框里明明已经选了方向，最常见的两列词表却全部失败。

**修改方法**
1. `_rows_to_rules()`：
   - `len(row) == 2`：视为 `(source, target)`，方向取对话框里选定的 `direction`。如果没有 `direction`，报新键 `rules.import_needs_direction`。
   - `len(row) >= 3`、`row[0].strip()` 不在 `SUPPORTED_DIRECTIONS ∪ {"*"}` 中、并且提供了 `direction`：视为 `(source, target, comment)`。
   - 其他情况保持现状，保证旧的 4 列格式不受影响。
2. `_is_header()`：去掉首尾空白后，只要该行第一个字段属于下列集合，就把这一行当作表头：`{"方向","源","源文本","原文","目标","目标文本","目標","目標文字","來源文字","备注","備註","comment","direction","source","target"}`。比较时不区分大小写。
3. 在规则窗口的导入/导出区增加“批量添加…”入口（UXS-06 完成后放进“更多…”菜单）：
   - 弹出一个带 `QPlainTextEdit` 的对话框，说明文字写明“每行一条：源<Tab>目标，或 源=目标，或 源→目标”；
   - 确认后，把每行第一个 `=` 或 `→` 替换为 Tab，然后调用 `import_rules(text, format="tsv", direction=当前方向, scope=当前范围, ...)`；
   - 结果走现有流程：`reassign_colliding_ids` → `review_import` → `_confirm_import`。去重、冲突检查和错误行显示都照常进行。
4. 在三种语言的 `resources/rule-guide.md` 中，加入两列格式的示例。

**测试**（`tests/unit/test_rule_import_export_roundtrip.py`，除非另注）
- `test_two_column_tsv_uses_selected_direction`：得到 2 条 `s2t` 规则。
- `test_three_columns_without_direction_are_source_target_comment`。
- `test_chinese_tsv_header_is_skipped`：没有诊断，得到 1 条规则。
- `tests/unit/test_rules_window.py::test_bulk_paste_adds_rules_through_import_review`：3 行中有 1 行重复，断言新增 2 条、重复 1 条。

**验收标准**
- [ ] 两列、三列（无方向列）、中文表头的文件都能导入。
- [ ] 旧的 4 列格式，以及导出后再导入的往返结果不变（`probe_edge_cases.py` 中的 TSV roundtrip 仍为 True）。
- [ ] 批量添加经过导入预览；取消时规则列表不变。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_rules_window.py -q
```

**不要做**
- 不新增 CSV schema。
- 批量添加不能绕过去重和冲突检查。
- 不自动猜测方向。

---

## RULE-07（bug，P2）TSV 导入沿用了 CSV 的引号规则：源文本两侧的 ASCII 引号被吞掉，不成对的引号会吞掉后面的行

**位置**：`rules/importers.py:172-174`，`_delimited_rows()`，其中 `csv.reader(io.StringIO(text), delimiter=delimiter)` 同时处理 TSV 和 CSV。

**现状**（`rule06_import_formats.py`）
```
quoted source : rules= [('s2t', '引号', '「引号」')] diagnostics= []
unbalanced quote: rules= [] diagnostics= [(1, 'line', 'rule 1: expected direction, source, target, comment')]
```
- 第一例：源文本 `"引号"` 被悄悄改成了 `引号`。
- 第二例：3 行被合并成 1 行后报错，另外 2 条规则丢失。

**修改方法**
1. TSV 导入改为逐行 `line.split("\t")`：先去掉 BOM，再按 `splitlines()` 分行，不做任何引号处理。CSV 仍然使用 `csv.reader`。
2. 修改 `exporters._delimited()` 的 TSV 分支：
   - 字段原样写出，不加引号；
   - source、target、comment 中含有 `\t`、`\r` 或 `\n` 的规则，跳过不导出；
   - 跳过的数量复用 `export_warnings` 报告，新键为 `rules.export_tsv_skipped`。
3. 兼容旧的导出文件：导入时如果某个字段匹配 `^".*"$` 并且内部含有 `""`，追加一条 warning 诊断：“字段两侧带引号，已按原样导入”。内容本身不改写。

**测试**（`tests/unit/test_rule_import_export_roundtrip.py`）
- `test_tsv_keeps_ascii_quotes_literally`：源文本为 `"引号"`。
- `test_tsv_unbalanced_quote_does_not_swallow_following_lines`：得到 3 条规则。
- `test_tsv_export_import_roundtrip_with_quotes`。

**验收标准**
- [ ] 两个示例都按行得到结果。
- [ ] 导出后再导入，结果与原来一致。
- [ ] CSV 的行为不变。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_rules_m3.py -q
```

**不要做**：不改 CSV 解析；不改 JSON。

---

## RULE-08（bug，P3）TSV/CSV 导入的错误行号是解析后的记录序号，不是文件中的物理行号；消息前面还带着“rule 0:”

**位置**
- `rules/importers.py:115-123`，`import_rules()`：`for index, value in enumerate(values, 1)` 被当作行号使用。
- `rules/validators.py:210-216`：调用 `validate_rules((value,))` 时 `index=0`，所以消息前缀是“rule 0:”。

**现状**（`rule06_import_formats.py`）
```
bad direction on physical line 6: ... diagnostics= [(2, 'line', "rule 0: direction: ...")]
```

**期望**：按 R-12 第 3 点，CSV/TSV/TXT 报告物理行号，JSON 报告记录序号。

**修改方法**
1. `_rows_to_rules`、`_opencc_rows`、`_json_rules` 改为返回 `list[tuple[int, Rule]]`，携带物理行号；JSON 携带记录序号。
   - 物理行号在 `_delimited_rows` 中获得：RULE-07 之后 TSV 按行拆分，行号直接可得；CSV 使用 `reader.line_num`。
2. `import_rules` 的校验循环使用携带的行号，并调用 `validate_rule(value, index=None)`，不再产生“rule 0:”前缀。如果 `validate_rule` 不接受 `index=None`，就为它增加这个参数，默认值保持现在的行为。

**测试**：`tests/unit/test_rule_import_export_roundtrip.py::test_delimited_validation_errors_report_physical_line`
- 断言 `diagnostics[0].line == 6`，并且 `"rule 0" not in diagnostics[0].message`。

**验收标准**
- [ ] TSV、CSV、TXT 报告物理行号，JSON 报告记录序号。
- [ ] `test_lenient_json_import_skips_bad_records_and_preserves_record_numbers` 通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rule_import_export_roundtrip.py -q
```

**不要做**：不改 strict/lenient 的语义。

---

## RULE-09（bug，P2）JSON 导入忽略对话框里选的范围；其他书或方案的规则被静默导入后永远不生效；全局规则被写入当前方案的归属

**位置**
- `rules/importers.py:279-285`，`_json_rules()`。
- `rules/models.py:111-116`，`Rule.from_dict()`：只要字段为空，就填入 `profile_id` 和 `book_fingerprint`，不管范围是什么。
- `ui/rules_window.py:1754-1762`，`_import_options()`。

**现状**（`rule06_import_formats.py`）
```
chosen scope=book -> imported scope: global book_fingerprint: 'THIS-BOOK' profile_id: 'P'
foreign book rule -> scope: book owner: OTHER-BOOK (never active in this book)
canonical equal: False diff: {'profile_id': ('', 'P')}
```

**修改方法**
1. `Rule.from_dict()`：只在最终 `scope == "profile"` 时填 `profile_id`，只在 `scope == "book"` 时填 `book_fingerprint`。修改前先 grep `from_dict` 的所有调用方，确认没有依赖旧行为；如果有，就在那个调用方显式传入字段。
2. `_import_options()`：格式为 JSON 时，范围控件的标签改为新键 `rules.import_scope_default_only`（“仅用于未写范围的记录”）。
3. `_confirm_import()`：统计 `additions` 中因归属不符而 `not applies_to(...)` 的数量，追加新键 `rules.import_foreign_owner` =“{count} 条规则属于其他书籍/方案，本次不会生效”。
4. 选项对话框增加复选框 `rules.import_rebind_owner`：“把其他书/方案的规则改绑到当前书/方案”。默认不勾选；只有勾选后，才改写归属。

**测试**（`tests/unit/test_rule_import_export_roundtrip.py`）
- `test_json_global_rule_roundtrip_keeps_empty_owner_fields`：导出再导入后，canonical 形式相等。
- `test_json_import_reports_foreign_owner_rules`：提示中的计数为 1。
- `test_json_import_rebinds_foreign_owner_only_when_requested`。

**验收标准**
- [ ] 全局规则导出再导入后，canonical 形式相等。
- [ ] 属于其他书或方案的规则有明确提示。
- [ ] 默认不改写归属。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rule_import_export_roundtrip.py tests/unit/test_rules_window.py -q
```

**不要做**：不实现 C-02 迁移包；不改 `rule_dedup_key`；不自动改绑。

---

## RULE-10（bug，P1）在默认规则集里新建规则时，方向默认是“任意方向”：s2t 时加的规则会作用到以后的 t2s 转换

**位置**
- `app/settings.py:295`：`values.setdefault("default", RuleSet("default"))`。
- `rules/store.py:34`：`default_direction: str = "*"`。
- `ui/rules_window.py:857-866`，`_apply_rule_defaults()`：在 `:809` 的 `_populate_rulesets()` 中调用，覆盖了 `_select_default_direction(self.direction_combo, self._config)` 的结果。
- 对照：`_new_ruleset()` 在 `:1043` 使用的是 `base_direction(self._config)`。

**现状**（`scripts/rules/rule10_ui_defaults_qt.py`，使用真实的 vendored OpenCC）
```
RULE-10 run config = s2t; new-rule direction preselected: * -> 任意方向
  added rule: 里 -> 裡 direction = '*'
  applies to a later t2s run: True
  t2s without rule: 他每天走三公里去邻里的学校。
  t2s with the '*' rule added during an s2t session: 他每天走三公裡去邻裡的学校。
```

**期望**
- Spec §11.7 规定规则必须明确方向。
- 现有测试 `test_direction_default_is_selected_from_current_config` 的意图，就是默认取当前方向。

**修改方法**（按 README 的 D7）
1. `app/settings.py` 的 `edit_rules()`：改为 `values.setdefault("default", RuleSet("default", default_direction=base_direction(config)))`。对磁盘上不存在的其他 `identifiers`，同样处理。
2. `_apply_rule_defaults()`：当 `current.default_direction == "*"` 时，预选 `base_direction(self._config)`。
3. 当方向下拉框选中 `*` 时，在编辑区和规则详情中显示新键 `rules.wildcard_direction_warning`：
   - zh-Hans：“此规则也会用于其他方向（包括繁→简）”
   - zh-Hant：“此規則也會用於其他方向（包括繁→簡）”
   - en：“This rule also applies to other directions, including Traditional→Simplified.”
4. `_clear_editor()` 和 `_add()` 执行之后，不要把方向重置为 `*`。

**测试**
- `tests/unit/test_rules_window.py::test_new_rule_in_fresh_default_set_uses_current_direction`：
  - 用 `RuleManagerDialog(make_with_table(), (), rulesets=(RuleSet("default"),), config="s2t", ...)` 构造窗口；
  - 断言 `direction_combo.currentData() == "s2t"`；
  - 执行 `_add()` 后，断言新规则的方向为 `"s2t"`。
- `tests/unit/test_rules_window.py::test_wildcard_direction_shows_reverse_warning`。

**验收标准**
- [ ] 脚本第一行的预选方向为 `s2t`。
- [ ] 已经存在的 `*` 规则不被改写。
- [ ] 三种语言的文案齐全。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py tests/unit/test_i18n.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/rules/rule10_ui_defaults_qt.py
```

**不要做**
- 不迁移已保存规则的方向。
- 不引入“方向族”（例如 s2*）的新语义。
- 不删除 `*` 选项。

---

<a id="rule-11"></a>
## RULE-11（bug，P1）规则集的“本次使用”和“全局启用”混在一起：标着“本次”的开关实际永久全局生效；只是浏览另一个规则集，保存时也会把它加入本次（已合并 UXS-05 和原 RULE-12 的“本次引用”部分）

**位置**
- `ui/rules_window.py:511`：`self.ruleset_enabled_check`，文案键 `rules.ruleset_enabled` =“本次启用此规则集”（en “Use this rule set”）。
- `ui/rules_window.py:811-827`，`_stash_ruleset()`：把勾选状态写入 `RuleSet.enabled`。
- `app/settings.py:329`：保存规则集文件。
- `app/settings.py:390`，`freeze_rules()`：`if ruleset.enabled:` 对所有方案都生效。
- `app/settings.py:339-358`，`edit_rules()`：`updated_rule_ids = ... + [selected_id]`，这一步无条件执行。
- `ui/rules_window.py:1889-1899`，`_apply()`：生成 `RuleWindowResult`。

**现状**（`scripts/rules/rule11_ruleset_enabled_is_global.py`）
```
before: profile B freezes ['r1']
label shown to the user: 本次启用此规则集
after : shared.json enabled = False
after : profile B (never touched) freezes []
-- merely viewing another ruleset and saving adds it to this run --
run ruleset_ids before: ()
run ruleset_ids after : ('other',)
```
- 标着“本次”的开关，实际上是写入文件、对所有方案生效的开关。
- 保存时，下拉框里正在显示哪个规则集，就把哪个规则集加入本次转换。
- 如果当前方案已保存，保存时会先问“将规则集 X 加入方案 Y？”；选“否”之后，还会再弹一个信息框“仅在本次运行中生效”，一次保存最多弹出 2 个模态框。

**期望**
- 是否用于本次转换，由用户明确勾选决定，并且只在当前会话中有效。
- 全局启用开关的文案要如实说明它的作用范围。
- 保存一次，最多出现 1 个问题框。

**修改方法**
1. 修改 `rules.ruleset_enabled` 的文案：
   - zh-Hans：“启用此规则集（所有方案）”
   - zh-Hant：“啟用此規則集（所有設定檔）”
   - en：“Enable this rule set (all profiles)”

   另外：
   - 为这个复选框加 tooltip，列出引用该规则集的方案名。方案名由 `RunSettings.edit_rules` 通过 `self.profiles.load_all()` 计算后传给窗口；
   - 取消勾选时，如果有其他方案引用这个规则集，调用一次 `ask_confirmation`；用户取消时，勾选状态恢复。
   - UXS-06 完成后，这个复选框移到“规则集设置…”对话框中。
2. 在 `ruleset_row` 中原来那个复选框的位置，新增 `self.use_in_run_check`，新键 `rules.use_in_run`：“用于本次转换”/“用於本次轉換”/“Use in this conversion”。
   - `RuleManagerDialog.__init__` 增加参数 `run_ruleset_ids: tuple[str, ...] = ()`，由 `edit_rules()` 传入 `self.active.ruleset_ids`；
   - `_ruleset_changed()` 和 `_populate_rulesets()` 根据当前规则集是否在 `self._run_ruleset_ids` 中，设置勾选状态；
   - 勾选状态变化时，只更新内存中的 `self._run_ruleset_ids`。
3. `RuleWindowResult` 增加字段 `run_ruleset_ids: tuple[str, ...] | None = None`，由 `_apply()` 填入。
4. `edit_rules()`：
   - `result.run_ruleset_ids` 不为 None 时，用它代替 `... + [selected_id]`，并对其中的重命名做映射；为 None 时保持旧行为，兼容旧的调用方；
   - 只有“这次新加入、并且方案已保存”的规则集才调用 `ask_confirmation`，每次保存最多问一次；如果有多个新加入的规则集，在同一个问题中一起列出；
   - 删除 `:353-357` 的 `QMessageBox.information(... settings.ruleset_session_only ...)`。如果这个键没有其他引用，从三份 JSON 中删除。
5. “本次生效”筛选和 `_rule_is_active` 改为根据 `self._run_ruleset_ids` 判断。
6. RULE-05 中的 `_run_candidates()` 同样改用 `self._run_ruleset_ids`。

**测试**
- `tests/integration/test_ruleset_persistence.py::test_viewing_other_ruleset_does_not_add_it_to_run`：
  - 使用 `RuleWindowResult("mine", (RuleSet("mine"),), run_ruleset_ids=("default",))`；
  - 断言 `settings.active.ruleset_ids == ("default",)`，并且没有调用问题框。
- 更新 `test_saved_profile_rejection_keeps_change_session_only`：
  - 传入 `run_ruleset_ids=("default", "mine")`；
  - 断言 `information_messages == []`，且 `settings.active.ruleset_ids == ("default", "mine")`。
- `tests/unit/test_rules_window.py::test_use_in_run_checkbox_tracks_selected_ruleset`：切换规则集时，勾选状态跟着变化；`_apply()` 的结果中带有正确的 tuple。
- `tests/integration/test_ruleset_persistence.py::test_disabling_shared_ruleset_asks_when_other_profiles_reference_it`：用户取消时，文件不被写入。
- `tests/unit/test_i18n.py`：`rules.ruleset_enabled` 的三种语言文案中，都不含“本次”和 “this run”。

**验收标准**
- [ ] 只是切换下拉框浏览另一个规则集再保存，本次引用不变。
- [ ] 一次保存最多出现 1 个模态框。
- [ ] 全局开关的文案中不含“本次”；有其他方案引用时，取消勾选需要确认。
- [ ] R-01（清空默认规则集）和重命名相关的现有用例全部通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/integration/test_ruleset_persistence.py tests/unit/test_rules_window.py tests/unit/test_profiles_m3.py tests/unit/test_i18n.py -q \
  && mise exec -- uv run python docs/reviews/2026-09-28/scripts/rules/rule11_ruleset_enabled_is_global.py
```

**不要做**
- 未经用户确认，不写入已保存的方案。
- 不删除 `RuleSet.enabled` 字段，不改 schema。
- 不把规则集的勾选状态持久化到偏好设置中。

---

## RULE-12（design，P2）规则集无法删除

**依赖**：RULE-11。

**位置**：`ui/rules_window.py:501-510`。规则集这一行只有“新建”和“重命名”，整个文件中都没有删除规则集的入口；用 `grep -n -i delete` 查找，只命中删除单条规则的代码。

**现状**：不用的规则集只能到文件系统里手动删除。删除之后，引用它的方案还会反复提示 `rulesets_missing`。

**修改方法**
1. 增加“删除规则集…”按钮（UXS-06 完成后放进“更多…”菜单）：
   - 当前规则集是 `default` 时，按钮禁用，tooltip 用新键 `rules.cannot_delete_default` 说明原因；
   - 点击后弹出确认框，列出引用这个规则集的方案名。新键 `rules.delete_ruleset_confirm`：“删除规则集 {name}？以下方案将不再引用它：{profiles}”。
2. 用户确认后，`RuleWindowResult` 增加字段 `deleted: tuple[str, ...] = ()`。`edit_rules()` 的处理顺序：
   - 先仿照 `_replace_ruleset_references` 写一个删除版的函数，从各方案中移除对该规则集的引用，然后保存这些方案；
   - 从 `self.active.ruleset_ids` 中移除；
   - 最后删除规则集文件（用 `RuleStore` 中已有的删除方法；如果没有，就新增 `RuleStore.delete(id)`，内部用 `Path.unlink(missing_ok=True)`）。
3. 在窗口中，删除只是草稿层面的操作，要等点击“保存”后才真正执行。取消窗口时，不删除任何东西。

**测试**
- `tests/integration/test_ruleset_persistence.py::test_delete_ruleset_removes_profile_references_and_file`：删除后文件不存在，所有方案的 `ruleset_ids` 中都没有它，也不出现 `rulesets_missing` 提示。
- `tests/unit/test_rules_window.py::test_default_ruleset_cannot_be_deleted`。
- `tests/unit/test_rules_window.py::test_cancel_after_delete_keeps_ruleset`。

**验收标准**
- [ ] 删除后没有悬空的引用。
- [ ] `default` 规则集不能删除，并且说明了原因。
- [ ] 取消窗口时，不删除任何文件。

**验证命令**
```sh
mise exec -- uv run pytest tests/integration/test_ruleset_persistence.py tests/unit/test_rules_window.py tests/unit/test_profile_window.py -q
```

**不要做**：不做回收站；不修改方案文件的格式；不实现 C-02。

---

## RULE-13（bug，P3）列表被搜索过滤后，输入框为空时的“词典检查”检查的是另一条规则

**位置**：`ui/rules_window.py:1653-1656`，`_inspect()`：
```python
row = self.table.currentRow()
if 0 <= row < len(self.rules):
    text = self.rules[row].source
```
这里用可见行号去索引完整的规则列表。

**现状**（`scripts/rules/rule13_inspect_filtered_row.py`）
```
visible rows: ['r-b'] | editor shows: 乙方
inspector opened for: 甲方 (expected 乙方)
```

**修改方法**：改用已有的辅助函数，把可见行号转换成规则下标：
```python
index = self._rule_index_at_row(self.table.currentRow())
if 0 <= index < len(self.rules):
    text = self.rules[index].source
```

**测试**：`tests/unit/test_rules_window.py::test_inspect_without_input_uses_the_visible_selected_rule`，断言 `seen["text"] == "乙方"`。

**验收标准**
- [ ] 过滤和未过滤两种情况下，检查的都是当前选中的规则。
- [ ] 脚本输出 `inspector opened for: 乙方`。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py -q -k inspect
```

**不要做**：不改变输入框有内容时的行为。

---

## RULE-14（design，P3）属于其他书或方案的规则，在表格里仍显示为“当前书/当前方案”；没有“改绑到当前书”的入口

**位置**
- `ui/rules_window.py:1148`、`ui/rules_window.py:1271`：`self._labels.get(f"scope_{rule.scope}")`，不管归属是谁，永远显示“当前书/当前方案”。
- `ui/rules_window.py:1364`，`_rule_from_form()`：范围不变时保留原来的归属。这是 R-02 要求的正确行为，但没有提供显式改绑的入口。
- `sigil/adapter.py:87-102`，`book_fingerprint()`：把所有 `dc:identifier` 拼在一起做哈希。

**现状**（`scripts/rules/rule14_book_owner_display.py`）
```
fingerprint changes after adding an ISBN identifier: 6cf6c6af0339 -> 16f1289eb285
table scope column: 当前书 | activity: 方案或书籍归属不匹配
after update with scope unchanged -> owner still old book: True
```
给书加一个 ISBN，原来的书籍规则就全部失效，但表格上仍然写着“当前书”。

**修改方法**
1. 在表格和详情中，如果规则的归属与当前书或方案不一致，改为显示新键 `rules.scope_book_other`（“其他书籍”）或 `rules.scope_profile_other`（“其他方案”），三种语言都要有。
2. 归属不一致时，编辑区显示按钮 `rules.rebind_owner`（“改绑到当前书/当前方案”）：
   - 点击后，把 `book_fingerprint` 或 `profile_id` 显式设为当前值，并更新 `updated_at`；
   - 当前没有归属信息（例如没有打开书）时，按钮禁用。
3. 规则窗口顶部显示提示 `rules.foreign_owner_count`：“有 {count} 条规则属于其他书籍或方案”。点击后，活动筛选切换到“本次不生效”。

**测试**
- `tests/unit/test_rules_window.py::test_foreign_book_rule_is_labelled_other_book`。
- `tests/unit/test_rules_window.py::test_rebind_button_binds_current_book_only_on_click`。

**验收标准**
- [ ] 其他书的规则不再被标成“当前书”。
- [ ] 只有点击按钮才改绑。
- [ ] R-02 的回归测试继续通过。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_rules_window.py -q
```

**不要做**
- 本批不改 `book_fingerprint()` 算法。改了会让现有的书籍规则全部失配，如果要改，需要单独制定迁移方案。
- 不自动改绑。

---

## RULE-15（design，P2）能匹配空串的正则通过了保存时的校验，但书中遇到空括号 `「」` 时，会中止整次分析

**位置**
- `rules/validators.py:177-190`，`_validate_regular_expression()`：只用 `""` 和一段固定的样例文本来测试。
- `rules/matching.py:159-162`，`collect_matches()`：运行时遇到零长度匹配就抛出 `RuleExecutionError`。

**现状**（`scripts/rules/rule15_zero_width_and_entities.py`）
```
validation of (?<=「)[^」]*: passes
runtime on '他说「」然后': RuleExecutionError rule z: zero-length regular-expression match at offset 3 is not allowed
```

**期望**：`docs/rule-format.md:21` 写的是 “rejects zero-length matches”，应当拒绝的是这一次匹配，而不是整次分析。

**修改方法**（按 README 的 D3）
1. `collect_matches()` 中，遇到 `found.start() == found.end()` 时：
   - 执行 `budget.zero_width_skips[rule.id] = budget.zero_width_skips.get(rule.id, 0) + 1`；
   - 执行 `cursor = found.start() + 1`，然后 `continue`，不抛异常。
   - `RegexBudget.__init__` 中新增 `self.zero_width_skips: dict[str, int] = {}`。
2. 分析结束后，对有跳过记录的规则追加一条诊断 `REGEX_ZERO_WIDTH_SKIPPED`，内容只包含规则 ID 和次数，不包含正文：
   - 诊断的添加位置，放在 converter 或 workflow 收集诊断的地方（与现有 Diagnostic 的添加方式一致）；
   - 沙箱 trace 显示新键 `rules.zero_width_skipped`。
3. 保存时的校验保持不变：能匹配空串 `""` 的模式，继续拒绝保存。
4. 更新 `docs/rule-format.md:20-27` 和三种语言的 `resources/rule-guide.md`。

**测试**（`tests/unit/test_regex_rules.py`）
- `test_zero_width_runtime_match_is_skipped_not_fatal`：规则 `(?<=「)[^」]*` 作用于 `他说「」然后「好」`，只替换 `好`，诊断计数为 1。
- 现有的 `test_zero_width_pattern_and_bad_template_are_rejected` 保持通过。

**验收标准**
- [ ] 不再因为零长度匹配中止分析。
- [ ] 时间预算和命中预算仍然有效。
- [ ] 诊断和日志中不含原文。

**验证命令**
```sh
mise exec -- uv run pytest tests/unit/test_regex_rules.py -q
```

**不要做**：不放宽保存时的校验；不把零长度匹配当作插入点来替换。

---

## RULE-16 → 已合并到 [02-performance.md 的 PERF-01](02-performance.md)

## 其他观察（证据较弱，暂不单列）

- **实体导致沙箱和书籍结果不一致。** 规则 `A&B` 在书中的 `A&amp;B` 处不会命中，但纯文本沙箱会显示命中。可以在 `rule-guide.md` 中补一句：“含有 & < > 的规则无法匹配实体化的文本”。
- **`rules/precedence.py:55-59` 的 `precedence_key()` 没有被调用，而且它的 docstring 与实际排序相反。** 执行 RULE-02 时可以顺手删除（先 grep 确认没有引用）。
- **TSV 导出按规则 ID（随机 UUID）排序**，与界面上的列表顺序不同，不便于人工编辑。
