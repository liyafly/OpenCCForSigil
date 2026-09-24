# 第三轮审查：修改规格（按条目逐项执行）

日期：2026-09-24。基线：`main` @ `4706a92`（第二轮基线 `263f657` 之后又有 21 个提交）。

这份文档写给负责实现的模型。每一条都是独立的任务，写明了改哪个文件、怎么改、加什么测试、用什么命令验证。**按第 1 节的规则执行，按第 2 节的批次顺序执行。**

编号规则：
- `A-xx`：非 UI 逻辑（转换、分词、规则、写回）。
- `B-xx`：UI 缺陷（按了会出错的）。
- `C-xx`：UI 体验改进（不出错，但难用）。
- `D-xx`：性能。
- `E-xx`：发布与打包，见 `02-release-plan.md`。
- `R-xx`：第二轮条目；`N-xx`：复审第二轮修复时新发现的问题。都在第 7 节。

复现脚本在 `scripts/` 下，用法见 `README.md`。

---

## 1. 执行规则（每一条都必须遵守）

1. **一次只做一条。** 做完一条、测试通过、提交之后，再开始下一条。不要把多条混在一个提交里，除非第 2 节的批次表明确把它们放在一起。
2. **先复现，再修改。** 如果条目给了复现脚本，先运行脚本，确认看到的输出和"当前输出"一致。不一致就停下来，在提交说明里写清楚你看到了什么，不要猜着改。
3. **先写测试，确认测试失败，再改代码，确认测试通过。** 测试必须在不改代码时失败。不能只断言"没有抛异常"。
4. **只改条目里写的地方。** "不要"一栏列出的事情一律不做。发现条目以外的问题，记在提交说明里，不要顺手修。
5. **行号只是参考。** 代码可能已经移动。用条目里给的函数名或代码片段定位。
6. **每条做完都运行：**
   ```sh
   mise exec -- uv run pytest -q
   mise exec -- ruff check .
   ```
   两条命令都必须通过。每个批次结束后再运行一次 `make check`。
7. **已有测试失败时：**
   - 如果失败的原因正是本条要改变的行为（条目里会写明是哪个测试），按条目要求修改该测试的期望值。
   - 其他任何失败：停下，不要改测试去迁就代码。
8. **提交信息**用英文，格式与仓库历史一致：`fix: ...`、`perf: ...`、`ui: ...`、`test: ...`。第 2 节给出了每个批次建议的提交主题。
9. **界面文字**一律走 `resources/i18n/{en,zh-Hans,zh-Hant}.json`，三个文件同时加键，不要在 Python 里写中文或英文字面量。加键后运行 `mise exec -- uv run pytest tests/unit/test_i18n.py -q`。
10. **UI 测试**用 `tests/support/fake_qt.py`。假 Qt 缺少某个方法时，在 `fake_qt.py` 里按真实 Qt 的行为补一个最小实现，并在同一个提交里提交。

---

## 2. 批次顺序

| 批次 | 条目 | 建议提交主题 | 依赖 |
| --- | --- | --- | --- |
| 1 | A-01 | `fix: find raw-text closing tags without lowercasing the source` | 无 |
| 1 | A-04 | `fix: keep run successful when post-commit bookkeeping fails` | 无 |
| 1 | A-03 | `perf: skip and index quotation entity scanning` | 无 |
| 1 | B-01、B-02 | `ui: stop re-checking Jieba and stop the probe timer` | 无 |
| 1 | B-03 | `ui: make Esc close the no-change result` | 无 |
| 1 | N-01 | `fix: report the Jieba probe error in self-test` | 无 |
| 1 | N-02 | `fix: keep the saved pivot chain when the settings dialog opens` | 无 |
| 1 | N-03 | `fix: compare profiles with panel defaults filled in` | 无 |
| 2 | A-02 + D-01 | `fix: diff equal-length output by position and keep phrases whole` | 无（两条改同一个函数，必须一起做） |
| 2 | A-06 | `fix: protect prefixed MathML and SVG elements` | 无 |
| 2 | A-07 | `fix: skip CDATA and comments inside script and style` | A-01 |
| 2 | A-08 | `fix: let protect rules win over earlier overlapping rules` | 无 |
| 2 | A-09 | `fix: give imported rules fresh ids on collision` | 无 |
| 3 | A-05 | `fix: verify planned spans and protected content` | 批次 2 全部完成 |
| 4 | D-02、B-04 | `perf: format preview rows lazily and stop resizing headers` | 无 |
| 4 | D-03 | `perf: build absolute changes once` | 无 |
| 4 | D-04 | `perf: compute classifier alignments only when needed` | A-02 + D-01 |
| 4 | D-05 | `perf: probe Jieba with one configuration` | B-01、B-02 |
| 4 | D-06 | `perf: hash the payload tree once per process` | 无 |
| 4 | D-07 | `test: share backends across controller integration tests` | D-05、D-06 |
| 5 | B-05 至 B-12 | 每条一个提交，`ui: ...` | 批次 4 |
| 6 | C-01 至 C-17 | 每条一个提交，`ui: ...` | 批次 5 |
| 7 | A-10 至 A-15、D-08 | 每条一个提交 | 无 |
| 8 | N-04、N-06 至 N-09 | 每条一个提交 | N-07 依赖 A-02 + D-01 |
| 9 | E-xx | 见 `02-release-plan.md` | 批次 1 至 6 |

批次 1 的各项是"会卡死 / 会丢改动 / 用户取消不掉"一类问题，必须最先完成。批次 1 做完后，就可以在 Sigil 里做一轮实测（见 `02-release-plan.md` 第 4 节）。

---

## 3. 非 UI 逻辑（A）

### A-01 标题里出现 `İ`（U+0130）时分词器死循环（P1，已复现）

**位置**：`plugin/OpenCCForSigil/document/tokenizer.py`，函数 `_find_closing_tag`（约第 291 行）：

```python
def _find_closing_tag(source: str, start: int, name: str) -> int:
    return source.lower().find("</" + name, start)
```

**原因**：`"İ".lower()` 是 2 个字符（`i` + U+0307）。`source.lower()` 比 `source` 长，返回的偏移在原串里是错的。`tokenize_xhtml`（约第 133-140 行）拿这个偏移判断"不是结束标签"，于是 `continue`，下一轮又得到同一个偏移，永远不前进。分词在工作线程里执行，取消按钮也无效，只能强制结束 Sigil。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a01_tokenizer_hang.py
```
- 当前输出：5 秒后打印 `Timeout (0:00:05)!` 和堆栈。
- 期望输出：`OK: 1 targets in 0.00x s`（数字可以不同，但要立即返回）。

**修改步骤**：
1. 在 `tokenizer.py` 顶部（已有 `import re` 就复用）加一个缓存：
   ```python
   _CLOSING_TAG_PATTERNS: dict[str, "re.Pattern[str]"] = {}
   ```
2. 把 `_find_closing_tag` 改成在原串上做不区分大小写的正则查找：
   ```python
   def _find_closing_tag(source: str, start: int, name: str) -> int:
       pattern = _CLOSING_TAG_PATTERNS.get(name)
       if pattern is None:
           pattern = re.compile("</" + re.escape(name), re.IGNORECASE)
           _CLOSING_TAG_PATTERNS[name] = pattern
       match = pattern.search(source, start)
       return match.start() if match else -1
   ```
3. 检查同一文件的 `_is_closing_tag_at`，如果它也用了 `source.lower()` 或 `.lower()` 后的偏移，同样改成在原串上比较（例如 `source[start:start + len(name) + 2].lower() == "</" + name`，这里只对切片小写化，偏移不受影响）。
4. 在整个 `document/` 目录里搜索 `.lower().find(` 和 `.lower().index(`，凡是拿结果当原串偏移用的，都按同样方法改。

**测试**：在 `tests/unit/test_xml_targets.py`（或新建 `tests/unit/test_tokenizer_unicode.py`）加参数化测试：
- 三种位置：`İ` 在 `<title>` 里、在 `<p>` 正文里、在 `title="İ"` 属性值里；每种后面都跟 `<style>p{}</style>` 或 `<script>var a=1;</script>`。
- 断言 1：`tokenize_xhtml(source)` 返回（用 `pytest` 的 `timeout` 不可用，就在测试里记 `time.perf_counter()`，断言小于 1 秒）。
- 断言 2：`<style>` 之后 `<p>汉字</p>` 里的"汉字"仍然是一个 target（`[t.source_text for t in doc.targets]` 包含 `"汉字"`）。
- 断言 3：`<style>` 内容不是 target。

**验证**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a01_tokenizer_hang.py
mise exec -- uv run pytest tests/unit -q -k "tokenizer or xml_targets"
```

**不要**：不要改 `_raw_protected_name` 的逻辑；不要在这里处理 CDATA（那是 A-07）。

---

### A-02 一条 OpenCC 词组映射被拆成几条可以分别接受的变更（P1，已复现）

> 与 D-01 改同一个函数 `bounded_opcodes`，**必须在同一个提交里一起做**。先读完 D-01 再动手。

**位置**：
- `plugin/OpenCCForSigil/core/diff.py`，函数 `bounded_opcodes`（约第 35-74 行）。
- 调用方：`core/converter.py` 的 `convert`（约第 78 行 `for tag, i1, i2, j1, j2 in bounded_opcodes(text, target):`），以及 `core/classifier.py` 的 `classify_conversion`（约第 66-70 行）。两处都通过 `bounded_opcodes` 取对齐，所以只改 `bounded_opcodes` 就能保持两边一致。

**原因**：`SequenceMatcher` 按字符对齐，会把一个词组映射拆开，还会跨词组对齐同一个字。每个非 equal 的 opcode 变成一条独立的 `TokenChange`，用户可以只接受其中一条，写出既不是原文也不是 OpenCC 结果的文字。verify 只检查结构，拦不住。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a02_phrase_split.py
```
当前输出（s2twp）：
```text
打印机 → 两条：打→'' 和 机→表機；只接受第一条得到 <p>印机</p>，只接受第二条得到 <p>打印表機</p>
激光打印机坏了 → 两条：激光打→雷射、机坏→表機壞；只接受第一条得到 <p>雷射印机坏了</p>
鼠标和内存 → 三条：''→滑、标→''、内存→記憶體；只接受第一条得到 <p>滑鼠标和内存</p>
```
期望输出：三个输入各自只有 **1 条**变更，只接受它得到完整的 OpenCC 结果（`印表機`、`雷射印表機壞了`、`滑鼠和記憶體`）。

**修改步骤**（在 `core/diff.py` 里）：
1. 先完成 D-01 的第 1-2 步（等长快速路径）。等长输出不经过下面的合并。
2. 新增函数 `_merge_close_changes(opcodes, source, target)`，规则：
   - 依次扫描 opcode。遇到非 equal 的 opcode A，如果紧跟一个长度 **≤ 1** 的 equal 段 E，再紧跟一个非 equal 的 opcode B，就把 A、E、B 合并成一个 `("replace", A.i1, B.i2, A.j1, B.j2)`，并继续尝试和后面的合并。
   - 合并后的 opcode 必须满足：`source[i1:i2]` 和 `target[j1:j2]` 就是对应的原始切片（按坐标取，不要拼字符串）。
   - 纯 equal 段长度 ≥ 2 的地方不合并。
3. 在 `bounded_opcodes` 的非等长分支里，`_coalesce_opcodes(opcodes)` 之后调用 `_merge_close_changes`，返回合并后的结果。
4. `bounded_opcodes` 的文档字符串补一句：非等长输出时，被单个相同字符隔开的变更会合并，避免把一个词组拆开。

**测试**：在 `tests/unit/test_converter_diff.py` 加：
1. `test_regional_phrase_is_one_change`：参数化 `("打印机", "印表機")`、`("激光打印机坏了", "雷射印表機壞了")`、`("鼠标和内存", "滑鼠和記憶體")`。对每对，断言 `bounded_opcodes(s, t)` 中非 equal 的 opcode 只有 1 个。
2. `test_partial_acceptance_never_mixes_phrase`：用真实后端（参考同目录其他测试怎样构造 `OpenCCBackend("s2twp")`；如果单元测试里没有真实后端，就放到 `tests/integration/test_rules_transform_workflow.py`），对 `<p>打印机</p>` 规划，枚举所有变更子集（`itertools` 的组合），用 `core.staging.apply_changes` 写出，断言每个结果的段落文本要么是 `打印机`，要么是 `印表機`。
3. `test_opcodes_partition_both_strings`：对上面的输入和几组随机字符串，断言 opcode 首尾相接、完全覆盖 `source` 和 `target`，并且把非 equal 段替换后能还原出 `target`。

**已知会变的测试**：`tests/unit/test_converter_diff.py` 中断言具体 opcode 粒度的用例，可能因为合并而改变期望。只允许修改"期望的 opcode 列表"，并在提交说明里列出改了哪些测试、为什么。其他文件的测试失败则停下。

**验证**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a02_phrase_split.py
mise exec -- uv run pytest -q
```

**不要**：不要用 `group_id` 来实现这一条。`GROUP_PARTIAL` 是在 finalize 阶段报错，用户点完"应用"才看到失败，体验更差。

---

### A-03 引号实体扫描是 O(实体数 × 标签数)，而且在 `keep` 模式下也执行（P1，已复现）

**位置**：`plugin/OpenCCForSigil/core/planner.py`
- 函数 `_feed_quotation_entities`（约第 229-238 行）：对每个实体匹配，都用 `any(...)` 线性扫描全部 `ignored_ranges`。
- `ignored_ranges` 由 `_ignored_quotation_ranges`（约第 208-226 行）生成，每个标签都是一个区间。
- 两个调用点（约第 109 行、第 153 行）不看 `request.quotation_mode`。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a03_entity_scan_perf.py
```
当前输出（本机实测）：4000 段 2.3 s、8000 段 8.7 s、16000 段 33.9 s（规模翻倍，时间约翻 4 倍）。期望：16000 段低于 1 s。

**修改步骤**：
1. 在两个调用点外面加条件：`request.quotation_mode == "keep"` 时不调用 `_feed_quotation_entities`。这样做是安全的：`transforms/quotations.py` 里 `QuotationPairer.feed` 的第一行就是 `if self.mode == "keep" or not text: return ...`，keep 模式下喂实体本来就不改变任何状态。
2. 让 `_ignored_quotation_ranges` 返回**排好序、合并过重叠**的区间，外加一个起点列表：
   ```python
   def _ignored_quotation_ranges(source, tags):
       ...  # 原逻辑收集 ranges
       ranges.sort()
       merged = []
       for start, end in ranges:
           if merged and start <= merged[-1][1]:
               merged[-1] = (merged[-1][0], max(merged[-1][1], end))
           else:
               merged.append((start, end))
       return tuple(merged)
   ```
3. `_feed_quotation_entities` 里用 `bisect` 查询：
   ```python
   starts = [start for start, _end in ignored_ranges]   # 在调用方算一次，作为参数传入
   index = bisect.bisect_right(starts, position) - 1
   ignored = index >= 0 and position < ignored_ranges[index][1]
   ```
   `starts` 列表每个文件只算一次，不要在每次调用时重算。

**测试**：在 `tests/unit/test_quotation_pairing.py` 加：
1. `test_keep_mode_skips_entity_scan`：用 `monkeypatch` 把 `core.planner._feed_quotation_entities` 换成计数函数，`quotation_mode="keep"` 规划一个含 `&#12288;` 的文件，断言调用次数为 0。
2. `test_entity_scan_is_not_quadratic`：非 keep 模式（例如 `"corner"`），16000 段 `<p>&#12288;第{i}段。</p>`，断言规划耗时 < 3 s。
3. 已有的实体引号配对测试（R-11 相关）必须仍然通过。

**验证**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a03_entity_scan_perf.py
mise exec -- uv run pytest tests/unit/test_quotation_pairing.py -q
```

**不要**：不要改 `QuotationPairer` 的配对规则。

---

### A-04 全部写回成功后，日志或进度窗口出错会让整次转换被 Sigil 丢弃（P1，已复现）

**位置**：`plugin/OpenCCForSigil/app/controller.py`，`run` 方法里 commit 成功之后的一段（约第 494-526 行），从 `finally: post_preview_progress.close()` 到 `return 0`。异常会落进约第 572-603 行的 `except Exception`，因为 `committed` 非空，显示 `partial_failure` 然后 `raise`，`plugin.py` 返回 2。

**为什么严重**：规范 `OpenCCForSigil_Engineering_Spec.md` 第 185 行：返回非 0 时 **Sigil 丢弃全部修改**。所以一个日志写失败（例如磁盘满）就让用户整本书的转换白做，而界面还说"已写入 N 个文件"。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a04_post_commit_log_failure.py
```
- 当前输出：`return code 2 writes ['a', 'b'] status partial_failure`
- 期望输出：`return code 0 writes ['a', 'b'] status success`

**修改步骤**：
1. 在 `controller.py` 里加一个私有方法：
   ```python
   def _best_effort(self, label, action, default=None):
       """Run post-commit bookkeeping; never let it fail a committed run."""
       try:
           return action()
       except Exception as error:  # noqa: BLE001 - bookkeeping must not undo a commit
           try:
               self.logger.exception(f"post_commit_{label}_failed", error)
           except Exception:
               print(f"OpenCCForSigil: {label} failed after commit: {error}", file=sys.stderr)
           return default
   ```
2. commit 成功之后的每一步都改用 `_best_effort` 包起来：
   - `post_preview_progress.close()` → `self._best_effort("progress_close", post_preview_progress.close)`（它在 `finally` 里，只在 commit 已成功的路径上替换；commit 失败的路径保持原样）。
   - `self.logger.event("commit_completed", ...)`
   - `self.logger.summary(...)`
   - `report_text = self._record_history(...)` → `report_text = self._best_effort("history", lambda: self._record_history(...), default=None)`
3. `self.session.complete()` 放在这些步骤**之前**，并保持不包裹（它只改内存状态）。
4. `_show_result_safely(...)` 已经是安全的，保持不变。最后 `return 0`。
5. 修改 `except Exception` 分支里 `committed` 非空时的文案：因为这时一定返回非 0，Sigil 会丢弃全部修改。在三个 i18n 文件里把 `result.partial` 改成表达"写回过程中出错，Sigil 将放弃本次所有修改，书保持原样"。中文参考："写回在 {failed_file} 处出错。Sigil 会放弃本次全部修改，书保持转换前的内容。"英文、繁中同步。**这个行为需要在 Sigil 里实测确认**（`02-release-plan.md` 第 4 节第 3 项），实测结果不同就回来改文案。

**要修改的已有测试**：`tests/integration/test_error_reporting.py::test_post_write_progress_close_failure_uses_adapter_commit_record` 现在断言的正是错误行为（进度关闭失败 → 整次作废）。把它改为断言：返回 0、结果状态 `success`、`files_changed == 2`、日志里有 `post_commit_progress_close_failed` 事件。

**新增测试**（同一文件）：
- `test_summary_failure_after_commit_still_succeeds`：照复现脚本的做法让 `SessionLogger.summary` 在 `status == "success"` 时抛 `OSError`，断言 `plugin.run(book) == 0`、`book.writes == ["a", "b"]`、`results[-1]["status"] == "success"`。
- `test_history_failure_after_commit_still_succeeds`：让 `_record_history` 抛异常，断言同上，且 `report_text` 为 `None`。

**验证**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a04_post_commit_log_failure.py
mise exec -- uv run pytest tests/integration/test_error_reporting.py -q
```

**不要**：不要包裹 `WorkflowCommitError` 路径（真正的写入失败必须仍然返回非 0）。不要吞掉 `UserCancelled`。

---

### A-05 verifier 没有检查"只改了计划内的地方"和受保护内容（P2，已复现，故障注入）

> 依赖：批次 2 全部完成后再做。加强的 verifier 会把 A-06、A-07 那类问题当成错误拦下，先修掉它们，避免这一条引入大量测试失败。

**位置**：`plugin/OpenCCForSigil/core/verifier.py`，`verify_staged_file`（约第 19-54 行）。现在只做三件事：重放变更比对结果；比对标签名、属性名、引号风格；比对 `id/href/src/class/style` 的值。规范 §9.6、§27 要求的"变更只落在计划区间内"和"受保护块不变"没有实现。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a05_verifier_gap.py
```
- 当前输出：`passed: True []`（脚本手工注入了对 `epub:type`、`role`、`<pre>`、注释、`<script>` 的修改）
- 期望输出：`passed: False`，诊断码包含 `UNPLANNED_CHANGE` 和 `PROTECTED_ATTRIBUTE_CHANGED`。

**修改步骤**：
1. **每条变更必须落在某个 target 内。** 对 `staged.plan.changes` 的每条变更，检查存在 `original_document.targets` 中的某个 target，满足 `target.source_start <= change.span.start` 且 `change.span.end <= target.source_end`（字段名以 `TextTarget` 实际定义为准）。不满足就加诊断 `UNPLANNED_CHANGE`（ERROR），消息里带文件 id 和偏移。
2. **变更集合必须等于计划允许的区间。** 如果 `plan.allowed_spans` 非空，检查每条变更的 span 都在 `allowed_spans` 里；不在就加 `UNPLANNED_CHANGE`。
3. **计划外的原文必须原样保留。** 把原文按变更 span 切开：所有不在任何变更 span 内的片段，在结果里必须按顺序逐段相同。实现方法：遍历排好序的变更，维护原文游标和结果游标，比较每段"两次变更之间的原文"是否等于结果中对应位置的文字。不同就加 `UNPLANNED_CHANGE`。
4. **受保护属性。** 找到现有的"受保护属性签名"（比较 `id/href/src/class/style` 的那段代码），把 `epub:type`、`role`、`xmlns` 以及所有 `xmlns:*`、所有 `aria-*`（`aria-label` 除外，它是可转换的）加进去。不同就加 `PROTECTED_ATTRIBUTE_CHANGED`。
5. 三个新诊断码加到定义诊断码的地方（在 `core/models.py` 或 `core/diagnostics.py` 里搜索现有的码，例如 `grep -rn "PROTECTED_\|_CHANGED\"" plugin/OpenCCForSigil/core`），并在三个 i18n 文件里加用户可读的说明。

**测试**：新建 `tests/unit/test_verifier_invariants.py`，把复现脚本改写成测试：
- 注入对 `epub:type` 的修改 → 断言有 `PROTECTED_ATTRIBUTE_CHANGED`。
- 注入落在 `<pre>`、注释、`<script>` 里的修改 → 断言有 `UNPLANNED_CHANGE`。
- 正常规划的计划（不注入）→ 断言 `passed is True`，诊断为空。
- 再对 `tests/integration/` 里现有的转换流程全部跑一遍，确认没有误报。

**验证**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a05_verifier_gap.py
mise exec -- uv run pytest -q
```

**不要**：不要在这一条引入新的 XML 解析库依赖（lxml 等）。第 3 步的逐段比较已经足够兜住 A-06、A-07 这类问题。

---

### A-06 带命名空间前缀的 `<m:math>`、`<svg:svg>` 没有被保护（P2，已复现）

**位置**：
- `plugin/OpenCCForSigil/document/tokenizer.py`：`_is_protected`、`_element_is_writable`（约第 263-281 行）用 `name == "svg"`、`name == "math"` 比较；标签名来自约第 348 行 `name = source[name_start:cursor].lower()`，是带前缀的限定名，例如 `m:math`。
- `plugin/OpenCCForSigil/core/planner.py`：`_ignored_quotation_ranges` 里的 `protected_names` 也按限定名比较。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a06_prefixed_namespaces.py
```
- 当前输出：`<m:mtext>數學漢字</m:mtext>`、`<svg:text>圖形漢字</svg:text>`（被转换了）
- 期望输出：`数学汉字`、`图形汉字` 保持不变，`<p>正文</p>` 变成 `<p>正文</p>`（"正文"繁简相同）。

**修改步骤**：
1. 在 `tokenizer.py` 加：
   ```python
   def _local_name(name: str) -> str:
       return name.rsplit(":", 1)[-1]
   ```
2. `_is_protected`、`_element_is_writable` 里所有和 `"svg"`、`"math"` 的比较改成 `_local_name(name) == "svg"` / `"math"`。`options.protected_elements` 的判断也改成同时检查 `name` 和 `_local_name(name)`（任一命中即保护）。
3. `_raw_protected_name` 里 `{"script", "style"}` 的判断同样用 `_local_name`。
4. `planner.py` 的 `_ignored_quotation_ranges`：`tag.name not in protected_names` 改成 `tag.name.rsplit(":", 1)[-1] not in protected_names`，入栈和出栈都用本地名。

**测试**：在 `tests/unit/test_xml_targets.py` 加参数化用例：`<m:math><m:mtext>数学</m:mtext></m:math>`、`<svg:svg><svg:text>图形</svg:text></svg:svg>`、`<math xmlns="...">`（默认命名空间）。默认选项下断言这些文字都不在 `targets` 里。再加一个开启 `svg_text=True` 的用例，断言 `svg:text` 里的文字在 targets 里。

**验证**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a06_prefixed_namespaces.py
mise exec -- uv run pytest tests/unit/test_xml_targets.py -q
```

**不要**：不要实现完整的 `xmlns` 声明跟踪，本地名判断就够了。

---

### A-07 `<script>` 的 CDATA 里出现 `</script>` 时，后面的代码被转换（P2，已复现）

> 依赖 A-01（同一个函数）。

**位置**：`plugin/OpenCCForSigil/document/tokenizer.py`，`tokenize_xhtml` 主循环里 raw-text 分支（约第 133-140 行）和 `_find_closing_tag`。raw 模式直接查找 `</script`，没有跳过 `<![CDATA[ … ]]>` 和 `<!-- … -->`。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a07_script_cdata.py
```
- 当前输出：`var msg = "漢字軟件"`（脚本被改了），正文 `<p>漢字</p>`。
- 期望输出：`var msg = "汉字软件"` 不变，正文 `<p>漢字</p>`。

**修改步骤**：把 A-01 改好的 `_find_closing_tag` 再扩展一次：从 `start` 开始循环，每一步找最近的三种位置——`<![CDATA[`、`<!--`、`</name`（不区分大小写）：
- 最近的是 `<![CDATA[`：跳到它之后第一个 `]]>` 的末尾（找不到就返回 -1），继续循环；
- 最近的是 `<!--`：跳到之后第一个 `-->` 的末尾（找不到就返回 -1），继续循环；
- 最近的是 `</name`：返回它的位置；
- 都没有：返回 -1。

**测试**（`tests/unit/test_xml_targets.py`）：
- `<script>` 和 `<style>` 各一例：CDATA 或注释里含 `</script>` / `</style>` 和汉字。断言这些汉字都不是 target，并且结束标签之后 `<p>汉字</p>` 里的"汉字"仍是 target。
- A-01 的 `İ` 用例必须仍然通过。

**验证**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a07_script_cdata.py
mise exec -- uv run pytest tests/unit -q -k "xml_targets or tokenizer"
```

---

### A-08 保护规则被一条起点更早、与它重叠的 exact 规则抢先（P2，已复现）

**位置**：`plugin/OpenCCForSigil/rules/compiled.py`，`lock_spans_compiled`（约第 62-79 行）。从左到右贪心匹配，只在同一起点上比较优先级。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a08_protect_overlap.py
```
- 规则：protect `乾隆`；exact `大乾 → 大幹`。输入 `<p>大乾隆帝</p>`。
- 当前输出：`<p>大幹隆帝</p>`（受保护的词被改了）
- 期望输出：`<p>大乾隆帝</p>`

**修改步骤**（两遍扫描）：
1. **第一遍，只找保护规则。** 用同样的从左到右贪心算法，但只考虑 `rule.type == "protect"` 的规则，得到保护区间列表 `protected`。
2. **第二遍，所有规则。** 按原算法扫描；当某个候选规则（非 protect）的区间 `[cursor, cursor + len(rule.source))` 与 `protected` 里的任何区间重叠时，跳过这个候选，尝试同一起点的下一个候选；都不行就 `cursor += 1`。
3. 当 `cursor` 正好落在某个保护区间的起点时，直接输出这个保护区间（`LockedSpan`，target 等于 source），`cursor` 跳到它的末尾。
4. 保持函数签名和返回类型不变。
5. 如果旧的 `rules/engine.py` 里还保留 `lock_spans`（非编译版本），并且有测试比较两者等价，两处要做同样修改。

**测试**（`tests/unit/test_rules_compiled.py`）：
- 上面的用例：断言 `lock_spans_compiled("大乾隆帝", overlay)` 中有一个 source 为 `乾隆` 的 span，并且没有 source 为 `大乾` 的 span。
- 反例：protect `乾隆`、exact `大乾 → 大幹`，输入 `大乾坤`（不含"乾隆"）→ 仍然输出 `大幹` 的 span。
- 已有的"与旧 `lock_spans` 等价"的测试：如果它包含 protect 与 exact 重叠的随机用例而开始失败，说明旧实现也有同样问题，按第 5 步同步修改后再比较。

**验证**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a08_protect_overlap.py
mise exec -- uv run pytest tests/unit/test_rules_compiled.py tests/unit/test_rules_m3.py -q
```

**同时**：在 `docs/rule-format.md` 的优先级说明里加一句"保护规则优先于任何与它重叠的转换规则，无论起点先后"。

---

### A-09 JSON 导入保留原规则 id，两个规则集同 id 不同内容后每次转换都失败（P2，已复现）

**位置**：
- `plugin/OpenCCForSigil/rules/importers.py`（约第 238-261 行）：JSON 导入原样保留 `id`。
- `plugin/OpenCCForSigil/rules/validators.py`（约第 106-113 行）：id 相同但内容不同就抛 `RuleValidationError`。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a09_duplicate_rule_id.py
```
- 当前输出：`FAIL: RuleValidationError id: rule IDs must be unique`
- 期望输出：`ok`

**修改步骤**：
1. 找到规则窗口调用 `import_rules` 之后把结果存进规则集的地方（在 `ui/rules_window.py` 里搜索 `import_rules`），以及其他所有调用 `import_rules` 的地方。
2. 在 `rules/importers.py` 加一个公共函数：
   ```python
   def reassign_colliding_ids(rules, existing_ids):
       """Return rules with a fresh id wherever the id is already used."""
   ```
   对每条规则：如果 `rule.id` 在 `existing_ids` 里，就用 `dataclasses.replace(rule, id=<新 id>)`。新 id 用 `rules/models.py` 里现有的 `_new_id()`（返回 `str(uuid.uuid4())`）。把它改名为公开的 `new_rule_id()` 并保留 `_new_id = new_rule_id` 别名，不要另写一种 id 格式。
3. `existing_ids` = 所有已保存规则集里的全部规则 id（用 `RuleStore` 读取）。导入时调用这个函数。
4. 导入预览里如果能显示"已重新分配 id 的条目数"，就加一行提示（i18n 键 `rules.import_ids_reassigned`）；不能就跳过这一步。

**测试**（`tests/unit/test_rules_m3.py`）：
- 把复现脚本改成测试：导出 A → 修改 A → 导入到 B → `validate_no_blocking_conflicts(store.load_many(["A", "B"]))` 不抛异常。
- 断言 B 中导入的规则 id 与 A 的不同，source/target 相同。
- 断言没有冲突时 id 保持不变（导入到空仓库）。

**验证**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a09_duplicate_rule_id.py
mise exec -- uv run pytest tests/unit/test_rules_m3.py tests/unit/test_rules_window.py -q
```

**不要**：不要放宽 `validators.py` 的唯一性检查。

---

### A-10 TSV/CSV/TXT 导出再导入会丢失语义（P3，已复现）

**位置**：`plugin/OpenCCForSigil/rules/exporters.py`（约第 44-72 行）。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a10_export_roundtrip.py
```
当前：已禁用的规则导入后变成启用；protect 变成 target 等于 source 的 exact；priority 变回 100；TXT 里 `Apple Inc` 被截成 `Apple`。

**修改步骤**：
1. 导出为 TSV/CSV/TXT 时，如果规则里有任何一条满足 `enabled is False`、`type == "protect"`、`priority != 100` 之一，导出前在界面上提示："这种格式不保存启用状态、类型和优先级，需要完整备份请选 JSON。"（i18n 键 `rules.export_lossy_warning`），用户确认后再导出。
2. TXT 导出时，target 含空白字符的规则跳过，并在提示中列出被跳过的条数（i18n 键 `rules.export_txt_skipped`）。
3. 不改 JSON 格式。

**测试**（`tests/unit/test_rules_window.py` 或 `test_rules_m3.py`）：导出含禁用规则的集合为 TSV 时，断言提示函数被调用一次；TXT 导出 `Apple Inc` 时，断言结果中不含这条规则，提示里跳过条数为 1。

---

### A-11 非中文 `lang` 的内容也被转换（P3，已复现）

**位置**：`plugin/OpenCCForSigil/document/tokenizer.py`（目标收集处）。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/a11_foreign_lang.py
```
当前：`<span lang="ja">国会図書館の桜</span>` → `國會図書館の桜`。期望：不变。

> 这一条改变转换范围，**先确认作者同意**（`02-release-plan.md` 第 6 节第 2 项）。未确认就跳过。

**修改步骤**：
1. 在 `TokenizerOptions` 加字段 `skip_foreign_lang: bool = True`。
2. 分词时维护一个"当前语言"栈：遇到带 `lang` 或 `xml:lang` 的开始标签就入栈该值（`xml:lang` 优先），结束时出栈；没有属性的元素继承父级。
3. 当前语言非空、且不以 `zh` 开头（不区分大小写）时，该元素内的文本不生成 target（和受保护元素一样处理）。`lang` 属性本身仍按现有逻辑处理。
4. 在设置对话框的高级选项里暂不加开关；如果要加，另开一条。

**测试**（`tests/unit/test_xml_targets.py`）：`lang="ja"`、`lang="en"`、`xml:lang="ko"` 内的汉字不是 target；`lang="zh-Hans"`、`lang="zh"`、无 lang 的内容是 target；嵌套 `<span lang="ja"><span lang="zh">汉</span></span>` 中"汉"是 target。

---

### A-12 `<rtc>` 注音未保护（P3，已复现）

**位置**：`plugin/OpenCCForSigil/app/settings.py`（约第 547-563 行）的 `tokenizer_policy` 只保护 `rt`、`rp`；NCX 处理在 `document/xml_processor.py`。

**修改步骤**：
1. `tokenizer_policy` 的受保护元素加上 `rtc`。
2. NCX 里的 CDATA：规范没有规定。**不要改**，只在 `docs/deviations.md` 记一句"正文 CDATA 不转换，NCX CDATA 转换"，等作者决定（见 `02-release-plan.md` 第 6 节第 1 项）。

**测试**：`<ruby>汉<rtc>ㄏㄢˋ</rtc></ruby>` 中注音不是 target。

---

### A-13 profile 的 `mathml: true` 能通过校验但不生效（P3，阅读推断）

**位置**：`plugin/OpenCCForSigil/app/profiles.py`（约第 128 行）接受 `mathml`；`app/settings.py`（约第 556 行）构造 `tokenizer_policy` 时没有把它传给 `TokenizerOptions`。

**修改步骤**：先写测试确认：profile 设 `mathml: true`，规划 `<math><mtext>汉字</mtext></math>`，看是否有变更。
- 没有变更（确认问题）：在构造 `TokenizerOptions` 时传入 `mathml=profile.mathml`（字段名以实际为准）。
- 已有变更：说明已生效，在提交说明里写明"无需修改"，只保留测试。

---

### A-14 NCX 或 metadata 不良构时整次运行失败（P3，阅读推断）

**位置**：`plugin/OpenCCForSigil/core/workflow.py`（约第 522-527 行）没有捕获 `XMLDocumentError`。XHTML 不良构时会跳过该文件并继续（L-13），NCX/OPF 却会让整次失败。

**修改步骤**：
1. 先写测试：一个良构 XHTML 加一个不良构 NCX，开启 NCX 转换。确认当前行为是整次失败。
2. 在规划 NCX、metadata 的地方捕获 `XMLDocumentError`，按 XHTML 跳过文件的同样方式生成诊断（复用 L-13 的诊断码和结果对话框里的"已跳过的不合法文件"列表），继续处理其他文件。

**测试**：断言 XHTML 被转换、NCX 未修改、结果里列出了 NCX 文件和行号。

---

### A-15 偏好文件固定用 `preferences.json.tmp` 作临时文件（P3，阅读推断）

**位置**：`plugin/OpenCCForSigil/sigil/storage.py`（约第 196-205 行）。两个 Sigil 实例同时写时会冲突。`ProfileStore`、`RuleStore` 已经用 `tempfile.mkstemp`。

**修改步骤**：改成与 `ProfileStore` 相同的写法：同目录 `tempfile.mkstemp(prefix="preferences.", suffix=".tmp")`，写入、`flush`、`os.fsync`，再 `os.replace`；失败时删除临时文件。

**测试**（`tests/unit/test_storage.py`）：monkeypatch `os.replace` 抛错，断言目录里不残留 `.tmp` 文件；连续两次保存互不影响。

---

## 4. UI 缺陷（B）

以下 B-01 至 B-04 在真实 PySide6 6.11（offscreen）里复现过。仓库的 `.venv` 没有 PySide6，所以测试一律用 `tests/support/fake_qt.py`。每一条的"测试"一栏写的是假 Qt 里能断言的内容。

### B-01 上次用过 Jieba 时，Jieba 复选框取消不掉（P1，已复现）

**位置**：`plugin/OpenCCForSigil/ui/preview_window.py`，`_apply_jieba_state`（约第 1708-1710 行）：

```python
if self._probe_state == "available" and self._preferred_jieba \
        and not self._direction_reselected and base_config == self._default_base:
    self.jieba_checkbox.setChecked(True)
```

**原因**：`_apply_jieba_state` 在每次状态刷新时都会执行（包括 `jieba_checkbox.stateChanged` 触发的刷新）。用户取消勾选 → `stateChanged` → 这段代码又把它勾回去。

**修改步骤**：
1. 在对话框的 `__init__` 里（`self._direction_reselected` 初始化的地方）加 `self._jieba_auto_checked = False`。
2. 把上面那段改成只执行一次：
   ```python
   if (self._probe_state == "available" and self._preferred_jieba
           and not self._direction_reselected and base_config == self._default_base
           and not self._jieba_auto_checked):
       self._jieba_auto_checked = True
       self.jieba_checkbox.setChecked(True)
   ```
3. 在 `__init__` 里 `self.jieba_checkbox.setChecked(default_config in self._jieba_configs.values())` 这一行执行后，如果结果为 True，也把 `self._jieba_auto_checked = True`（探测已经完成、一开始就勾上的情况）。

**测试**（`tests/unit/test_conversion_dialog_jieba.py`）：
- `test_user_can_uncheck_preferred_jieba`：首选配置为 `s2t_jieba`，探测状态为 available。构造对话框 → 断言复选框已勾选 → 调用 `jieba_checkbox.setChecked(False)`（假 Qt 必须因此发出 `stateChanged`）→ 断言 `isChecked()` 为 False，`_get_config()` 为 `"s2t"`。
- `test_preferred_jieba_is_checked_when_probe_finishes`：探测先是 pending、再变成 available（调用 `_poll_jieba_probe()`），断言复选框被勾选一次；之后用户取消，再调用 `_poll_jieba_probe()`，断言仍然是未勾选。

**不要**：不要改 `_direction_reselected` 的含义。

---

### B-02 Jieba 探测计时器从不停止（P1，已复现）

**位置**：`preview_window.py`
- 计时器创建：约第 1657-1665 行（`self._probe_timer = timer_type(self.dialog)`，50 ms）。
- `_poll_jieba_probe`（约第 1735-1747 行）：探测结束后没有停止计时器。
- 约第 1645-1646 行：只有 `cancel_button.clicked` 连到了 `_stop_probe_timer`。按 Esc 或标题栏关闭走的是 `reject()`，不经过它。

**后果**：探测结束后每 50 ms 仍调用一次 `options_panel.update_enablement`，它会清空并重建中转链下拉框（实测 500 ms 重建 11 次）；对话框关闭后计时器还在后续窗口的事件循环里跑。

**修改步骤**：
1. 在 `_poll_jieba_probe` 的末尾（`self._update_jieba_state()` 之后）加：
   ```python
   if state != "pending":
       self._stop_probe_timer()
   ```
2. 在创建计时器之后加：`self.dialog.finished.connect(self._stop_probe_timer)`。如果 `QDialog` 没有 `finished` 信号（假 Qt 可能没有），在 `fake_qt.py` 给 dialog 加一个 `finished` 信号，并在 `accept()`、`reject()`、`done()` 里发出。
3. 确认 `_stop_probe_timer` 在 `_probe_timer` 为 None 或已停止时调用也不会出错。

**测试**（`tests/unit/test_conversion_dialog_jieba.py`）：
- 探测从 pending 变 available，调用一次 `_poll_jieba_probe()` 后，断言 `dialog._probe_timer.isActive()` 为 False。
- 对话框 `reject()` 之后，断言计时器已停止。

---

### B-03 无变化结果框里按 Esc 或关闭窗口，会回到文件选择（P1，已复现）

**位置**：`preview_window.py` 约第 475-489 行（`show_result` 里 `return_to_scope or report_text` 分支）。"返回文件选择"按钮用的是 `QMessageBox.RejectRole`，Qt 自动把它当作 Esc 按钮。

**修改步骤**：
1. 把 `back = box.addButton(..., qt_widgets.QMessageBox.RejectRole)` 的 `RejectRole` 改成 `ActionRole`。
2. 在 `box.setDefaultButton(close)` 后面加 `box.setEscapeButton(close)`。
3. 如果假 Qt 的 `QMessageBox` 没有 `setEscapeButton`，在 `fake_qt.py` 里补上：记录按钮，并在测试用的"按 Esc"辅助方法里返回它。

**测试**（`tests/unit/test_result_counts.py` 或 `test_preview_window.py`）：构造 `return_to_scope=True` 的结果框，模拟按 Esc（`clickedButton()` 返回 escape 按钮），断言返回值为 `"close"`，不是 `"back_to_scope"`。

---

### B-04 预览里每做一个决定要卡 200–280 ms（P1，已复现）

与 D-02 一起做，步骤见 D-02 第 5 步。

---

### B-05 多个窗口里回车会点中错误的按钮（P2，已复现）

Qt 会把第一个 `autoDefault` 按钮当默认按钮。以下窗口都没有显式指定：

| 窗口 | 位置 | 当前回车效果 | 修改 |
| --- | --- | --- | --- |
| 规则窗口 | `ui/rules_window.py` 约第 325-329 行 | 在"源文本"框按回车，弹出"新建规则集" | 所有按钮 `setAutoDefault(False)`；"源文本""目标文本"两个 QLineEdit 的 `returnPressed` 连到"新增/更新规则" |
| 历史窗口 | `ui/history_window.py` 约第 137-145 行 | 在表格上按回车，弹出清理确认框 | 所有按钮 `setAutoDefault(False)`；"查看报告"`setDefault(True)`；表格为空时禁用"清理" |
| 错误对话框 | `preview_window.py` 约第 556-571 行 | 回车只展开/收起详情 | "详情"`setAutoDefault(False)`；"关闭"`setDefault(True)` |
| 范围对话框 | `preview_window.py` 约第 1867、1893-1898 行 | 在筛选框按回车直接进入下一步 | 筛选框的 `returnPressed` 连到一个空函数（吞掉回车），或者连到"选中第一个可见项" |

**修改步骤**：按上表逐个窗口修改。每个窗口单独一个提交。

**测试**：每个窗口一个测试，断言对应按钮的 `autoDefault()` / `isDefault()` 状态符合上表；规则窗口额外断言：在源文本框触发 `returnPressed` 后，规则表多了一行，且没有调用 `QInputDialog.getText`（monkeypatch 成抛异常）。

---

### B-06 规则窗口按 Esc 或"取消"会静默丢弃未保存的规则（P2，已复现）

**位置**：`ui/rules_window.py` 约第 426 行（对话框的 reject）。

**修改步骤**：
1. 打开窗口时记录当前规则集内容的快照（规则元组，或 `sha256`）。
2. 重写 reject 路径：如果当前内容与快照不同，弹出确认框，复用预览窗口放弃确认的写法（在 `preview_window.py` 搜索 `_confirm_discard_decisions`，把它提取成 `ui/` 下的公共函数，或照它的结构写一个）。默认按钮是"返回编辑"，Esc 也等于"返回编辑"。
3. 新文字加 i18n 键：`rules.discard_title`、`rules.discard_message`、`rules.discard_confirm`、`rules.discard_back`。

**测试**（`tests/unit/test_rules_window.py`）：新增一条规则后 reject → 断言确认函数被调用；选择"返回编辑"→ 窗口没有关闭；未修改时 reject → 确认函数没有被调用。

---

### B-07 范围对话框切换界面语言后仍有控件是旧语言（P2，已复现）

**位置**：`preview_window.py` 约第 1958-1981 行（`_language_changed`）。`guide_label`、列表项的"（导航）"后缀、`recovery_notice_label` 没有重新翻译。

**修改步骤**：在 `_language_changed` 里补上这三处：
1. `self.guide_label.setText(self._translator.text(<构造时用的同一个键>))`。
2. 遍历列表项，用构造时相同的函数重新生成每项文字（导航文件带后缀）。把构造时生成文字的代码提取成一个方法，构造和切换语言时共用。
3. `recovery_notice_label` 同理（只在它存在且可见时）。

**测试**（`tests/unit/test_scope_selection.py`）：以 zh-Hans 构造，切换到 en，断言这三处的文字等于 en 目录里对应键的值。

---

### B-08 预览打开时焦点在"文件"筛选框（P2，已复现）

**位置**：`preview_window.py` 约第 823、882 行。用户按↓想看下一行，却改了筛选。

**修改步骤**：在 `_PreviewDialog.__init__` 的最后（第一次 `_refresh()` 之后）加 `self.table_view.setFocus()`。

**测试**：假 Qt 记录 `setFocus` 调用；断言构造后获得焦点的是 `table_view`。

---

### B-09 进度框宽度随文件名变化，长文件名能撑到约 1489 px（P2，已复现）

**位置**：`preview_window.py` 约第 71-107 行、135-143 行（进度报告器）。

**修改步骤**：
1. 创建进度框时 `setMinimumWidth(480)`，并设置固定宽度（`setFixedWidth(480)` 或最大宽度 640）。
2. 设置文件名文字前用 `QFontMetrics(label.font()).elidedText(text, Qt.ElideMiddle, label.width() or 440)` 截断；完整文件名放进 tooltip。
3. 假 Qt 缺 `QFontMetrics` 时，在 `fake_qt.py` 里补一个按字符数截断的简化实现。

**测试**（`tests/unit/test_progress_reporter.py`）：传入 300 个字符的文件名，断言标签文字长度小于原文、包含 `…`，tooltip 等于原文。

---

### B-10 单文件模式下筛选会隐藏当前选中的文件（P3，已复现）

**位置**：`preview_window.py` 约第 2037-2042 行。

**修改步骤**：单文件模式下，计数行显示"已选择：<文件名>"（i18n 键 `scope.selected_file`），筛选时即使该项被隐藏也保持显示这行文字。

**测试**：单文件模式选中 A，筛选到只显示 B，断言计数行包含 A 的文件名，`selected_ids()` 仍为 A。

---

### B-11 报告窗口没有关闭按钮，看完报告回不到结果框（P3，已复现）

**位置**：`app/settings.py` 约第 524-533 行（`show_text`）；`preview_window.py` 约第 486-488 行。

**修改步骤**：
1. `show_text` 加一个 `QDialogButtonBox(Close)`，连到 `dialog.accept`。
2. 结果框点"查看报告"后，报告关闭时重新显示结果框（把 `show_result` 里的 `exec_dialog(box)` 放进循环：点了"查看报告"就显示报告，然后 `continue` 再次 `exec_dialog(box)`；点其他按钮才返回）。

**测试**：模拟依次点击"查看报告""关闭"，断言报告函数调用一次，最终返回 `"close"`。

---

### B-12 导出预览失败时没有任何提示（P3，代码确认）

**位置**：`preview_window.py` 约第 1016-1025 行（`_export_preview`）。只捕获了 `OSError`、`ValueError`，`RuntimeError` 等只打印到 stderr。

**修改步骤**：改成 `except Exception as error:`，用已有的警告框函数显示"导出失败：{reason}"（i18n 键 `preview.export_failed`，如果已有同义键就复用）。

**测试**：monkeypatch `export_preview` 抛 `RuntimeError("x")`，断言警告函数被调用且消息包含 `x`。

---

## 5. UI 体验改进（C）

> 这些条目不修就不会出错，但会让界面难用。做完批次 5 再做。每条一个提交。**C-02 必须在 Sigil 里实测**，其余可以用假 Qt 测试加截图检查。

### C-01 预览表格看不到实际变更的字（P1）

**问题**：
- "原文""转换后"两列显示"前 20 字上下文【变更】后文"，在右端截断，【变更】经常被截掉。
- 文件列是 `ResizeToContents`，长路径把其他列挤到约 15 px。
- 文件筛选下拉框按最长项定宽，对话框最小宽度被撑到 1058 px（zh）/ 1144 px（en）。
- `setStretchLastSection(True)` 把"风险"列拉宽。

**修改步骤**：
1. **新增一列"变更"**，显示 `source → target`（例如 `后 → 後`）。在 `_PREVIEW_COLUMNS` 里状态列之后插入 `"change"`；三个 i18n 文件加 `preview.column.change`。`format_change_row` 返回的元组相应加一项。
2. **文件列只显示文件名**（`href` 的最后一段），完整路径放在 `ToolTipRole`。
3. **上下文列**：前文太长时从左边截断，保证【变更】可见。在 `format_change_row` 里把前文截成最后 12 个字符，前面加 `…`；后文截成前 12 个字符，后面加 `…`。
4. **所有单元格**在 `data()` 里对 `ToolTipRole` 返回完整文字。
5. 删除 `header.setStretchLastSection(True)`。"原文""转换后"两列用 `Stretch`，其余列在 D-02 第 5 步里设为 `Interactive`。
6. 三个筛选下拉框：`setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)`，`setMinimumContentsLength(16)`。

**测试**（`tests/unit/test_preview_model.py`）：
- 断言列数比原来多 1，第 2 列（从 0 开始数，以实际插入位置为准）为 `"后 → 後"`。
- 前文 50 个字的变更，断言上下文列以 `…` 开头且包含 `【`。
- 断言文件列显示 `ch001.xhtml`、tooltip 为 `Text/ch001.xhtml`。

**已知会变的测试**：`test_preview_model.py`、`test_preview_window.py` 中按列下标取值的断言。只改下标。

---

### C-02 使用 Sigil 的 `PluginApplication`（P1，必须在 Sigil 里实测）

**问题**：`ui/qt.py` 的 `ensure_application` 直接 `QApplication(sys.argv)`。Sigil 自带的 `plugin_utils.PluginApplication(sys.argv, bk=bk)` 会同步 Sigil 的深色调色板、界面字体、高 DPI 设置，并加载 Qt 自带文字（OK/Cancel 等）的翻译。不用它，深色 Sigil 下插件窗口是浅色的，`QMessageBox`、`QInputDialog` 的按钮是英文。

**修改步骤**：
1. `ui/qt.py` 加模块级变量 `_host_bk = None` 和函数：
   ```python
   def set_host_book(bk: Any) -> None:
       global _host_bk
       _host_bk = bk
   ```
2. `ensure_application` 在创建新实例时先尝试 `PluginApplication`：
   ```python
   if application is None:
       application = None
       if _host_bk is not None:
           try:
               from plugin_utils import PluginApplication
               application = PluginApplication(sys.argv, bk=_host_bk)
           except Exception:  # noqa: BLE001 - older Sigil or no plugin_utils
               application = None
       if application is None:
           application = qt_widgets.QApplication(sys.argv)
   ```
3. `app/controller.py` 的 `Controller.__init__` 开头调用 `set_host_book(bk)`（`from ui.qt import set_host_book`；如果 controller 不直接依赖 `ui`，就在 `plugin.py` 的 `run` 里调用）。
4. **不要**在这一条里改任何颜色。颜色见 C-03。

**测试**（`tests/unit/test_i18n.py` 或新文件 `tests/unit/test_qt_application.py`）：
- 注入一个假的 `plugin_utils` 模块（`monkeypatch.setitem(sys.modules, "plugin_utils", fake)`），断言 `set_host_book(bk)` 后 `ensure_application` 用了 `PluginApplication(sys.argv, bk=bk)`。
- `plugin_utils` 导入失败时，断言回退到 `QApplication`。

**Sigil 实测**：见 `02-release-plan.md` 第 4 节第 5、6 项。

---

### C-03 状态颜色硬编码，深色模式下对比度不足（P2）

**位置**：`preview_window.py` 约第 711-717 行，`#267a35`、`#777777`、`#a15c00`。在深色底 `#1e1e1e` 上对比度只有 3.1–3.7（WCAG AA 要求 4.5）。

**修改步骤**：
1. 在 `data()` 的 `ForegroundRole` 分支里，先取 `self.parent()` 或 `QApplication.palette()` 的 `Base` 颜色，`lightness() < 128` 视为深色。
2. 两套颜色：浅色 `#1f6f2e` / `#5f5f5f` / `#8a4d00`；深色 `#7fd18b` / `#b0b0b0` / `#f0b050`。
3. 状态文字已经能区分，颜色只是辅助；取不到 palette 时返回 `None`（使用默认前景色）。

**测试**：假 Qt 的 palette 分别返回浅色、深色 Base，断言返回的颜色属于对应的一套。

---

### C-04 繁中"接受"和"应用"都译成"套用"（P2）

**位置**：`resources/i18n/zh-Hant.json`。`preview.accept_this` = "套用此項"、`accept_file` = "套用本檔案"、`accept_all` = "套用全部檔案"、`status.accepted` = "套用"，而 `preview.apply` = "套用已接受的變更"。用户会以为点"套用此項"就立即写回。

**修改步骤**：在 `zh-Hant.json` 里，所有表示"接受一条变更"的值用"接受"；只有表示"写回书中"的值用"套用"。逐个检查 `preview.*`、`status.*`、`result.*` 下的键。`result.row.written` 统一为"已寫入"。

**测试**：`tests/unit/test_i18n.py` 加一个断言：zh-Hant 中键名含 `accept` 的值都不含"套用"。

---

### C-05 Qt 自带按钮和文字仍是英文（P2，依赖 C-02）

先做 C-02，在 Sigil 里确认 OK/Cancel 是否已经翻译。
- 已翻译：本条关闭。
- 未翻译：在 `ensure_application` 里，按插件界面语言加载 Qt 翻译：
  ```python
  translator = QtCore.QTranslator(application)
  path = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.TranslationsPath)
  if translator.load(f"qtbase_{'zh_CN' if lang == 'zh-Hans' else 'zh_TW'}", path):
      application.installTranslator(translator)
  ```
  并且把 `profile_window.py:238`、`rules_window.py:458/480`、`settings.py:251` 的 `QInputDialog.getText` 改成自建对话框（`QDialog` + `QLineEdit` + `QDialogButtonBox`，按钮文字走 i18n），`_warn`（`profile_window.py:329`、`rules_window.py:519`）改成 `ask_confirmation` 那种自建按钮的写法。

---

### C-06 转换设置对话框的按钮顺序（P2，需在 Sigil 里确认）

**问题**：offscreen 下是"分析并预览 | 上一步：更改文件 | 取消"，"上一步"夹在中间。`QDialogButtonBox` 的顺序随平台变化。

**修改步骤**：不用 `QDialogButtonBox` 放这三个按钮，改成 `QHBoxLayout`：`[上一步]  <stretch>  [取消] [分析并预览]`，与预览窗口、范围窗口的写法一致（在 `preview_window.py` 里搜索 `buttons.addWidget(self.back_button)` 参考）。"分析并预览"`setDefault(True)`。

**测试**：断言布局中按钮的顺序为 back、stretch、cancel、continue。

---

### C-07 设置面板内容沉到底部（P2）

**位置**：`ui/run_options.py` 约第 51-63 行、125-137 行。

**修改步骤**：
1. 在 `body_layout` 的最后加 `body_layout.addStretch(1)`。
2. 空的方案标签、规则集标签设置 `setSizePolicy(Preferred, Maximum)`。
3. "详情"按钮在没有错误时 `setVisible(False)`，有错误时才显示（原来是整行禁用）。

**测试**：断言 `body_layout` 最后一项是 stretch；没有错误时"详情"按钮 `isVisible()` 为 False。

---

### C-08 规则窗口的布局与用词（P2）

**问题**：最小高度 742 px（1366×768 屏幕放不下）；规则表只显示约 3 行；冲突列表没有标题；方向列显示 `s2t`、`*`；类型列显示 `exact` / `protect`；规则集下拉显示 `default`；"新建"（规则集）和"新增"（规则）容易混淆。

**修改步骤**：
1. 测试区（样例文本、结果）放进一个可折叠的 `QGroupBox`（`setCheckable(True)`，默认折叠），或放进 `QSplitter` 的下半部分。
2. 冲突列表上方加标签（i18n 键 `rules.conflicts_title`），`setMaximumHeight(120)`。
3. 方向列：用 `configuration_label(direction, translator)`（在 `ui/` 下搜索这个函数；`*` 显示为 i18n 键 `rules.direction_any`）。
4. 类型列：用已有的 `rules.exact`、`rules.protect` 键（约第 527 行）。
5. 规则集 id 为 `default` 时显示 i18n 键 `rules.default_set_name`。
6. 按钮文字：规则集的"新建"改为"新建规则集…"（`rules.new_set`），规则的"新增"保持；繁中两者要不同。

**测试**：断言方向列、类型列显示的是翻译后的文字；`minimumSizeHint().height()` 小于 600（假 Qt 无法算尺寸时跳过这条断言，改为截图检查）。

---

### C-09 方案窗口摘要不完整（P2）

**位置**：`ui/profile_window.py` 约第 184-203 行。

**修改步骤**：
1. 摘要改为逐行列出方案的**全部**选项：方向、Jieba、引号、标点、语言标签、强制中转、NCX、metadata、SVG 等（以方案模型的字段为准，遍历字段，每个字段一个 i18n 标签）。用换行分隔，不要用逗号连成一行。
2. 规则集复选框区域加说明文字"仅本次运行使用，不保存到方案"（`profile.rulesets_session_only`）。
3. 方案名列表项设置 tooltip 为完整名称。

**测试**：两个只在引号模式上不同的方案，断言摘要文字不同。

---

### C-10 历史窗口的列内容与排序（P2）

**位置**：`ui/history_window.py` 约第 44-51 行、207 行。

**修改步骤**：
1. "方案"列显示方案名：用 `profile_id` 在 `ProfileStore` 里查名字，查不到显示 `profile_id` 前 8 位。
2. "方向"列用 `configuration_label`。
3. "文件数""变化数"两列：`item.setData(Qt.DisplayRole, int(value))`，让排序按数字。

**测试**：断言数字列的 `data(DisplayRole)` 是 `int`；方向列是翻译后的文字。

---

### C-11 错误对话框过窄（P2）

**位置**：`preview_window.py` 约第 523-571 行（错误对话框）。

**修改步骤**：`setMinimumWidth(420)`；在消息左边加标准警告图标（`style().standardIcon(QStyle.SP_MessageBoxWarning)` 放进 `QLabel`）；"关闭"设为默认按钮（与 B-05 一致）。

---

### C-12 无障碍与快捷键提示（P2）

**修改步骤**：
1. "转换方向""界面语言"等标签调用 `label.setBuddy(<对应控件>)`，规则编辑区的 `QGridLayout` 标签同样处理。
2. 筛选框、表格、横幅上的"×"按钮调用 `setAccessibleName(...)`（i18n 键 `a11y.*`）。
3. 预览窗口"接受此项""跳过此项""下一条未决"按钮的 tooltip 加上快捷键，例如"接受此项（A）"；状态行加一句"A 接受 · S 跳过 · N 下一项"（`preview.shortcut_hint`）。

**测试**：断言这些控件的 `accessibleName()` 非空；tooltip 含 `(A)`。

---

### C-13 预览窗口的垂直空间分配（P2）

**修改步骤**：
1. 表格和详情放进 `QSplitter(Qt.Vertical)`，`setStretchFactor(0, 3)`、`setStretchFactor(1, 1)`；删除详情框的 `setMinimumHeight(180)`，改为 80。
2. 窗口尺寸、分隔位置写入 `ui_preferences`，下次打开恢复（参考转换设置对话框保存尺寸的代码，在 `run_options.py` 或 `preview_window.py` 里搜索 `ui_preferences`）。
3. 顶部汇总里"已跳过的不合法文件"列表超过 3 个时，只显示前 3 个加"等 N 个"，完整列表放 tooltip。

---

### C-14 i18n 清理（P3）

1. 删除未使用的键。先运行下面的命令列出候选，逐个确认代码里（包括 `f"...{name}"` 拼接）确实没有用到，再删：
   ```sh
   .venv/bin/python docs/reviews/2026-09-23/scripts/round2/i18n_check.py
   ```
   本轮审查列出的候选：`error.backend_self_test/failed/read/scope_invalid`、`options.operation_failed`、`preview.apply_accepted/apply_one/apply_many/change/checkpoint_message/checkpoint_yes/checkpoint_no`、`profile.jieba`、`result.cancelled/done/noop/partial/skipped`、`result.changes_*/files_*/not_written_*/unchanged_*`、`scope.all_count/choose/selected_count/spine_count`、`settings.ruleset`。**注意**：A-04 会修改 `result.partial`，如果 A-04 已经在用它就不要删。
2. 英文单复数："Apply 1 changes to 1 file"。改成 `{count, plural}` 不可用时，拆成 `_one` / `_many` 两个键，代码里按数量选。
3. 中文术语统一：变更（不用"修改""变化"）、标签（不用"标记"）、方案（不用"配置方案"）。状态值用"已接受""已跳过"。
4. 中文界面里的英文冒号 `": "`（`preview_window.py:1276-1282`、`profile_window.py:200-202`、`rules_window.py:152-164、647-652`）改为 i18n 键 `common.label_separator`（中文值"："，英文值": "）。
5. 文件过滤器字面量（`rules_window.py:702/826`、`settings.py:478`）、导出预览时写入的 `"preview (not committed)"` 移入 i18n。

---

### C-15 各窗口之间不一致（P3）

1. 窗口标题统一加插件名："OpenCCForSigil — <窗口名>"（`app.title` + 分隔符 + 窗口名）。
2. 按钮行统一为"左侧次要按钮 / stretch / 右侧取消 + 主按钮"。方案窗口的 6 个等宽按钮改为这种布局。
3. 每个窗口都记住尺寸（写入 `ui_preferences`，键为窗口名）。

---

### C-16 范围对话框的列表与横幅（P3）

1. 列表 `setTextElideMode(Qt.ElideMiddle)`，每项 tooltip 为完整路径，保证"（导航）"后缀可见。
2. 横幅"×"按钮 `setFixedWidth(24)`、`setFlat(True)`。
3. 恢复提示和 Checkpoint 横幅加信息图标和浅色背景（颜色从 palette 取，参考 C-03）。

---

### C-17 结果文案不说明为什么没写回（P3）

"未写回：1 个文件（其中没有建议变更：0 个）"没有说明另外那个文件是因为全部跳过。在结果统计里加"全部跳过：N 个"一项（`result.files_all_skipped`），并在文案里显示。

---

## 6. 性能（D）

测量环境：合成书 200 个 XHTML、4.06 MB、约 104 万汉字（`scripts/perf/book.py`），macOS arm64，CPython 3.14.7。约产生 28 万条变更。

| 场景 | 当前 | 目标 |
| --- | --- | --- |
| 规划，s2twp，UI 默认选项 | 12.9–15.5 s | ≤ 6 s |
| 规划，s2t，UI 默认选项 | 9.4–10.3 s | ≤ 4 s |
| 预览对话框构建（28 万条） | 1.7 s | ≤ 0.4 s |
| 预览里点一次"接受此项"（28 万条，真实 Qt） | 约 0.5 s | ≤ 30 ms |
| Jieba 探测（主线程最长卡顿） | 2.1–2.4 s（约 300 ms） | ≤ 0.5 s（≤ 100 ms） |
| 全部测试 | 162–181 s | ≤ 110 s |

### D-01 等长输出按位置对比，不用 SequenceMatcher（P0，与 A-02 一起做）

**位置**：`plugin/OpenCCForSigil/core/diff.py`，`bounded_opcodes`。

**依据**：OpenCC 的输出绝大多数与输入等长（本书 s2t/s2twp 中有变化的目标 100% 等长）。等长时按位置逐字比较就能得到精确的变更，速度快 9–10 倍，而且修掉了约 0.5% 目标上 SequenceMatcher 的错位（例如本该逐字的 `面→麪`、`资→資` 被对成 `'' → '麪包資源後'` 加 `'包资源后面还' → '還'`）。

**复现 / 测量**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/perf/diff_fastpath.py
```

**修改步骤**：
1. 在 `bounded_opcodes` 中，`if source == target:` 分支之后、`_DETAILED_LIMIT` 分支之前加：
   ```python
   if len(source) == len(target):
       return _positional_opcodes(source, target)
   ```
2. 新增：
   ```python
   def _positional_opcodes(source: str, target: str) -> tuple[Opcode, ...]:
       """Diff two equal-length strings by position.

       Consecutive differing characters form one ``replace``; this keeps an
       OpenCC phrase such as 打印机 -> 印表機 in one opcode.
       """
       opcodes = []
       index = 0
       length = len(source)
       while index < length:
           end = index
           same = source[index] == target[index]
           while end < length and (source[end] == target[end]) == same:
               end += 1
           opcodes.append(("equal" if same else "replace", index, end, index, end))
           index = end
       return tuple(opcodes)
   ```
3. 然后做 A-02 的第 2-4 步（非等长时合并相近的变更）。

**测试**（`tests/unit/test_converter_diff.py`）：
- `bounded_opcodes("后面还有", "後面還有")` == `(("replace",0,1,0,1), ("equal",1,2,1,2), ("replace",2,3,2,3), ("equal",3,4,3,4))`。
- `bounded_opcodes("面包资源后面还", "麪包資源後面還")` 的非 equal 段全部是单字替换（修掉错位）。
- 等长随机字符串 200 组：结果满足 A-02 测试 3 的"完全覆盖且可还原"。

**验证**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/perf/diff_fastpath.py      # different-spans 这一项会大于 0，这是预期（错位被修掉）
.venv/bin/python docs/reviews/2026-09-24/scripts/perf/bench_plan.py s2twp    # plan 时间应比修改前下降一半以上
mise exec -- uv run pytest -q
```
把修改前后 `bench_plan.py` 的输出都写进提交说明。

---

### D-02 预览表按需格式化、只刷新改动的行（P0）

**位置**：`plugin/OpenCCForSigil/ui/preview_window.py`
- `_PreviewTableData.__init__`（约第 641-655 行）：构造时对全部条目调用 `format_change_row`。
- `PreviewTableModel.__init__`（约第 689-691 行）建一次 `_PreviewTableData`，`_PreviewDialog._refresh` → `set_entries`（约第 732-736 行）又建一次。28 万条时共调用 `format_change_row` 56.3 万次。
- `refresh`（约第 738-743 行）：每次决定都对整张表 `refresh_statuses()`，并对整张表发 `dataChanged`。
- `_update_summary`、`_refresh_file_filter_counts`、`_visible_entries`：每次决定都全量遍历。

**修改步骤**：
1. **行文字按需生成并缓存。** `_PreviewTableData.__init__` 不再循环格式化。改为 `self._display_cache = {}`，`row_values(row)` 里：
   ```python
   change_id = self.entries[row][1].change_id
   values = self._display_cache.get(change_id)
   if values is None:
       values = self._format(row)          # 原来循环体里的逻辑
       self._display_cache[change_id] = values
   return (self._status(*self.entries[row]), *values)
   ```
   `statuses` 列表和 `refresh_statuses` 删除：状态在 `row_values` 里现算（一次 `decision()` 查询，很便宜）。
2. **格式化缓存跨 `set_entries` 共享。** 把 `_display_cache` 放在 `PreviewTableModel` 上（或 `_create_preview_table_model` 的闭包里），`set_entries` 创建新的 `_PreviewTableData` 时传入同一个缓存字典。筛选只换条目列表，不重新格式化。
3. **构造时只建一次。** `PreviewTableModel.__init__` 里先用空条目（或直接用第一次 `_refresh` 的结果），避免构造时建一次、`_refresh` 又建一次。
4. **只刷新改动的行。** `refresh()` 增加可选参数 `rows=None`。`_decide_entry` 的单条分支调用 `self.table_model.refresh(rows=[current_row])`，只对这一行发 `dataChanged(index(row, 0), index(row, 0))`（状态列）。批量决定（整个文件、全部）仍然整表刷新。
5. **（B-04）表头不再按内容反复计算列宽。** 约第 891-899 行：把第 0、1、4、5 列的 `ResizeToContents` 改为 `Interactive`；对话框第一次显示后调用一次 `self.table_view.resizeColumnsToContents()`，或者 `header.setResizeContentsPrecision(50)`（只看前 50 行）。
6. **汇总计数增量维护。** `_update_summary` 不再每次对所有 `PreviewSession.summary()` 求和：在对话框上维护 `self._totals`（total/accepted/rejected/undecided），`_decide_entry` 单条决定时按新旧状态加减；批量决定后再全量重算一次。`_refresh_file_filter_counts` 同理，只在批量决定后重算。

**测试**（`tests/unit/test_preview_model.py`、`test_preview_window.py`）：
- 计数测试：monkeypatch `format_change_row` 统计调用次数。5000 条变更构造对话框后，调用次数 ≤ 可见行数（假 Qt 可能不调用 `data()`，那就断言为 0）；筛选再恢复"全部"后，同一 change 不会被格式化第二次。
- 单条决定只刷新一行：monkeypatch 模型的 `dataChanged.emit`，断言 `_accept_this()` 后发出的范围是一行。
- 已有的"5 万条"测试把规模提到 30 万条（D-08），并断言 `_accept_this()` 耗时 < 50 ms（假 Qt）。
- 汇总：随机做 100 次单条接受/跳过后，`self._totals` 与全量重算的结果相同。

**验证**：
```sh
mise exec -- uv run pytest tests/unit/test_preview_model.py tests/unit/test_preview_window.py -q
```
Sigil 里用一本大书实测单击是否流畅（`02-release-plan.md` 第 4 节第 8 项）。

---

### D-03 每条变更只构造一次（P1）

**位置**：`plugin/OpenCCForSigil/core/planner.py` 约第 123-128 行：
```python
change = _absolute_change(file_id, target, local_change, source, ...)
if document_kind == "metadata":
    change = replace(change, risk="HIGH")
changes.append(replace(change, document_kind=document_kind))
```
每条变更先在转换器里建一次，`_absolute_change` 再建一次，`replace` 又复制一到两次。28 万次 `dataclasses.replace` 约 0.9 s。

**修改步骤**：
1. 给 `_absolute_change` 加两个关键字参数 `document_kind` 和 `risk_override=None`，在它内部构造 `TokenChange` 时直接填入 `document_kind=document_kind`，`risk=risk_override or <原来的 risk>`。
2. 调用处改为：
   ```python
   change = _absolute_change(
       file_id, target, local_change, source,
       cdata_ranges=cdata_ranges, cdata_starts=cdata_starts,
       document_kind=document_kind,
       risk_override="HIGH" if document_kind == "metadata" else None,
   )
   changes.append(change)
   ```
3. 检查 `_absolute_change` 的其他调用方（`grep -n "_absolute_change" plugin/OpenCCForSigil -r`），给它们传同样的参数，保持行为不变。

**测试**：已有测试全部通过即可，外加：monkeypatch `core.planner.replace` 计数，规划一个 100 条变更的文件，断言调用次数 < 10。

**验证**：`bench_plan.py` 前后对比写进提交说明。

---

### D-04 分类器的对齐按需计算（P1，依赖 A-02 + D-01）

**位置**：`plugin/OpenCCForSigil/core/classifier.py`，`classify_conversion`（约第 66-70 行）。s2twp 开启详细分类时，每个有变化的目标做 5 次 diff：转换器 1 次、分类器 4 次（s2t、s2tw、s2twp 各一次，再对 final 一次）。其中 `alignments[config]` 和 `final_alignment` 输入完全相同，重复计算。

**修改步骤**：
1. `final_alignment`：如果 `selected == output_map.get(config)`，直接复用 `alignments[config]`，不再调用 `bounded_opcodes`。
2. 更进一步：`alignments` 改为按需字典。先读 `_project_target`（或使用 `alignments` 的函数），确认 alignments 只在源和目标长度不同时才被使用。如果是，把 `alignments = {...}` 改成一个小类或 `functools.lru_cache` 包装的函数 `alignment(name)`，只在第一次用到时计算。
3. 相同输出字符串共用同一个对齐：用 `{output: bounded_opcodes(source, output)}` 做缓存键。

**测试**：monkeypatch `core.classifier.bounded_opcodes` 计数，s2twp、详细分类、等长输出时，断言每个目标调用次数 ≤ 1；分类结果与修改前相同（用 `tests/unit/` 里已有的分类测试保证）。

---

### D-05 Jieba 探测只构造一个配置（P1，依赖 B-01、B-02）

**问题**：`JiebaProbe` 依次构造 7 个 jieba 配置，共 2.1–2.4 s。pybind 构造 OpenCC 对象时一直持有 GIL，主线程每次被卡约 300 ms，设置对话框周期性卡顿。

**修改步骤**：
1. 找到 `JiebaProbe`（`grep -rn "class JiebaProbe" plugin/OpenCCForSigil`）。探测只构造 `s2t_jieba` 一个配置并做一次转换；成功就认为所有 jieba 配置可用（它们共用同一份 Jieba 数据）。
2. `available_configs_nonblocking()` 在探测成功后返回全部 jieba 配置。
3. 真正运行时选中的 jieba 配置由工作线程里的后端构造来验证（已有逻辑），构造失败时走已有的错误路径。
4. 在 `docs/deviations.md` 记一句：探测只验证一个 jieba 配置。

**测试**（`tests/integration/test_jieba_probe_flow.py`）：monkeypatch 后端构造函数计数，探测完成后断言只构造了 1 次；`available_configs_nonblocking()` 返回的配置集合与修改前相同。

---

### D-06 同一进程只哈希一次载荷树（P1）

**问题**：冷启动构造后端时，载荷树（98 个文件，24 MB）被 SHA-256 计算 5 次：`select()` 1 次，`_SourceOnlyLoader` / `_VerifiedExtensionLoader` 的 `exec_module`、`create_module` 里 4 次（`opencc_backend/runtime_selector.py` 约第 96-105、377、455 行）。一次转换至少构造 2–3 个后端（`controller.py` 约第 94、295、330 行），每个都要重新哈希、重新自检。

**修改步骤**：
1. 在 `runtime_selector.py` 加一个模块级缓存：键为 `(root 的绝对路径, 每个文件的 (相对路径, size, mtime_ns) 元组)`，值为哈希结果。计算键只需要 `os.stat`，不读文件内容。
2. 所有计算载荷树哈希的地方都先查缓存。
3. 如果 loader 需要"加载时再校验一次"以防文件被替换（安全要求），保留**第一次**加载时的完整哈希，后续命中缓存的前提是 size 和 mtime 都没变。把这个取舍写进 `docs/native-backend.md`。

**测试**（`tests/unit/test_payload_integrity.py`）：monkeypatch `hashlib.sha256` 计数，同一进程构造两次后端，断言第二次不再读载荷文件；修改其中一个文件的 mtime 后，断言会重新哈希。

---

### D-07 控制器集成测试共享后端（P2，依赖 D-05、D-06）

**问题**：全部 421 个测试 162–181 s，其中 60 个集成测试占约 76%。每个控制器集成测试 4–5 s，主要是真实构造 OpenCC 加后台 Jieba 探测（约 2.2 s）和载荷哈希。

**修改步骤**：
1. 在 `tests/integration/conftest.py`（没有就新建）加一个 `scope="session"` 的 fixture，缓存已构造的 `OpenCCBackend`（按配置）和一个已完成的 `JiebaProbe`。
2. 控制器集成测试通过 monkeypatch 让 `Controller` 使用这些缓存对象（找到 `controller.py` 里构造后端和探测的位置，看已有测试是否已有注入点；没有就加一个可选参数，默认行为不变）。
3. `test_jieba_probe_flow.py` 这种专门测探测的测试**不要**用缓存。

**验证**：`mise exec -- uv run pytest -q --durations=15`，把前后的总时间写进提交说明。目标 ≤ 110 s。

---

### D-08 预览规模测试提高到 30 万条；可选的内存优化（P2）

1. 把 `test_preview_model.py` / `test_preview_window.py` 里 5 万条的测试规模提到 30 万条（真实中文书约每个汉字产生 0.27 条变更，100 万字的书约 28 万条）。如果单个测试超过 10 s，就只在 `-m slow` 标记下运行，并在 `docs/testing.md` 说明。
2. （可选，单独提交）规划后内存 316 MB（约 1.1 KB/条）。其中 `context_before`、`context_after` 共 65 MB（`planner.py` 约第 331-332 行），`text_context` 41 MB。改为只存偏移、显示时从原文切片，可以降到约 180 MB。**这项改动涉及 `TokenChange` 的字段，影响面大，只在前面各项都完成后再做**，并先在提交说明里列出所有读取这些字段的地方。

---

## 7. 第二轮遗留（R-xx）与复审中新发现的问题（N-xx）

### 7.1 第二轮条目状态

复审方法：逐条运行第二轮的复现脚本；把每个修复提交在副本里回滚，确认对应测试会失败。

| 条目 | 状态 | 说明 |
| --- | --- | --- |
| R-01 闭引号分类 | 已修复 | ee56faf；回滚后 5 项测试失败。遗留见 N-07 |
| R-02 循环后 Jieba 丢失 | 已修复 | 141f486。缺一个测试，见 N-08 |
| R-03 方向被重置 | 已修复 | 回滚后 2 项集成测试失败 |
| R-04 部分写回报成 0 | 已修复 | 7f84637 |
| R-05 新版 schema 被隔离 | 已修复 | e489596 |
| R-06 强制中转误报 | 已修复 | 37f9e2e |
| R-07 覆盖层每文件重建 | 已修复 | 1976 条规则、300 个文件规划 0.83 s，构建 1 次 |
| R-08 旧偏好覆盖新值 | 已修复 | `update_preferences` |
| R-09 行列号 | 基本修复 | 列号基准见 N-04 |
| R-10 `]]>` | 已修复 | — |
| R-11 实体引号 | 已修复 | — |
| R-12 缓存键 | 已修复 | — |
| R-13 进程退出延迟 | 已修复 | 守护线程 |
| R-14 预览无法构造 | 已修复 | 33a7424，经真实 `__init__` 测试 |
| R-15 单文件"继续" | 已修复 | 33a7424 |
| **R-16 中转链被重置** | **部分修复** | "方案 → 使用"已修；**打开对话框时仍被替换**，见 N-02 |
| R-17 回车触发应用 | 已修复 | 真实 Qt 下复核通过 |
| R-18 改名后新建被删 | 已修复 | — |
| **R-19 "（已修改）"恒显示** | **未修复** | 见 N-03 |
| R-20 NAV 偏好 | 已修复 | — |
| R-21 布局顺序 | 已修复 | — |
| R-22 Jieba 下强制中转 | 已修复 | — |
| R-23 筛选计数 | 已修复 | — |
| R-24 应用按钮文案 | 已修复 | — |
| R-25 残留英文 | 基本修复 | Qt 标准按钮见 C-05；规则窗口方向下拉显示原始 ID（`rules_window.py:349`）见 C-08 |
| R-26 其他小问题 | 已修复 | 死键见 C-14 |

第二轮第 5 节（证明力不足的测试）大部分已改写。剩下两处：R-16 的"打开对话框"路径和 R-19 都没有经过真实对话框构造的测试，由 N-02、N-03 补上。

### 7.2 新发现的问题

#### N-01 Jieba 探测失败时 `self_test` 抛 AttributeError，误报核心检查失败（P2，回归，已复现）

**位置**：`plugin/OpenCCForSigil/opencc_backend/backend.py` 约第 328 行：`error = self._jieba_error`。这个属性在 141f486 重构 JiebaProbe 时被删除，现在应该用第 225 行的 `jieba_error` 属性。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/n1_self_test_jieba_error.py
```
- 当前输出：`error: self-test failed: 'OpenCCBackend' object has no attribute '_jieba_error'`，`config: False s2t_smoke: False`
- 期望输出：error 是 Jieba 失败的原因；`config: True s2t_smoke: True`

**修改步骤**：把 `error = self._jieba_error` 改成 `error = self.jieba_error`。

**测试**（`tests/unit/test_optional_jieba.py`）：找到调用 `backend_with_loader(..., fail_optional=True)` 后断言 `not result.passed` 的测试，补充断言：`result.checks["config"] is True`、`result.checks["s2t_smoke"] is True`、`"_jieba_error" not in (result.error or "")`。

**影响**：工具菜单的"自检"、`tools/package_smoke.py`、`tools/verify_runtime_subset.py` 在 Jieba 不可用的机器上会报核心转换失败。

---

#### N-02 打开设置对话框时，以 t2s 结尾的已保存中转链被换成 `s2hk>t2s`（P1，R-16 遗留，已复现）

**位置**：`plugin/OpenCCForSigil/ui/run_options.py`，`_update_enablement` 开头：

```python
current_chain = self.combos["pivot_chain"].currentData()
if current_chain:
    self._preferred_pivot_chain = _pivot_chain_key(current_chain)
```

**原因**：`bind()` 在对话框把方向设为默认值**之前**就调用了 `update_enablement`。这时方向下拉框是第一项 s2t，中转链下拉框被填成以 s2t 结尾的链并选中第一项；等方向切到 t2s 时，上面三行用这个临时值覆盖了用户保存的 `_preferred_pivot_chain`。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/n2_pivot_chain_on_open.py
```
- 当前输出：前两行 `-> values ('s2hk', 't2s')`
- 期望输出：每行的 values 和 prefs 都等于传入的链，例如 `('s2tw', 't2s')`

**修改步骤**：
1. 删除上面这三行。用户手动选择中转链时，`_pivot_chain_changed` 已经会更新 `_preferred_pivot_chain`。
2. 确认 `_pivot_chain_changed` 连在中转链下拉框的 `currentIndexChanged` 上，并且在 `_update_enablement` 重建下拉框时被 `blockSignals(True)` 屏蔽（现有代码已经这样做）。

**测试**（`tests/unit/test_run_options.py`）：把复现脚本改写成参数化测试，用 `fake_qt.make()` 经真实 `_ConversionConfigDialog.__init__` 构造，断言 `values()["pivot_chain"]` 和 `preference_values()["pivot_chain"]` 都等于传入的链。四组参数照抄脚本。再加一个用例：打开后用户手动选另一条链，再切换方向并切回，断言保留的是用户手动选的那条。

---

#### N-03 未修改的方案仍显示"（已修改）"，不能重命名或删除（P2，R-19 遗留，已复现）

**位置**：`ui/run_options.py` 的 `_update_profile_label`，以及 `app/settings.py` `pick_profile` 里传给方案窗口的 `active_profile=`。

**原因**：比较的一侧是 `panel.values()`，里面有 `diagnose_mixed`、`detailed_classification` 两个键；另一侧是方案本身，没有这两个键（值为 `None`）。所以没有这两个键的方案永远"不相等"。首次运行的内置 Conservative 方案也会显示"(modified)"。

**复现**：
```sh
.venv/bin/python docs/reviews/2026-09-24/scripts/round3/n3_profile_modified_label.py
```
- 当前输出：`label: Current profile: Mine (modified)`，`rename enabled: False delete enabled: False`，`diff: {'detailed_classification': (None, True), 'diagnose_mixed': (None, True)}`
- 期望输出：label 不含 `(modified)`，两个按钮都可用，`diff: {}`

**修改步骤**：
1. 找到 `_profile_signature`（`ui/profile_window.py`）。在它计算签名之前，给两侧都用面板的默认值补齐缺失的键：写一个函数 `_with_panel_defaults(options)`，对 `diagnose_mixed`、`detailed_classification` 这类"方案里可以没有、面板里一定有"的键，缺失或为 `None` 时填入面板的默认值（默认值从 `RunOptionsPanel` 初始化时用的同一处取，不要另写一份常量）。
2. `_update_profile_label` 和 `pick_profile` 两处比较都经过这个函数。

**测试**（`tests/unit/test_profile_window.py`）：把复现脚本改写成测试。**不要**把 `panel.values` 打桩成 `profile_options(active)`（那是同义反复，第二轮已经指出过），必须使用真实 `RunOptionsPanel.values()`。断言 label 不含"modified"对应的翻译文字、`rename_button.isEnabled()`、`delete_button.isEnabled()`。再加一个用例：改动面板上的引号选项后，label 显示已修改。

---

#### N-04 不良构 XHTML 的列号少 1（P3）

**位置**：`plugin/OpenCCForSigil/document/validation.py`，`column = exc.offset - …`。expat 的 `offset` 从 0 开始。

**修改步骤**：列号改为从 1 开始（`+ 1`），与行号一致。更新断言列号的现有测试（`grep -rn "column" tests/unit/test_xhtml_validation.py`），只改期望值。

---

#### N-05 Jieba 探测期间主线程被卡

合并到 D-05，不单独处理。

---

#### N-06 对话框静态检查可能空跑（P3）

**位置**：`tests/unit/test_dialog_construction.py` 用相对路径 `Path("plugin/OpenCCForSigil/ui")`。从其他目录运行 pytest 时 glob 为空，测试直接通过。

**修改步骤**：
1. 改成 `Path(__file__).resolve().parents[2] / "plugin" / "OpenCCForSigil" / "ui"`。
2. 加一句 `assert files`（glob 结果非空）。
3. 把检查范围扩展到 `opencc_backend/`，并增加对 `self.<attr>` **读取**的检查：属性必须在类里被赋值过，或者是方法或 property（这样能抓到 N-01 这类问题）。如果误报太多，只对 `opencc_backend/backend.py` 开启。

---

#### N-07 引号和汉字合并成一个变更时，块内引号不平衡也不提升为 REVIEW（P3）

**位置**：`core/planner.py`，不平衡块提升风险的地方（`unbalanced_blocks` 附近），现在只看 `category == "quotation"`。

**修改步骤**：提升条件改为 `change.category == "quotation"` **或** `"includes QuotationTransform" in (change.attribution_method or "")`。做这一条时，注意 A-02 + D-01 之后这类合并变更会更多。

**测试**（`tests/unit/test_quotation_pairing.py`）：`<p>"后"乙"</p>`（corner 模式）中包含 `「後` 的变更风险为 REVIEW。

---

#### N-08 R-02 第 3 点缺测试（P3）

**问题**：把 `controller.py` 改回 `OpenCCBackend(selected_config)`（不传会话级 probe）时，所有测试仍然通过。

**修改步骤**：在 `tests/integration/test_jieba_probe_flow.py` 加一个测试：monkeypatch `OpenCCBackend.__init__` 记录传入的 `jieba_probe`（参数名以实际为准），走一遍"设置 → 返回 → 设置 → 预览"，断言所有后端收到的是同一个 probe 对象。

---

#### N-09 第二轮的部分复现脚本已过时（P3）

`docs/reviews/2026-09-23/scripts/round2/` 下的 `probe_check.py`、`s1_jieba_loop.py` 引用了已删除的 API，`preview_repro.py` 开头的 "BLOCKER" 检查也已过时。在 `docs/reviews/2026-09-23/README.md` 的"说明"里加一句"以下脚本对应 263f657，在 4706a92 之后不再适用：…"。不要修改或删除这些脚本。
