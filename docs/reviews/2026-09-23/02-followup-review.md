# v0.1.0 修改复审（第二轮）：剩余问题与修改规格

日期：2026-09-23。基线：`main` @ `263f657`（在 `b2f674b` 之后的 25 个提交）。对照规格：同目录下的 `01-ui-logic-spec.md`（下称"第一轮规格"）。状态：待实施。

写法与第一轮规格一致：每条给出位置、证据、修改要求和验证方法。编号 R-xx 为本轮新发现；括号里是它对应的第一轮条目。复现脚本在同目录的 `scripts/` 下，用法见 `README.md`。

---

## 1. 结论

**有两个阻断问题，当前 `263f657` 不能发布**：
- 只要有任何变更，预览对话框就无法构造，每次转换都会以"意外错误"结束（R-14）。
- 范围选择为"单个文件"时，"继续"按钮始终不可用（R-15）。

现有测试都没有发现这两个问题：单元测试用 `object.__new__` 绕过 `__init__`，集成测试又把 `show_preview` 整个替换掉了。

大部分修改已正确落地：
- `.venv/bin/python -m pytest -q` 共 322 项通过（71.6 秒）；
- 第一轮复现的三个核心问题已修复：引号跨内联标签/规则切分的配对、长文本中 `>` 被转义、规则覆盖层的逐节点重复开销（2000 条规则的基准从约 36.5 秒降到 0.6 秒）。

仍需修改的 P1（除上面两个阻断外还有 7 项）：

- **流程与数据一致性**
  - 部分写回后若进度界面抛错，会被报告成"没有文件被修改"（R-04）。
  - 从设置或无变化结果返回时，转换方向被重置为 s2t（R-03）。
  - 第二轮循环里 Jieba 状态丢失，首选的 Jieba 配置被静默换成标准配置（R-02）。
- **引号**：闭引号仍被归类为 OpenCC 字符变更，不平衡时的风险提升漏掉了闭引号（R-01）。
- **设置与规则**
  - 在真实 Qt 中，已保存的强制中转链加载后会被换成第一条链（R-16）。
  - 规则集改名后再新建同名集合，新集合会被删除（R-18）。
- **误操作**：预览中按回车会直接触发"应用"（R-17）。

另有 P2 12 项、P3 5 项。所有阻断和 P1 问题都已用脚本复现：UI 类问题通过一个模拟真实 Qt 信号行为的假 Qt 复现，核心类问题直接在真实 payload 上复现。

---

## 2. 第一轮条目状态

| 条目 | 状态 | 说明 |
| --- | --- | --- |
| L-01 引号配对 | 部分完成 | 块级重置、属性独立、规则区间推进状态均正确；闭引号分类错误（R-01）；实体引号不参与配对（R-11） |
| L-02 最小转义 | 完成 | `attribute_quote` 已加入；跨替换边界拼出 `]]>` 时会阻断写回（R-10，安全失败） |
| L-03 规则集持久化 | 完成 | 测试绕过了 `edit_rules`（第 5 节） |
| L-07 规则编译 | 部分完成 | 与旧 `lock_spans` 等价（2000 例模糊测试无差异）；每个文件重建一次（R-07）；计数测试不会失败（第 5 节） |
| L-08 Jieba 后台探测 | 部分完成 | 首次对话框正确；循环后失效（R-02）；非守护线程延迟退出（R-13）；工具按钮同步阻塞（R-02） |
| L-09 诊断短路 | 完成，有回归 | 强制中转时误报 MIXED_SCRIPT（R-06） |
| L-10 进度合并 | 完成 | 合并测试不会失败（第 5 节） |
| L-11 错误对话框 | 部分完成 | 写回边界的"是否已写入"可能错误（R-04） |
| L-12 损坏文件恢复 | 部分完成 | 新版 schema 被隔离（R-05）；整份旧偏好覆盖新写入值（R-08） |
| L-13 跳过不良构源文件 | 部分完成 | 行列号偏移且界面不显示（R-09） |
| L-16 保留期清理 | 完成 | — |
| U-01 返回范围 | 部分完成 | 方向丢失（R-03）；Jieba 丢失（R-02） |
| U-02 Checkpoint 提示 | 完成 | 需宿主实测 |
| U-03 丢弃确认 | 完成 | Esc/关闭需宿主实测 |
| U-06 无变化直出结果 | 完成 | 返回时方向重置（R-03） |
| U-10 写回进度 | 代码完成 | 引入了 R-04；集成测试证明力弱（第 5 节） |

UI 窗口类条目：

| 条目 | 状态 | 说明 |
| --- | --- | --- |
| U-04 预览表格 | 完成，有缺陷 | 筛选计数不刷新（R-23）；目标文本以转义形式显示（R-26） |
| U-05 决定效率 | 部分完成 | 自动前进、快捷键、按 change_id 恢复选中均正确；回车触发应用（R-17）；应用按钮文案不全（R-24） |
| U-07 语言标签组 | 完成 | — |
| U-08 设置对话框 | 部分完成 | 分组、折叠、工具菜单、QDialogButtonBox、自检表格均已实现；布局顺序颠倒（R-21）；Jieba 下的强制中转（R-22）；残留英文（R-25） |
| U-09 范围对话框 | 部分完成 | 单文件模式"继续"不可用（R-15，阻断）；其余要求已实现 |
| U-11 结果对话框 | 完成 | — |
| U-12 方案窗口 | 部分完成 | "已修改"恒显示导致当前方案不能重命名/删除（R-19）；"另存为"无重名检查（R-26） |
| U-13 规则窗口 | 完成，有缺陷 | 改名后删除新集合（R-18）；检查器英文（R-25） |
| U-14 历史窗口 | 完成 | — |
| U-15 i18n | 部分完成 | 私有翻译表已移除，目录键与占位符一致；残留英文（R-25）；37 个运行时键未列入必需键（R-26） |
| L-04 Jieba 方案 | 完成（改为只读摘要） | — |
| L-05 中转链与联动 | 部分完成 | 真实 Qt 下链被重置（R-16）；禁用控件被取消勾选（R-16、R-20）；Jieba 配置（R-22） |
| L-06 添加/更新 | 完成 | — |
| L-14 导入预览 | 完成 | — |
| L-15 检查器参数 | 完成 | — |
| L-17 白名单与"已修改" | 部分完成 | 白名单与 attributes 重建正确；"已修改"判断错误（R-19） |
| C-01 结构整理 | 部分完成 | `ui/qt.py`、去全局变量、删占位模块已完成；误删 `_export_service` 导致 R-14；`_enum_value` 重复与遗留分支（R-26） |

---

## 3. 核心与流程问题

### R-01 闭引号被归类为 OpenCC 字符变更（P1，已复现；对应 L-01）

**位置**：`core/converter.py:77-80`。只有 `transform_quotations(source_part, mode) == target_part` 时才归类为 `quotation`。这个判断是无状态的：单独的 `"` 总是映射成开引号 `「`，所以 `"` → `」` 永远匹配不上，落入 `category="character"`、`rule_source="OpenCC:s2t"`、风险 LOW。

**复现**（corner 模式，s2t）：

```text
<p>"他说<em>你好</em>"</p>     闭引号：'"' → '」'  character  OpenCC:s2t  LOW
<p>"甲<span>"x"</span>乙"</p>  两个闭引号都是 character / OpenCC:s2t / LOW
```

**后果**
- 预览把引号变化记在 OpenCC 名下，按类别筛选"引号"时看不到闭引号。
- 块内引号不平衡时，只有开引号被提升为 REVIEW，闭引号仍是 LOW，不满足 L-01 第 4 点"块内所有引号变更提升为 REVIEW"。
- L-01 修复后，内联标签或规则区间之后的每个闭引号都会单独成为一个 diff 操作，这类误分类因此变多。

**修改要求**
1. 让 `QuotationPairer` 记录本次改写过的偏移集合（相对当前文本段），由 `convert` 返回给调用方。
2. 生成 `TokenChange` 时，若变更区间只覆盖被 pairer 改写过的字符：`category="quotation"`、`rule_source="QuotationTransform"`。这个判断不再依赖无状态的重新计算。
3. 变更区间同时包含 OpenCC 字符变化和引号变化时，保留 OpenCC 归因，并在 `attribution_method` 中注明同时包含引号变化。
4. 不平衡时的 REVIEW 提升作用于该块内所有 `category="quotation"` 的变更，包括闭引号。

**验证**
- 在 `tests/unit/test_quotation_pairing.py` 增加断言：跨内联用例中两个引号都是 `quotation`/`QuotationTransform`；`<p>"甲"乙"</p>` 中三个引号变更都是 REVIEW。
- 加一个开启 `detailed_classification=True` 的同样用例。

---

### R-02 第二轮循环中 Jieba 状态丢失（P1，已复现；对应 L-08、U-01）

**位置**
- `app/controller.py:199`：`available_configs` 在循环外计算一次，通常此时探测尚未完成，列表里没有 `_jieba` 配置。
- `app/controller.py:218`：对话框的 `jieba_probe=backend`。
- `app/controller.py:273-275`：方向改变时，backend 被替换成一个从未探测过的新 `OpenCCBackend`，状态为 `not_started`。
- `ui/preview_window.py:1629-1665` `_apply_jieba_state`：`not_started` 既不算"进行中"也不算"不可用"，继续按钮保持可用。

**复现**（真实 payload）：第一次对话框中 Jieba 为 `available`，用户选 `s2t_jieba` 并从预览返回。第二次对话框得到：

```text
{'default': 's2t_jieba', 'backend': 's2t_jieba', 'state': 'not_started', 'jieba_in_list': []}
dialog#2: 状态=不可用+请重选  复选框禁用  继续可用  最终配置=s2t
```

也就是说，这次会话里再也无法选择 Jieba，首选的 Jieba 配置被静默换成了 s2t，违反 L-08 第 4 点和不变量 15 "不静默回退"的要求。

**附带问题**：`settings.bind_run(..., 新 backend)`（`controller.py:279、395`）之后，方案窗口和规则窗口会调用 `available_configs()`，在 UI 线程上同步执行约 1.7 秒的探测（`backend.py:121-133`），界面无任何反馈。

**修改要求**
1. 探测结果归一个会话级对象持有，例如 `JiebaProbe`，由 controller 创建一次。它只依赖已校验的 payload，与当前 backend 的配置无关。
2. 每轮循环都从这个对象重新计算 `available_configs_nonblocking()`，并把同一个对象传给对话框、方案窗口和规则窗口。
3. 新建的 backend 不再自行探测，直接读取这个对象的结果。
4. 对话框中，若首选配置是 Jieba 且状态为 `not_started` 或 `pending`，继续按钮一律禁用，直到得到明确结果。
5. 方案和规则窗口需要配置列表时，若探测未完成，使用非阻塞列表，并在界面上标注"Jieba 检测中"，不在 UI 线程等待。

**验证**
- 新增集成测试（真实 payload，参照 `tests/integration/test_jieba_probe_flow.py`）：选 Jieba → 预览返回 → 第二次对话框状态为 `available`，列表含 Jieba 配置，最终配置仍为 `s2t_jieba`。
- 对话框单测：`Probe("not_started")` + Jieba 首选 → 继续按钮禁用。
- 计数测试：一次会话中 Jieba 探测只执行一次。

---

### R-03 返回设置或无变化结果时方向被重置（P1，已复现；对应 U-01 第 3 点、U-06）

**位置**：`app/controller.py:229-241`（设置对话框点"上一步"）和 `:368-372`（无变化结果点"返回设置"）没有更新 `default_config`。只有从预览返回的路径更新了（`:394`）。

**复现**：第二次对话框收到 `default_config='s2t'`，而 `preferences.json` 中是 `last_conversion_config: s2tw`；`quotation_mode='corner'` 等其他选项都恢复了，只有方向被静默重置。

**修改要求**：这两条路径都把 `default_config` 设为本次对话框的当前选择。更稳妥的做法是在 `reselect_scope` 之后统一用 `_preferred_config(preferences, ...)` 从刚保存的偏好中重新推导，三条返回路径共用一处逻辑。

**验证**：扩展现有的"无变化返回"和"返回范围"集成测试，断言第二次调用 `choose_conversion_config` 时 `default_config == "s2tw"`。

---

### R-04 部分写回后可能被报告为"没有文件被修改"（P1，已复现；对应 L-11、U-10）

**位置**
- `core/workflow.py:458-468`：U-10 让 `commit` 在交给 `SigilBookAdapter.commit` 迭代的生成器里调用 UI 的 `progress()`。
- `sigil/adapter.py:174`：迭代（`next()`）位于 adapter 的 `try` 之外。某个文件写入成功后，进度回调若抛出异常，会作为普通异常逃出，而不是 `CommitError`。
- 通用异常分支据此报告 `files_written`，该值只在 `controller.py:463` 赋值，此时仍为 0。

**复现**（故障注入：进度回调在 `("committing", 1)` 时抛异常）：

```text
book.writes = ['a']
show_error files_written = 0  kind = UNEXPECTED_ERROR
summary status/files_changed = failed 0
```

书中已写入一个文件，界面却说没有修改，违背 L-11 对"是否已写入"的承诺。这是 U-10 第 3 点引入的新问题。

**修改要求**
1. 写回阶段的进度回调改为尽力而为：在 `write_items` 中用 try/except 包住回调，失败时记录 `progress_failed` 事件，不中断写回。
2. `SigilBookAdapter.commit` 把 `next()` 也纳入异常处理：任何异常都转换为带 `committed_file_ids` 的 `CommitError`。
3. controller 的通用异常分支以 adapter 实际记录的已提交 ID 为准计算 `files_written`，不再依赖局部变量。
4. 任何路径上，只要 `writefile` 至少成功一次，就必须走 partial-failure 结果或成功结果，不能显示"没有文件被修改"。

**验证**
- 把故障注入脚本改成集成测试：结果只能是 partial-failure（`committed_file_ids == ["a"]`）或两个文件都写入成功。
- 断言在存在写入时，`show_error(files_written=0)` 从不出现。
- 再加一例：结果对话框本身抛异常时，summary 仍为 success。

---

### R-05 新版 schema 的方案与规则集被当成损坏文件隔离（P2，已复现；对应 L-12）

**位置**
- `app/settings.py:41-56`：加载方案遇到未来 schema 时，`ProfileValidationError`（`profiles.py:374`）导致文件被重命名为 `.corrupt-*`，并清除 `profile_id`。
- `app/settings.py:121-140`、`:272-282`：规则集同样处理（`rules/store.py:152`）。

**复现**：`profiles/mine.json` 的 `schema_version=2` → 变为 `mine.json.corrupt-20260923T085740Z`，提示 `profile_recovered`。`rules/newer.json` 同样被改名，提示只说"规则集缺失"，没有提到备份。回到新版插件后，这些文件已经找不到了。只有偏好文件实现了"未来 schema 只读"的处理。

**修改要求**
1. 隔离前先判断：`schema_version` 为大于当前支持版本的整数时，不隔离、不改名，跳过该文件并提示"需要更新版本的插件"，保留偏好中的 `profile_id`。
2. 只有 JSON 解析失败或结构不合法时才隔离。
3. 规则集被隔离时，提示中写明备份文件名。

**验证**
- 未来 schema 的方案和规则集：文件内容与 mtime 均不变，目录中不出现 `*.corrupt-*`，提示出现一次。
- 真正损坏的文件仍被隔离，提示含备份名。

---

### R-06 强制中转时误报混合脚本（P2，已复现；对应 L-09）

**位置**：`core/converter.py:57-58`。配置为 s2t 或 t2s 时传入 `known_output=official`，但启用强制中转后，`official` 实际是 `s2t(t2s(text))`，不是单纯的 s2t 输出。

**复现**：配置 s2t、中转链 `("t2s","s2t")`，输入繁体 `裡面`，中转结果为 `裏面`，得到 `MIXED_SCRIPT`。实际诊断应为 traditional；不启用中转时没有误报。这是相对基线的回归。

**修改要求**：两处 `known_output*` 参数都加条件 `and not request.pivot_chain`。

**验证**：把上述用例加入 `tests/unit/test_diagnostics.py`：启用中转时诊断结果与不启用时一致。

---

### R-07 规则覆盖层每个文件重建一次（P2，已复现；对应 L-07）

**位置**：`core/planner.py:54` 每次 `build_conversion_plan` 都新建 `OfficialBackendConverter`，覆盖层缓存随之按文件重建。每次构建（1976 条规则）约 10 ms。

**复现**：

| 书籍形态 | 0 条规则 | 1976 条规则 | 覆盖层构建次数 |
| --- | --- | --- | --- |
| 300 个文件 × 10 个节点 | 0.31 s | 3.46 s | 300 |
| 1000 个文件 × 3 个节点 | — | 10.9 s | 1000 |

节点分散在多个文件时，达不到 L-07 的"≤ 3 秒"目标。`tools/benchmark_rules.py` 使用单个 converter 和恒等后端，绕过了 planner，所以测不出这个问题（报告 0.073 s）。

**另一个既有问题**：`core/planner.py:194` 的 `_absolute_change` 对每个变更执行 `source.rfind("<![CDATA[")`，单个大文件时复杂度为二次。一个 3000 节点的文件中，这一项占 4.4 秒总耗时中的 3.1 秒。

**修改要求**
1. 每次 `plan()` 或 worker 的 `work()` 调用只创建一个 converter（含覆盖层缓存），作为参数传给 `build_conversion_plan`。对象始终留在 worker 线程内，线程归属不变。
2. CDATA 判断改为：每个文件先扫描一次 CDATA 区间并排序，之后对每个变更用 `bisect` 查询。
3. 缓存键不能只信任请求中声明的 `rules_hash`（R-12）。

**验证**
- `tools/benchmark_rules.py` 改为经由 `ConversionWorkflow.plan` 计时，覆盖"300 个文件 × 10 个节点"和"单文件 3000 个节点"两种形态。验收：1976 条规则时两者都 ≤ 3 秒，三次取中位数。
- 计数测试：多文件规划时覆盖层构建次数为 1。

---

### R-08 保存整份旧偏好会覆盖本次运行中写入的新值（P2，已复现；对应 L-12、U-08）

**位置**
- `app/controller.py:243`（以及 `:158`）：取消设置对话框时保存 `scope_preferences`，这份数据是对话框打开之前构建的。
- 它会覆盖 `save_run_ui_preferences`（`:209-213`）刚写入的 `run_options_advanced_expanded` 和 `conversion_dialog_size`，以及 `settings.hide_checkpoint_notice`（`settings.py:311-314`）写入的 `checkpoint_notice: False`（后者只在宿主没有 `bk.getPrefs` 时生效）。

**复现**：取消后偏好中 `checkpoint_notice: None`，`ui: {'language': 'en'}`，之前写入的值丢失。

**同类疑似问题**（阅读推断，未复现）
- `pick_profile` 删除方案后会移除磁盘上的 `profile_id`（`settings.py:157-161`），随后取消又把旧值写回，下次启动出现一次多余的"方案已恢复"提示。
- 未来 schema 只读模式下，`reselect_scope` 从磁盘重新加载，第一轮选择的选项会丢失。

**修改要求**
1. 新增 `UserDataStore.update_preferences(changes: Mapping)`：读取磁盘最新内容，合并修改后原子写回。只读模式下只更新内存副本。
2. controller 与 settings 中所有"保存整份缓存字典"的调用都改为提交变更字段。

**验证**：复现脚本改为测试：隐藏 Checkpoint 提示 → 取消 → 偏好中 `checkpoint_notice is False`，`ui` 保留窗口尺寸与折叠状态。删除方案 → 取消 → `profile_id` 不回来。

---

### R-09 不良构源文件的行列号偏移且界面不显示（P2，已复现；对应 L-13）

**位置**
- `document/validation.py:36-46`：校验副本去掉 DOCTYPE 与 XML 声明时连同其中的换行一起去掉，并在前面加上 `<validation-root>`。
- `ui/preview_window.py:461-465` 及预览摘要只显示本地化诊断码和数量，没有 L-13 第 2 点要求的"（第 L 行第 C 列）"。

**复现**
- Sigil 常见的两行 EPUB2 DOCTYPE 头，错误实际在第 5 行，报告为第 4 行。
- 第 1 行的错误列号多出包装元素的 17 个字符：`<p>汉字<br></p>` 报告为第 28 列。

**修改要求**
1. 去掉声明时用等量的换行替换；第 1 行列号减去包装前缀长度。
2. `Diagnostic` 携带结构化的 `line`、`column` 字段，UI 据此按 i18n 模板渲染，不解析错误字符串。
3. 预览顶部的"已跳过文件"列表显示 href 与行列号。

**验证**
- 带两行 DOCTYPE、错误在第 5 行第 10 列：诊断为 `line=5`、`column=10`。
- 第 1 行错误列号正确。
- 预览行文本含"第 5 行"。

---

### R-10 替换后与相邻文本拼出 `]]>` 时阻断写回（P3，已复现；对应 L-02）

**复现**：源文本 `<p>]]称呼</p>`，exact 规则"称呼"→`>`，拼出 `]]>`，verify 阻断。基线版本用 `html.escape` 把 `>` 转成 `&gt;`，可以写回。

这种情况只在用户规则很特殊时出现，而且是安全失败（零写入），因此列为 P3。

**修改要求**：`_absolute_change` 中，若 `source[:start]` 以 `]` 或 `]]` 结尾且 target 以 `>` 开头，或 target 以 `]]` 结尾且 `source[end:]` 以 `>` 开头，则把相关的 `>` 转义为 `&gt;`。

**验证**：上述用例写回成功，输出为 `]]&gt;`；其他 `>` 保持原样（L-02 的测试不变）。

---

### R-11 实体形式的引号不参与配对（P3，已复现；对应 L-01）

**复现**：`<p>&#34;甲"</p>` → `&#34;甲「`，并被标记 QUOTE_UNBALANCED。`&quot;`、`&#8220;` 同样如此。有 REVIEW 标记，用户能看到。

**修改要求**：同一块内，相邻 target 之间出现的引号实体（`&quot;`、`&#34;`、`&#x22;`、`&#8220;`、`&#8221;` 等）以 `mutate=False` 送入 pairer 推进状态。实体本身不改写。

**验证**：`<p>&#34;甲"</p>` → `&#34;甲」`，无 QUOTE_UNBALANCED。

---

### R-12 覆盖层缓存键只信任声明的哈希（P3，潜在问题；对应 L-07）

**复现**：同一个 converter 收到声明了相同 `rules_hash`、但规则不同的请求时，返回旧的覆盖层，不报 `rule snapshot hash mismatch`；新 converter 会正确报错。目前每个 converter 只服务一个请求，所以触发不了；R-07 把缓存提升到运行级别后就会变得可触发。

**修改要求**：缓存条目同时保存规则元组。命中时要求 `request.rules_snapshot.rules is cached_rules`；不是同一对象时重新校验哈希。

**验证**：同一 converter、同一声明哈希、不同规则 → 抛出 `rule snapshot hash mismatch`。

---

### R-13 提前取消时进程退出可能被延迟（P3，阅读推断）

**位置**：Jieba 探测使用非守护线程的 `ThreadPoolExecutor` worker，解释器退出时会等待它结束。在范围对话框取消，或宿主没有文本 API 时，插件进程最多可能多停留约 2 秒。

**修改要求**：探测改用守护线程加 `concurrent.futures.Future`；或在退出路径上 `shutdown(wait=False, cancel_futures=True)`。与 R-02 一起实现。

**验证**：模拟探测耗时 2 秒时，范围对话框取消后 `Controller.run()` 在 0.5 秒内返回。

---

## 4. UI 窗口问题

本节问题用 `scripts/round2/fakeqt.py` 复现。它是一个宽松的假 Qt，按真实 Qt 的规则发出信号：
- `QComboBox.clear()` 和向空下拉框插入第一项时，会发出 `currentIndexChanged`；
- 单选按钮互斥；
- 槽函数参数少于信号参数时照样调用。

它不能替代真实 Qt。标注"需宿主实测"的项目仍要在 Sigil 中确认。

### R-14 预览对话框无法构造（阻断，已复现；对应 C-01）

**位置**：`ui/preview_window.py:968` 调用 `self._export_service()`，但该方法在提交 `1efe4e0`（C-01"纯重构"）中被删除，整个 `ui/` 目录中已无定义（`hasattr(_PreviewDialog, "_export_service")` 为 False）。

**后果**：只要本次转换有任何变更，`_PreviewDialog.__init__ → _build()` 就抛出 `AttributeError`，经 `controller.py:538` 的通用分支显示"意外错误"。用户永远走不到预览。

**为什么测试没发现**：单元测试用 `object.__new__` 绕过 `__init__`；集成测试把 `ui.preview_window.show_preview` 整个替换掉了。

**修改要求**
1. 改为 `self.export_button.setEnabled(getattr(self._services, "export_preview", None) is not None)`，或恢复一个等价的私有方法。
2. 把 `scripts/round2/fakeqt.py` 整理后放入 `tests/support/fake_qt.py`，作为测试基础设施。新增端到端构造测试，通过真实 `__init__` 构造以下每个对话框：
   - `_PreviewDialog(fake_qt, planned, previews, translator, services)`，分别在 services 为 None 和有 `export_preview` 时各测一次；
   - `_ScopeDialog`、`_ConversionConfigDialog`、`ProfileManagerDialog`、`RuleManagerDialog`，以及历史窗口。
3. 新增静态检查测试：扫描 `ui/*.py` 中所有 `self.<name>(` 调用，断言每个都能在类或其基类中找到定义。`scripts/round2/selfcalls.py` 是一个可参考的实现。

**验证**
- 上述构造测试在修复前失败、修复后通过。
- 宿主实测：任意一本有变更的书能进入预览。

---

### R-15 "单个文件"模式下"继续"始终不可用（阻断，已复现；对应 U-09）

**位置**
- `ui/preview_window.py:2048`：单文件模式把所有条目设为未勾选，改用"当前行"表示选择。
- `ui/preview_window.py:2070-2080` `_update_analyze_enabled`：仍按 `len(self._checked_ids())` 判断，于是 `count == 1` 永远为假。

**复现**：初始选择 `('a',)`，模式为单个文件：`selected_ids() == ('a',)`，计数标签显示"已选择 1 / 3"，但继续按钮禁用；点击 b 行后仍禁用。这是最常见的使用方式（在 Sigil 中选中一个文件后启动），"返回范围"回到单文件选择时同样受影响。

**修改要求**
1. `_update_analyze_enabled` 改用 `len(self.selected_ids())`。书脊/全部模式的判断保持不变。
2. （P3，需宿主实测）`setCheckState(Unchecked)` 仍会写入 `CheckStateRole` 数据。`QStyledItemDelegate` 只要该数据有效就会画出勾选框，与 flags 无关，所以单文件模式下的勾选框实际并未隐藏。改为 `item.setData(Qt.CheckStateRole, None)`。

**验证**
- 新增测试：初始一个选中项构造 `_ScopeDialog`，继续按钮可用；点击另一行后仍可用，且 `selected_ids()` 为新行。
- 切到"全部"再切回单文件，继续按钮可用。

---

### R-16 已保存的强制中转链在真实 Qt 中被重置（P1，已复现；对应 L-05）

**位置与机制**
- `ui/run_options.py:246`：`_update_enablement` 清空并重新填充中转链下拉框时，信号处于连接状态。向空下拉框插入第一项时 Qt 会发出 `currentIndexChanged(0)`，触发 `_pivot_chain_changed`（`:295`）。这会在 `findData` 之前把 `_preferred_pivot_chain` 覆盖为排序后的第一条链。
- `ui/run_options.py:326-327`：`_tool("profiles")` 先设置复选框再调用 `_set_config`，且对当时处于禁用状态的控件设为 False。
- `ui/run_options.py:260`、`:266`：对禁用的控件调用 `setChecked(False)`，违反 L-05 第 3 点"被禁用的控件保留值"。

**复现**

```text
方向 t2s、链 s2tw>t2s 的方案 → 重新加载后链变为 ('s2hk','t2s')（打开对话框时与"方案→使用"时都会发生）
当前方向 tw2t（无可用链）时加载 s2tw 强制中转方案 → force_pivot=False
```

**为什么测试没发现**：`test_profile_chain_list_loads…` 使用 s2tw（只有一条可用链），而且测试用的假下拉框从不发出信号。

**修改要求**
1. 重新填充下拉框期间用 `blockSignals(True)`/`finally: blockSignals(False)` 包住。填充后再按 `_preferred_pivot_chain` 用 `findData` 选中。
2. `_tool("profiles")` 先调用 `_set_config(profile.conversion)`，再应用各选项值。应用值时不以 `isEnabled()` 为条件。
3. 任何地方都不要为了"禁用"去取消勾选。禁用只影响 `values()` 的输出（对禁用项输出屏蔽值）。
4. 加载失败（例如 Jieba 不可用）时先校验后应用，不要留下半应用状态（见 R-26）。

**验证**：用 `tests/support/fake_qt.py`（会发出信号的下拉框）测试：
- t2s + `s2tw>t2s` 的方案在打开对话框和"方案→使用"两条路径下都保持原链；
- 从 tw2t 加载 s2tw 强制中转方案，force_pivot 保持为 True；
- 禁用的复选框在重新启用后恢复原勾选状态。

---

### R-17 预览中按回车会触发"应用"（P1，代码确认；对应 U-05 第 5 点）

**位置**：`ui/preview_window.py:934-937` 对应用按钮调用了 `setDefault(True)` 和 `setAutoDefault(True)`，其他按钮都没有 `setAutoDefault(False)`。`QAbstractItemView` 不处理回车键，事件交给 `QDialog`，后者点击默认按钮。所以全部决定完成后，在表格里按回车就会直接应用。

**修改要求**：遍历预览对话框中所有 `QPushButton`，调用 `setAutoDefault(False)` 和 `setDefault(False)`。预览窗口不设默认按钮。

**验证**
- 测试：构造对话框后，所有按钮的 `autoDefault` 与 `default` 都为 False。
- 宿主实测：全部决定后在表格中按回车，不会应用。

---

### R-18 规则集改名后再新建同名集合，新集合被删除（P1，已复现；对应 U-13）

**位置**：`app/settings.py:221-225`。规则窗口返回后，先保存结果中的各规则集，再删除 `old_id.json`。

**复现**：改名 A→B，再新建一个 A。结果中有 `('default','B','A')`，但磁盘上只剩 `B.json`，当前方案的 `ruleset_ids` 为 `('B','A')`。新 A 被保存后又被删除，而且方案引用被从 A 改写成了 B。这是静默的数据丢失。

**修改要求**
1. 只删除不在结果集合中的旧 ID。
2. 或者在同一次编辑中禁止复用刚被改名掉的 ID，并在界面上提示。
3. 方案引用的改写只针对真正改名的 ID。

**验证**：测试"改名 A→B 后新建 A"：`A.json` 与 `B.json` 都存在；`ruleset_ids` 为 `('B','A')` 且 A 指向新建集合。

---

### R-19 "（已修改）"恒显示，当前方案不能重命名或删除（P2，已复现；对应 L-17、U-12）

**位置**：`ui/run_options.py:307` 比较 `settings_hash(current_profile(config, values()))` 与 `settings_hash(active)`，两者总是不同：
- 方案中 `language_region` 为 `'auto'`，界面值为 `''`；
- `detailed_classification`、`diagnose_mixed` 以 extras 的形式进入当前方案，而保存的方案中没有这两项。

同一个判断使 `ui/profile_window.py:187` 的 `_can_delete` 恒为 False，当前方案的"重命名""删除"一直禁用。

**复现**：未作任何修改的方案显示"当前方案：Mine（已修改）"，重命名、删除按钮均禁用。

**修改要求**：比较前两侧用同一种方式规范化，例如都经过 `current_profile(active.conversion, profile_options(active))`。或者只比较 `values()` 白名单中的键。

**验证**：新增"未修改 → 不显示标记、可重命名/删除"的测试；保留现有"修改后显示标记"的测试。

---

### R-20 导航文档不在范围内时，NAV 偏好被写成 False（P2，已复现 values 部分；对应 L-05）

**位置**：导航文档不在本次范围内时，`include_nav` 被强制为 False 并由 `values()` 返回，controller 把它存进 `run_options`。下次即使选中了导航文档，该选项也是未勾选。

**修改要求**：与 R-16 第 3 点相同：禁用时不改变勾选状态，`values()` 输出时屏蔽。保存偏好时保存用户原始选择。

**验证**：第一次运行范围不含 nav → 第二次运行范围含 nav，NAV 复选框为勾选。

---

### R-21 设置对话框布局顺序颠倒（P2，已复现；对应 U-08）

**位置**：`ui/run_options.py:137` 使用 `layout.insertWidget(0, scroll)`。结果是方案、文档、高级选项区位于说明文字、转换方向和 Jieba 控件之上，与 U-08 第 1 点规定的顺序相反（基线用的是 `addWidget`）。"工具"一行单独位于按钮框之上，而不是和按钮框在同一行的左侧（P3）。

**修改要求**：按 U-08 顺序排列：方向区 → 方案区 → 文档区 → 高级选项 → 底部一行（左"工具 ▾"，右按钮框）。

**验证**：用 fake Qt 输出布局树，断言控件顺序；宿主截图确认。

---

### R-22 Jieba 配置下提供强制中转，随后又拒绝（P2，已复现；对应 L-05）

**位置**：`option_enablement("s2twp_jieba", {...})` 用 `base_config` 判断，因此启用了强制中转和中转链。但 `app/settings.py:104` 与 `core/converter.py:42` 要求 `chain[-1] == config` 完全相等，而 `FORCE_PIVOT_CHAINS` 中没有以 Jieba 配置结尾的链，点"继续"会报"强制中转不匹配"。

**修改要求**：`option_enablement` 按精确配置匹配链。没有可用链时禁用 force_pivot，并在 tooltip 中说明"Jieba 配置不支持强制中转"。

**验证**：`option_enablement("s2twp_jieba", {"force_pivot": True, ...})` 的 `force_pivot` 与 `pivot_chain` 都不可用。

---

### R-23 预览文件筛选的计数不刷新（P2，已复现；对应 U-04 第 5 点）

**位置**：`ui/preview_window.py:879`。"N 项变更 / M 项待定"只在 `_build` 中计算一次。

**复现**：点"全部接受"后仍显示 "3 changes / 3 undecided"。

**修改要求**：在 `_update_summary` 中对文件筛选各项调用 `setItemText` 刷新计数，不改变当前选中项。

**验证**：全部接受后，每项显示"0 项待定"。

---

### R-24 "应用"按钮文案状态不全（P2，已复现；对应 U-05 第 4 点）

**现状**
- 只有一种文案"Apply changes to {files} file(s)"，没有接受数；
- 接受数为 0 时显示"Apply changes to 0 files"，而不是"完成（不修改）"；
- 有待定项时只在 tooltip 里说明，按钮旁没有可见的"剩余 N 项待定"。

**修改要求**：按 U-05 第 4 点实现三种状态，新增 i18n 键（三语），在按钮左侧放一个状态标签。

**验证**：三种状态各一个断言（中英文）。

---

### R-25 残留英文与 Qt 标准按钮未翻译（P2，部分需宿主实测；对应 U-12、U-13、U-15）

**代码确认**
- `ui/profile_window.py:166-168`：方案摘要显示 "NAV: on/off"、"metadata" 和原始配置 ID。
- `ui/rules_window.py:151-155`：检查器显示 "UserRule:"、`repr()` 引号，以及原始类别和置信度代码。
- `app/settings.py:394`：警告框直接显示 `str(exc)`。
- `app/settings.py:77`：默认方案名为英文 "Conservative"。

**需宿主实测**：`ui/preview_window.py:1562` 使用 Qt 标准"取消"按钮，`QMessageBox.question` 使用标准 Yes/No。这些文字来自 Qt 自带翻译，而插件创建的是普通 `QApplication`，没有安装 QTranslator，中文界面下很可能显示英文 "Cancel/Yes/No"。

**修改要求**
1. 以上文字全部改走 i18n 目录。默认方案名改为按界面语言显示，但不修改其 id `conservative`。
2. 标准按钮改为 `addButton(tr("common.cancel"), RejectRole)` 等自定义文字按钮。
3. `str(exc)` 只放在"详情"里。

**验证**：扩展 `scripts/round2/hardcoded.py` 的思路，写成测试：`ui/` 与 `app/settings.py` 中传给 Qt 文本接口的字符串字面量必须来自翻译函数。已知的文件过滤器等例外列入白名单。宿主上用中文界面截图确认。

---

### R-26 其他小问题（P3）

| 问题 | 位置 | 修改 |
| --- | --- | --- |
| "另存为方案"没有重名检查 | `app/settings.py` `save_profile` | 与方案窗口使用同一重名校验 |
| Jieba 方案"使用"失败时留下半应用状态：复选框已改，`settings.active` 已切换 | `ui/run_options.py` `_tool("profiles")` | 先校验，全部成功再应用（与 R-16 第 4 点合并） |
| 分组决定的反馈文字 `_last_group_feedback` 从不清除 | `ui/preview_window.py` | 下一次非分组操作时清除 |
| 预览中目标文本以转义形式显示（`A&amp;B`） | 预览表格与详情 | 显示时反转义，写回数据不变 |
| 方案/规则窗口调用阻塞的 `available_configs()`，可能等待约 2 秒 | 与 R-02 合并 | — |
| `_enum_value` 重复定义；只为测试保留的 `list_widget` 遗留分支；删除目录后遗留的空行 | `ui/*.py` | 删除遗留分支并改写对应测试 |
| 37 个运行时键（全部 `error.*`、`options.current_profile`、`options.profile_modified`、`settings.*` 等）不在 `tools/validate_artifact.py` 的 `_I18N_REQUIRED_KEYS` 中 | `tools/validate_artifact.py:46` | 加入必需键；`scripts/round2/i18n_check.py` 可列出清单 |
| 5 万条变更时，表格每次 `ResizeToContents` 约 43 ms 的 `data()` 调用，原因是每个 role 都重算 `row_values` | 预览表格模型 | 缓存每行的显示元组；宿主上测量模型重置时的表头调整耗时 |

---

## 5. 证明力不足的测试（需要改写）

| 测试 | 问题 | 改写要求 |
| --- | --- | --- |
| `tests/unit/test_rules_compiled.py` 中"validate_rules ≤ 3 次" | 打补丁的是 `rules.validators.validate_rules`，而 `rules/compiled.py` 与 `rules/conflicts.py` 直接导入了该名字，补丁不生效。强制关闭缓存时计数仍为 0，测试照样通过 | 改为统计 `rules.compiled.CompiledOverlay.build` 调用次数，或在 `rules.compiled`、`rules.conflicts` 模块内打补丁；配合 R-07 增加多文件断言 |
| 同上，等价性测试 | 所有规则源都以"词"开头，只覆盖了一个索引桶 | 随机首字符、重叠前缀、禁用规则、冲突集 |
| `tests/unit/test_worker_planning.py` 进度合并 | worker 在循环第一次检查前就已结束，只触发最后那次无条件回调；不取空队列的实现也只有 1 次调用。在突发更新后保持 300 ms 时，不合并的实现有 1011 次调用 | worker 在突发后等待一个 `Event` 再结束；断言最后一次回调前的更新 index 等于 total，且调用次数远小于 1000 |
| `test_post_preview_progress_covers_noncancellable_writeback` | fake 进度器自己设置标志，controller 在预览后从不调用 `cancelled()`，"关闭被忽略"这部分什么也没证明 | 保留阶段断言；关闭行为以 `test_progress_reporter` 为准，另加 R-04 的故障注入测试 |
| `test_new_ruleset_is_applied_on_the_next_controller_run` | 直接把 `ruleset_ids` 注入配置选项，绕过了 `edit_rules`/`QInputDialog`，没有测到 `values()` 读取 `services.active` | 按第一轮 L-03 验证第 1 步，通过 monkeypatch `QInputDialog.getItem` 与 `show_rules_window` 走真实路径；再加"规则集被删除 → 提示一次"的 controller 级测试 |
| `tests/integration/test_jieba_probe_flow.py` | 使用始终处于 pending 的假后端，不覆盖第二轮循环（R-02）和方向预填（R-03） | 增加 R-02、R-03 的用例 |
| L-13 相关测试 | 未断言 `files_without_changes == 1` | 补上断言 |
| L-02 随机测试 | 只覆盖文本节点 | 增加属性值（两种定界引号） |
| 所有对话框单元测试 | 用 `object.__new__` 绕过 `__init__`，无法发现 R-14 这类构造期错误 | 按 R-14 第 2 点，引入 `tests/support/fake_qt.py`，每个对话框至少一个经过 `__init__` 的测试 |
| `tests/unit/test_preview_window.py` | 覆盖的是只为测试保留的 `list_widget` 遗留分支，生产代码从不构造它 | 改为针对表格模型与真实构造路径；删除遗留分支 |
| `tests/unit/test_preview_model.py` 计时测试 | 只测了模型类的惰性构造时间 | 在 5 万条数据上测构造、筛选、全部接受的 Python 侧耗时，分别设上限 |
| 范围对话框测试 | 没有测单文件模式下继续按钮是否可用（R-15） | 见 R-15 验证 |
| 预览按钮测试 | 没有测 `setAutoDefault(False)`（R-17） | 见 R-17 验证 |
| 方案标签与中转链测试 | 只测"修改后"情形；假下拉框不发信号，且只用一条可用链的 s2tw | 见 R-16、R-19 验证 |

另外，`_set_progress_cancelling`（`core/workflow.py:82-88`）通过 `progress.__self__` 找进度器，对 controller 传入的绑定方法有效，但包装过的回调会静默跳过。建议把进度器对象显式传入 workflow，而不是反推。

---

## 6. 建议批次

| 批次 | 条目 | 建议提交主题 |
| --- | --- | --- |
| 0 | R-14、R-15，以及 `tests/support/fake_qt.py` | `fix: restore preview construction and single-file scope` |
| A | R-04 | `fix: report committed files when writeback progress fails` |
| B | R-02、R-03、R-13 | `fix: keep Jieba probe and direction across settings loops` |
| C | R-16、R-17、R-18、R-20、R-22 | `fix: keep saved options and rule sets intact in settings dialogs` |
| D | R-01、R-11 | `fix: classify every rewritten quotation mark` |
| E | R-05、R-08 | `fix: preserve newer schemas and merge preference updates` |
| F | R-06、R-07、R-12、R-10 | `perf: share one rule overlay per planning run` |
| G | R-09 | `fix: report source line numbers for skipped XHTML` |
| H | R-19、R-21、R-23、R-24、R-25、R-26 | `ui: fix profile state, layout order and remaining labels` |
| I | 第 5 节测试改写 | `test: make regression tests fail without their fixes` |

批次 0 修的是阻断问题，必须最先完成，并在修复后立即发布补丁版本。批次 A 影响用户对"是否已写入"的判断，紧随其后。

每个批次结束运行 `mise exec -- uv run pytest`、`mise exec -- ruff check .`；全部完成后运行 `make check`。批次 0、C、H 完成后，还要在 Sigil 中实际走一遍：选单个文件 → 设置 → 预览 → 应用。

---

## 附录：复现脚本

脚本位于同目录的 `scripts/round2/`。用 `.venv/bin/python docs/reviews/2026-09-23/scripts/round2/<脚本>` 运行，工作目录不限；脚本通过 `scripts/_env.py` 定位仓库，使用仓库自带的 macOS arm64 payload。本轮已逐个运行并核对输出。

| 脚本 | 对应 |
| --- | --- |
| `preview_repro.py` | R-14（先打印 BLOCKER 再继续探测）、R-17、R-23、R-24、R-26 |
| `scope_repro.py` | R-15 |
| `config_repro.py` | R-21、R-25（标准按钮文字） |
| `load_profile_repro.py` | R-16 |
| `label_repro.py` | R-19、R-20 |
| `rename_repro.py` | R-18 |
| `hardcoded.py`、`i18n_check.py` | R-25、R-26（残留字面量、必需键清单） |
| `selfcalls.py` | R-14（静态检查 `self.<name>(` 是否有定义） |
| `perf_model.py` | R-26（5 万条时的模型耗时） |
| `fakeqt.py` | 以上 UI 脚本共用的假 Qt（按真实 Qt 规则发信号） |
| `l01.py`、`l01b.py` | R-01、R-11 |
| `l02.py` | R-10 |
| `l07_files.py`、`l07_perf.py`、`l07_prof.py`（参数为规则数，如 `500`） | R-07 |
| `l07_count.py` | 第 5 节计数测试 |
| `l07_stale.py` | R-12 |
| `l07_eq.py` | 等价性模糊测试（无差异） |
| `l09.py` | R-06 |
| `l10.py` | 第 5 节进度合并测试 |
| `l13.py` | R-09 |
| `probe_check.py` | R-02（新 backend 的探测状态为 `not_started`） |
| `s1_jieba_loop.py` | R-02 |
| `s2_direction_reset.py` | R-03 |
| `s3_commit_progress.py` | R-04 |
| `s4_future_schema.py` | R-05 |
| `s6_stale_prefs.py` | R-08 |
| `common.py` | l01/l01b/l02 共用的规划辅助函数 |

这些脚本用于复现与核对，不是回归测试。实现者应按各条目的"验证"部分把场景写进 `tests/`。
